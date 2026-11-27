"""The memory MCP server: three read-only tools over Streamable HTTP (spec appendix 5, section 4;
appendix 10, section 2; ADR 0006).

MCP (the Model Context Protocol) is the standard way to offer tools to a model: a server lists
its tools and a client calls them over the network. Memory is the project's only MCP server, and
it offers exactly three tools, all read-only: `search_episodes`, `read_episodes` and
`read_track_record`. It logs in with its own role, which can only read, to the Postgres
database.

Each tool takes, besides what the LLM may set, the inputs code fills in on every call: the sim,
the step, and what the search serves (the asset looked at, the job, an open position's
direction). The LLM sees the tools through the bridge's hand-written definitions
(`jev_trader.memory.bridge`), which leave those out; a test compares the two.

The tools answer with structured data (episodes, ranks, a track record); the bridge writes it as
text with `jev_trader.memory.render`, since the labels the LLM sees (E1, E2, ...) belong to one
evaluation. A tool that fails answers with the MCP error flag (`is_error`).

Served over Streamable HTTP at `/mcp`, stateless (every call stands alone), with `/health` for
Kubernetes and only the allowed host names (any other gets error 421).
"""

from collections.abc import Callable
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from jev_trader.memory.lookups import Episodes, Lookups, NotAllowed, SearchResult
from jev_trader.memory.search import Filters
from jev_trader.memory.store import MemoryStore, NoSnapshot, UnknownSim
from jev_trader.memory.track_record import TrackRecord

NAME = "memory"
PATH = "/mcp"
HEALTH_PATH = "/health"
# What code fills in on every call; the LLM never sees these inputs.
FILLED_IN_BY_CODE = {
    "search_episodes": ("sim", "step", "asset_looked_at", "job", "position_direction"),
    "read_episodes": ("sim", "step"),
    "read_track_record": ("sim", "step", "asset_looked_at"),
}

Sim = Annotated[
    int, Field(description="Filled in by code: the sim whose memory is read.")
]
Now = Annotated[
    int,
    Field(description="Filled in by code: the current step; nothing later is read."),
]
AssetLookedAt = Annotated[
    str, Field(description="Filled in by code: the asset being looked at (ASSET_03).")
]


def _answered[T](lookup: Callable[[], T]) -> T:
    """A lookup's answer; a refusal or a missing sim or snapshot comes back flagged as an error
    with its message, anything else as the SDK's own "Error executing tool"."""
    try:
        return lookup()
    except (NotAllowed, NoSnapshot, UnknownSim) as refused:
        raise ToolError(str(refused)) from refused


def build_server(store: MemoryStore) -> MCPServer:
    lookups = Lookups(store)
    server = MCPServer(NAME)

    @server.tool(
        description="Search the sim's past episodes for those most like the asset's "
        "current snapshot, narrowed by the filters. Up to 10, closest first."
    )
    def search_episodes(
        sim: Sim,
        step: Now,
        asset_looked_at: AssetLookedAt,
        job: Annotated[
            Literal["full_evaluation", "position_review"],
            Field(description="Filled in by code: what the search serves."),
        ],
        position_direction: Annotated[
            Literal["long", "short"] | None,
            Field(
                description="Filled in by code: the open position's direction, "
                "for a position review."
            ),
        ] = None,
        asset: Literal["any", "same_asset", "same_asset_class"] = "any",
        pattern: str = "any",
        decided: Literal[
            "any", "long", "short", "no_trade", "hold", "close", "reduce", "add"
        ] = "any",
        standing: Literal["any", "in_profit", "at_a_loss"] = "any",
    ) -> SearchResult:
        filters = Filters(
            asset=asset, pattern=pattern, decided=decided, standing=standing
        )
        return _answered(
            lambda: lookups.search(
                sim, step, asset_looked_at, job, filters, position_direction
            )
        )

    @server.tool(description="Read 1 to 5 past episodes in full, by their stored IDs.")
    def read_episodes(
        sim: Sim,
        step: Now,
        episode_ids: Annotated[list[str], Field(min_length=1, max_length=5)],
    ) -> Episodes:
        return _answered(lambda: lookups.read(sim, step, episode_ids))

    @server.tool(
        description="Read the totals over the sim's closed trades for one candle pattern "
        "and direction, in the asset's class."
    )
    def read_track_record(
        sim: Sim,
        step: Now,
        asset_looked_at: AssetLookedAt,
        pattern: str,
        direction: Literal["long", "short"],
    ) -> TrackRecord:
        return _answered(
            lambda: lookups.track_record(sim, step, asset_looked_at, pattern, direction)
        )

    @server.custom_route(HEALTH_PATH, methods=["GET"])
    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return server


def http_app(server: MCPServer, allowed_hosts: list[str]):
    """The server as a web app (ASGI): `/mcp` and `/health`, answering only `allowed_hosts`
    ("memory:*" allows any port of the host name "memory")."""
    return server.streamable_http_app(
        streamable_http_path=PATH,
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=allowed_hosts
        ),
    )
