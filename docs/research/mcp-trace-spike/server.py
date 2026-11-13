"""Throwaway spike: a stand-in for the memory MCP server, one tool over Streamable HTTP.

The tool does one traced piece of work (a pretend Snowflake query). The `variant`
argument picks how the handler looks for the caller's LangSmith trace:

- none: does not look. The traced work starts wherever LangSmith puts it.
- meta: reads LangSmith's headers from the MCP request's `_meta`.
- http: reads LangSmith's headers from the HTTP request headers.
- off:  switches tracing off for the call, so the server sends nothing to LangSmith.
"""

from __future__ import annotations

import os
import sys
import time
from functools import partial
from typing import Any

os.environ["LANGSMITH_TRACING"] = "true"
os.environ.setdefault("LANGSMITH_PROJECT", "mcp-trace-spike")

import anyio
from langsmith import traceable, tracing_context
from langsmith.run_trees import get_cached_client
from mcp.server.mcpserver import Context, MCPServer

TRACE_KEYS = ("langsmith-trace", "baggage")

server = MCPServer("memory-spike")


@traceable(name="snowflake_query", run_type="retriever")
def fake_snowflake_query(query: str, spike_id: str, variant: str) -> list[dict[str, Any]]:
    time.sleep(0.05)
    return [{"episode_id": "ep-001", "summary": "synthetic episode for " + query}]


@server.tool()
async def search_episodes(query: str, spike_id: str, variant: str, ctx: Context) -> dict[str, Any]:
    meta = dict(ctx.request_context.meta or {})
    headers = {k.lower(): v for k, v in dict(ctx.headers or {}).items()}

    if variant == "meta":
        parent = {k: meta[k] for k in TRACE_KEYS if k in meta}
    elif variant == "http":
        parent = {k: headers[k] for k in TRACE_KEYS if k in headers}
    else:
        parent = None

    if variant == "off":
        with tracing_context(enabled=False):
            rows = fake_snowflake_query(query, spike_id, variant)
    elif parent:
        with tracing_context(parent=parent):
            rows = fake_snowflake_query(query, spike_id, variant)
    else:
        rows = fake_snowflake_query(query, spike_id, variant)

    # The server is killed at the end of the spike, so send queued runs now.
    get_cached_client().flush()

    return {
        "rows": rows,
        "handler_saw": {
            "meta_keys": sorted(meta.keys()),
            "trace_keys_in_meta": [k for k in TRACE_KEYS if k in meta],
            "trace_keys_in_http_headers": [k for k in TRACE_KEYS if k in headers],
            "parent_used": bool(parent),
        },
    }


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    anyio.run(partial(server.run_streamable_http_async, port=port))
