# Agent stack: LangGraph, LangChain MCP adapters, MCP Python SDK transport

Ticket: lofeodo/agentic-jev-trader#9 (map #7). All sources read 2026-11-11. Versions from the PyPI JSON API on the same day.

## Short answer

- LangGraph 1.2.20 is current and stable. Python >=3.10.
- The brief's "LangChain MCP adapters" package (`langchain-mcp-adapters`, 0.3.2) is **archived and no longer maintained**. Its successor is the `langchain.mcp` namespace, installed with `langchain[mcp]`, class `MCPAdapter`, built on FastMCP. It is in beta.
- The official MCP Python SDK (`mcp`) is now **2.3.0** (v2 line since 2026-07-28). v1.x (1.30.0 latest) is in maintenance. `langchain-mcp-adapters` 0.3.2 pins `mcp<2`.
- Recommended HTTP transport: **Streamable HTTP**. SSE is deprecated; WebSocket removed.
- Checkpointing fits the resume rule only partly: there is no Snowflake checkpointer. Keep the brief's "last completed step in Snowflake" as the source of truth; LangGraph checkpoints are optional.

## Versions (PyPI, 2026-11-11)

| Package | Latest stable | requires-python | Source |
|---|---|---|---|
| langgraph | 1.2.20 (2026-11-05) | >=3.10; classifiers list 3.10-3.13 | https://pypi.org/pypi/langgraph/json ; https://raw.githubusercontent.com/langchain-ai/langgraph/main/libs/langgraph/pyproject.toml |
| langchain-mcp-adapters | 0.3.2 (2026-08-06), repo archived | >=3.10; requires `mcp<2.0.0,>=1.24.0`, `langchain-core>=1.3.3` | https://pypi.org/pypi/langchain-mcp-adapters/json ; https://api.github.com/repos/langchain-ai/langchain-mcp-adapters (archived: true, last push 2026-09-16) |
| langchain | 1.5.0 (2026-11-11); extra `mcp` pulls `fastmcp>=4.0.11` | >=3.11; classifiers 3.11-3.14 | https://pypi.org/pypi/langchain/json |
| langchain-core | 1.8.0 | >=3.11; classifiers incl. 3.14 | https://pypi.org/pypi/langchain-core/json |
| fastmcp | 4.1.8 (server/client extras need `mcp>=2.3,<3`) | >=3.10 | https://pypi.org/pypi/fastmcp/json ; https://pypi.org/pypi/fastmcp-slim/json |
| mcp (official SDK) | 2.3.0 (2026-10-02); v1 line 1.30.0 (2026-09-07) | >=3.10; classifiers 3.11-3.14 | https://pypi.org/pypi/mcp/json |
| langgraph-checkpoint-postgres | 3.2.0 | >=3.10 | https://pypi.org/pypi/langgraph-checkpoint-postgres/json |
| langgraph-checkpoint-sqlite | 3.1.3 | >=3.10 | https://pypi.org/pypi/langgraph-checkpoint-sqlite/json |

Python 3.14: `pip install --dry-run` on the developer's Python 3.14.0 resolved all three combinations below without error (resolution only; nothing was run). LangGraph's own classifiers stop at 3.13, so 3.14 is not declared there; a conda env pinned to 3.12 or 3.13 is the conservative choice. `mcp`, `langchain` and `langchain-core` declare 3.14.

Dry-run results (my own check, 2026-11-11, Python 3.14.0):
- `langgraph langchain-mcp-adapters mcp` resolves to adapters 0.3.2 + mcp 1.30.0 (pip backtracks to v1 because of the `mcp<2` pin).
- `langgraph langchain-mcp-adapters "mcp>=2"` resolves to adapters **0.3.1** + mcp 2.3.0 (0.3.1 requires only `mcp>=1.24.0`, https://pypi.org/pypi/langchain-mcp-adapters/0.3.1/json). Not verified to work at runtime.
- `langgraph "langchain[mcp]>=1.4"` resolves to langchain 1.5.0, fastmcp 4.1.8, mcp 2.3.0.

## Adapters package: name and status

- README banner: "This repository is no longer actively maintained"; MCP support moved to `langchain.mcp`; migrate to `langchain[mcp]`. https://github.com/langchain-ai/langchain-mcp-adapters
- Migration guide: `pip install "langchain[mcp]>=1.4.0"`; `MultiServerMCPClient` becomes `MCPAdapter` (async context manager); `load_mcp_tools` becomes `adapter.list_tools()`; config uses `{"mcpServers": {name: {"url": ...}}}` with no `transport` key; Streamable HTTP is chosen by an `http(s)` URL; headers/auth go on a FastMCP transport or `fastmcp.Client`; `session(...)` is not exposed; each returned tool opens its own session per call; the namespace is beta (`LangChainBetaWarning`); interceptors are replaced by `@wrap_tool_call` middleware; tool names are auto-prefixed `{server}_{tool}` for multi-server configs; sampling and roots are unsupported. https://docs.langchain.com/oss/python/migrate/langchain-mcp-adapters
- Announcement: built on FastMCP 4, negotiates the new stateless protocol per connection and falls back to the older handshake; Python only for now. https://www.langchain.com/blog/mcp-in-langchain-stateless-protocol-elicitation-and-more
- Old package usage (works against mcp 1.x): `MultiServerMCPClient({"name": {"url": ".../mcp", "transport": "http", "headers": {...}}})`, `await client.get_tools()` (new session per tool call), `async with client.session("name") as s: tools = await load_mcp_tools(s)`. MCP execution errors (`isError`) go back to the model as a `ToolMessage` with `status="error"`. https://github.com/langchain-ai/langchain-mcp-adapters

## MCP Python SDK and transport

- v2 implements spec revision `2026-07-28` and serves it alongside older revisions with no flag. `Client` probes `server/discover` and falls back to `initialize` for older servers (`mode="auto"` default). https://py.sdk.modelcontextprotocol.io/whats-new/ ; https://py.sdk.modelcontextprotocol.io/protocol-versions/
- v1.x is in maintenance (critical and security fixes); libraries may pin `mcp>=1.28,<2`. https://py.sdk.modelcontextprotocol.io/whats-new/
- v2 server class is `MCPServer` (`from mcp.server import MCPServer`), replacing `FastMCP` at `mcp.server.fastmcp`; WebSocket removed; `host`/`port`/`stateless_http` moved from the constructor to `run()`. https://py.sdk.modelcontextprotocol.io/whats-new/
- The README calls Streamable HTTP "the transport you deploy"; serve with `mcp run server.py --transport streamable-http`; client: `async with Client("http://localhost:8000/mcp") as client: await client.call_tool("add", {"a": 1, "b": 2})`. https://github.com/modelcontextprotocol/python-sdk
- v1 README: `FastMCP("Demo", json_response=True)` and `mcp.run(transport="streamable-http")`. https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/v1.x/README.md
- SSE is deprecated by the MCP spec (per LangChain's migration guide, above). The SDK still lists SSE among supported transports.
- Kubernetes/deploy guidance (https://py.sdk.modelcontextprotocol.io/run/deploy/):
  - By default only localhost Host headers are accepted; a deployed server returns 421 unless you pass `transport_security=TransportSecuritySettings(allowed_hosts=[...])` to `streamable_http_app()`. In-cluster service names (for example `mcp-memory:*`, `mcp-memory.trading-agent.svc.cluster.local:*`) must be allowlisted.
  - On the 2026-07-28 protocol requests are self-contained: any replica can serve any request, nothing to configure. On 2025-11-25 and earlier, sessions live in one worker's memory and need sticky sessions (else 404); `stateless_http=True` removes that need but loses server-to-client features. With one replica per Deployment this matters little.
  - `mcp.run("streamable-http")` starts one uvicorn process; scale with `uvicorn server:app --workers N`. There is no built-in health-check route: add your own for Kubernetes probes.

## LangGraph: LLM-called vs code-called MCP tools

Composed from the sources above; the snippet was not executed.

- LLM-called: load tools (old: `MultiServerMCPClient.get_tools()`; new: `MCPAdapter(...).list_tools()`) and bind them in the `propose` node's model/agent (`create_agent(model, tools)` per the adapters README) or a `ToolNode`.
- Code-called (observe, retrieve, decide, act, record): bypass the LLM. Either call the same loaded LangChain tool objects with `await tool.ainvoke({...})`, or use a plain MCP client (`mcp.Client(url).call_tool(name, args)` in v2; `client.session("name")` + `session.call_tool` with the old adapters). Hold clients in graph config/context, not in state.

```python
# new stack: pip install "langchain[mcp]>=1.4" langgraph
from langchain.mcp import MCPAdapter
cfg = {"mcpServers": {"market-data": {"url": "http://mcp-market-data:8000/mcp"},
                      "broker-sim":  {"url": "http://mcp-broker-sim:8000/mcp"}}}
async with MCPAdapter(cfg) as adapter:
    tools = await adapter.list_tools()            # names prefixed e.g. market-data_get_snapshot
    by_name = {t.name: t for t in tools}
    llm_tools = [by_name["market-data_get_instrument"]]   # illustrative: only these go to the LLM
    snap = await by_name["market-data_get_snapshot"].ainvoke({...})  # direct call from a node
```

## Checkpointing vs brief section 9.5 (resume)

- A checkpoint is saved per super-step, keyed by `thread_id`; `graph.invoke(None, {"configurable": {"thread_id": ...}})` resumes from the latest checkpoint; `get_state` returns a `StateSnapshot`. Writes of nodes that finished in a failed super-step are kept and not re-run. https://docs.langchain.com/oss/python/langgraph/checkpointers
- Production checkpointer: `PostgresSaver`/`AsyncPostgresSaver` (`.setup()` creates tables); `SqliteSaver` for local dev; in-memory is lost on restart. Listed third-party: sqlite, postgres, mongodb, Azure Cosmos DB. **No Snowflake checkpointer is listed.** https://docs.langchain.com/oss/python/langgraph/persistence ; https://docs.langchain.com/oss/python/langgraph/checkpointers
- Node execution is at-least-once on resume; side effects need idempotency keys derived from durable state. https://docs.langchain.com/oss/python/langgraph/fault-tolerance
- Durability modes "exit" / "async" / "sync" ("async" the default; "sync" needed to survive a process crash). This came from a docs search summary spanning several pages, not one page I read directly; verify before relying on it.
- Fit: a Kubernetes Job restart loses the local filesystem, so SQLite would need a PVC. Options: (a) keep brief 9.5 as written: store the last completed step in Snowflake and, on restart, start a fresh graph invocation for the next step (one graph run per step, no checkpointer); (b) add Postgres for checkpoints (extra service). Since the loop runs the graph once per 15-minute step and each step's effects (broker order, memory write) must be idempotent anyway, (a) is the simpler fit. Key broker-sim and memory writes by step_id.

## Contradictions with the brief / open items

- Brief section 5 ("VERIFY package name"): `langchain-mcp-adapters` is archived; the replacement is `langchain[mcp]` (beta).
- Brief section 10 ("VERIFY recommended HTTP transport"): Streamable HTTP; SSE deprecated.
- The official SDK is on a new major (2.x) while the old adapters pin 1.x. `langchain[mcp]` brings FastMCP 4, which depends on `mcp>=2.3`.
- Not verified: runtime behaviour on Python 3.14; whether adapters 0.3.1 works with mcp 2.x; how to pass trace headers (separate ticket); the exact `langchain.mcp` API for direct calls beyond what the migration guide shows; durability-mode default.
