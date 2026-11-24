"""The bridge from the agent to the memory server: the official MCP SDK's own client plus three
tool definitions written by hand (spec appendix 5, section 4; appendix 10, section 2; ADR 0006).

The LLM sees each lookup tool through its hand-written definition (`definitions`), which has no
sim or step input. The bridge is made for one moment (`Moment`: the sim, the step, the asset
looked at, the job, an open position's direction) and fills those in on every call, so the LLM
can only ask about the current or earlier moments. A test compares the definitions with the
server's own tool list, so the two cannot drift apart.

Code's first search goes through the same tool, by the same bridge, as the LLM's.

Choices the spec leaves to the build:

- An input the LLM may not set (the sim, the step, or anything not in its definition) is refused
  before anything is sent, as is a value not in its definition's list (`NotAllowed`, whose
  message names the allowed values). What the agent then does is the LLM loop's to decide.
- A tool that fails on the server raises `MemoryToolFailed` with the server's message; whether
  it is retried or counted is the LLM loop's to decide (appendix 5, last section).
"""

import tomllib
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from jev_trader.memory.lookups import MOST_READ, Episodes, NotAllowed, SearchResult
from jev_trader.memory.search import (
    ASSET_FILTERS,
    DECIDED_FILTERS,
    DIRECTIONS,
    FULL_EVALUATION,
    POSITION_REVIEW,
    RESULTS,
    STANDING_FILTERS,
    Job,
)
from jev_trader.memory.server import PATH
from jev_trader.memory.track_record import TrackRecord

WORDING_PATH = Path(__file__).resolve().parents[3] / "prompts" / "llm_tools.toml"
LOOKUP_TOOLS = ("search_episodes", "read_episodes", "read_track_record")


class MemoryToolFailed(RuntimeError):
    """The memory server answered a tool call with its error flag."""


def load_wording(path: Path = WORDING_PATH) -> dict:
    with open(path, "rb") as file:
        return tomllib.load(file)


@dataclass(frozen=True)
class ToolDefinition:
    """A tool as the LLM sees it: its name, what it does, and the inputs it may set (a JSON
    schema)."""

    name: str
    description: str
    input_schema: dict


def _one_of(values: Sequence[str], description: str) -> dict:
    return {"type": "string", "enum": list(values), "description": description}


def definitions(job: Job, patterns: Sequence[str]) -> tuple[ToolDefinition, ...]:
    """The three lookup tools as the LLM sees them in `job`; `patterns` is every valid candle
    pattern name, from the playbook."""
    w = load_wording()
    names = sorted(patterns)
    search, read = w[job]["search_episodes"], w[job]["read_episodes"]
    search_inputs = {
        "asset": _one_of(ASSET_FILTERS, search["asset"]),
        "pattern": _one_of(["any", *names], search["pattern"]),
        "decided": _one_of(DECIDED_FILTERS[job], search["decided"]),
    }
    if job == POSITION_REVIEW:
        search_inputs["standing"] = _one_of(STANDING_FILTERS, search["standing"])
    track = w["read_track_record"]
    return (
        ToolDefinition(
            "search_episodes",
            search["description"].format(per_search=RESULTS),
            {"type": "object", "properties": search_inputs, "required": []},
        ),
        ToolDefinition(
            "read_episodes",
            read["description"],
            {
                "type": "object",
                "properties": {
                    "episode_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": MOST_READ,
                        "description": read["episode_ids"].format(per_read=MOST_READ),
                    }
                },
                "required": ["episode_ids"],
            },
        ),
        ToolDefinition(
            "read_track_record",
            track["description"],
            {
                "type": "object",
                "properties": {
                    "pattern": _one_of(names, track["pattern"]),
                    "direction": _one_of(DIRECTIONS, track["direction"]),
                },
                "required": ["pattern", "direction"],
            },
        ),
    )


@dataclass(frozen=True)
class Moment:
    """What code fills in on every call: the sim, the current step, the asset looked at, the
    job, and for a position review the open position's direction."""

    sim: int
    step: int
    asset: str
    job: Job = FULL_EVALUATION
    position_direction: str | None = None


def _checked(definition: ToolDefinition, arguments: dict) -> dict:
    """The LLM's inputs, refused if one is not in the definition or not an allowed value."""
    schema = definition.input_schema
    properties = schema["properties"]
    for name in arguments:
        if name not in properties:
            raise NotAllowed(f"{definition.name} has no input {name}.")
    for name in schema["required"]:
        if name not in arguments:
            raise NotAllowed(f"{name} is required.")
    for name, value in arguments.items():
        allowed = properties[name].get("enum")
        if allowed is not None and value not in allowed:
            listed = ", ".join(f'"{a}"' for a in allowed)
            raise NotAllowed(f"{name} must be one of {listed}.")
        if properties[name]["type"] == "array":
            least, most = properties[name]["minItems"], properties[name]["maxItems"]
            if not isinstance(value, list) or not least <= len(value) <= most:
                raise NotAllowed(f"{name} must be a list of {least} to {most} IDs.")
    return arguments


class MemoryBridge:
    """The three lookups for one moment, over an MCP client session."""

    def __init__(self, session: ClientSession, moment: Moment, patterns: Sequence[str]):
        self.session = session
        self.moment = moment
        self.definitions = {d.name: d for d in definitions(moment.job, patterns)}

    def _filled_in(self, name: str) -> dict:
        m = self.moment
        filled = {"sim": m.sim, "step": m.step}
        if name in ("search_episodes", "read_track_record"):
            filled["asset_looked_at"] = m.asset
        if name == "search_episodes":
            filled["job"] = m.job
            if m.job == POSITION_REVIEW:
                filled["position_direction"] = m.position_direction
        return filled

    async def call(self, name: str, arguments: dict) -> dict:
        """Call a lookup tool with the LLM's inputs; returns the server's structured answer."""
        if name not in self.definitions:
            raise NotAllowed(f"There is no tool {name}.")
        llm = _checked(self.definitions[name], dict(arguments))
        result = await self.session.call_tool(name, {**llm, **self._filled_in(name)})
        if result.is_error:
            text = " ".join(getattr(c, "text", "") for c in result.content)
            raise MemoryToolFailed(f"{name} failed: {text}")
        return result.structured_content

    async def search(self, **filters: str) -> SearchResult:
        return SearchResult.model_validate(await self.call("search_episodes", filters))

    async def read(self, episode_ids: list[str]) -> Episodes:
        """`episode_ids` are stored IDs: the caller maps the labels the LLM saw back first."""
        return Episodes.model_validate(
            await self.call("read_episodes", {"episode_ids": episode_ids})
        )

    async def track_record(self, pattern: str, direction: str) -> TrackRecord:
        return TrackRecord.model_validate(
            await self.call(
                "read_track_record", {"pattern": pattern, "direction": direction}
            )
        )


@asynccontextmanager
async def connect(
    url: str, http_client: httpx2.AsyncClient | None = None
) -> AsyncIterator[ClientSession]:
    """A client session with the memory server at `url` (its address, without `/mcp`)."""
    async with (
        streamable_http_client(
            url.rstrip("/") + PATH, http_client=http_client
        ) as streams,
        ClientSession(streams[0], streams[1]) as session,
    ):
        await session.initialize()
        yield session
