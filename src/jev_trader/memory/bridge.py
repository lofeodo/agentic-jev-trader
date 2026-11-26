"""The bridge from the agent to the memory server: the official MCP SDK's own client plus three
tool definitions written by hand (spec appendix 5, section 4; appendix 10, section 2; ADR 0006).

The LLM sees each lookup tool through its hand-written definition (`definitions`), which has no
sim or step input. The bridge is made for one moment (`LookupContext`: the sim, the step, the asset
looked at, the job, an open position's direction) and fills those in on every call, so the LLM
can only ask about the current or earlier moments. A test compares the definitions with the
server's own tool list, so the two cannot drift apart.

Code's first search goes through the same tool, by the same bridge, as the LLM's.

The bridge is asynchronous; the agent's steps are not. `Connection` keeps one session open for a
sim and gives the lookups for each moment as plain blocking calls (`BlockingLookups`).

Choices the spec leaves to the build:

- An input the LLM may not set (the sim, the step, or anything not in its definition) is refused
  before anything is sent, as is a value not in its definition's list (`NotAllowed`, whose
  message names the allowed values). What the agent then does is the LLM loop's to decide.
- A tool that fails on the server raises `MemoryToolFailed` with the server's message; whether
  it is retried or counted is the LLM loop's to decide (appendix 5, last section).
"""

import asyncio
import concurrent.futures
import threading
import tomllib
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Self

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
from jev_trader.memory.server import FILLED_IN_BY_CODE, PATH
from jev_trader.memory.track_record import TrackRecord

WORDING_PATH = Path(__file__).resolve().parents[3] / "prompts" / "llm_tools.toml"
SERVER_SETTINGS_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "memory_server.toml"
)
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
class LookupContext:
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

    def __init__(
        self, session: ClientSession, context: LookupContext, patterns: Sequence[str]
    ):
        self.session = session
        self.context = context
        self.definitions = {d.name: d for d in definitions(context.job, patterns)}

    def _filled_in(self, name: str) -> dict:
        """The inputs the server's tool takes from code, from this context."""
        c = self.context
        values = {
            "sim": c.sim,
            "step": c.step,
            "asset_looked_at": c.asset,
            "job": c.job,
            "position_direction": c.position_direction,
        }
        return {
            key: values[key]
            for key in FILLED_IN_BY_CODE[name]
            if values[key] is not None
        }

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


def local_url(path: Path = SERVER_SETTINGS_PATH) -> str:
    """The memory server's address on this computer: the host and port it listens on, from
    `config/memory_server.toml`."""
    with open(path, "rb") as file:
        settings = tomllib.load(file)
    return f"http://{settings['host']}:{settings['port']}"


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


class Connection:
    """Memory's lookups as plain blocking calls, for the agent's steps (`MemoryLookups` in
    `jev_trader.llm.selection`), over one MCP session kept open for the whole sim.

    The session lives on an event loop in a thread of its own, opened and closed by one task, as
    the SDK's client asks; each lookup is handed to that loop and waited for. Use it as a context
    manager, then `lookups_at(context)` gives the lookups for one moment. `open_session` makes
    the session (by default `connect(url)`); tests pass one reaching an in-process server.
    """

    def __init__(
        self,
        url: str,
        patterns: Sequence[str],
        open_session: Callable[[], AbstractAsyncContextManager[ClientSession]]
        | None = None,
    ):
        self.patterns = list(patterns)
        self._open = open_session or (lambda: connect(url))
        self._session: ClientSession | None = None
        self._held: concurrent.futures.Future | None = None
        self._close: asyncio.Event | None = None

    def __enter__(self) -> Self:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        opened: concurrent.futures.Future = concurrent.futures.Future()
        self._held = asyncio.run_coroutine_threadsafe(self._hold(opened), self._loop)
        try:
            self._session = opened.result()
        except BaseException:
            self._stop()
            raise
        return self

    def __exit__(self, *exc) -> None:
        if self._close is not None:
            self._loop.call_soon_threadsafe(self._close.set)
        try:
            if self._held is not None:
                self._held.result()
        finally:
            self._stop()

    async def _hold(self, opened: concurrent.futures.Future) -> None:
        """Open the session, hand it over, and keep it open until asked to close."""
        self._close = asyncio.Event()
        try:
            async with self._open() as session:
                opened.set_result(session)
                await self._close.wait()
        except BaseException as error:
            if not opened.done():
                opened.set_exception(error)
            raise

    def _stop(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
        self._loop.close()

    def run(self, coroutine):
        """Run one of the bridge's calls on the session's loop and wait for its answer."""
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result()

    def lookups_at(self, context: LookupContext) -> "BlockingLookups":
        if self._session is None:
            raise RuntimeError("the memory connection is not open")
        return BlockingLookups(
            self, MemoryBridge(self._session, context, self.patterns)
        )


class BlockingLookups:
    """The three lookups for one moment, each a plain call that waits for its answer."""

    def __init__(self, connection: Connection, bridge: MemoryBridge):
        self.connection, self.bridge = connection, bridge

    def search(self, **filters: str) -> SearchResult:
        return self.connection.run(self.bridge.search(**filters))

    def read(self, episode_ids: list[str]) -> Episodes:
        return self.connection.run(self.bridge.read(episode_ids))

    def track_record(self, pattern: str, direction: str) -> TrackRecord:
        return self.connection.run(self.bridge.track_record(pattern, direction))
