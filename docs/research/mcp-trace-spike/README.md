# Spike: does a LangSmith trace reach an MCP tool handler? (issue #31)

Run 2026-11-13. Throwaway code: this branch is never merged.

## Words used here

- **Trace:** LangSmith's record of one piece of agent work from start to finish, for example one clock step. LangSmith bills and limits by the number of traces (the free plan allows 5,000 a month).
- **Step inside a trace:** one nested piece of that work, such as a tool call. LangSmith calls it a run. Steps inside a trace are not counted for billing.
- **Hop:** the agent and the memory server are two separate programs talking over HTTP. The question is whether work done on the far side of that hop shows up inside the agent's trace or as a trace of its own.

## Answer

Yes, it can, and it takes about five lines on each side. Left alone, it does not: the memory server's work becomes a second trace for every tool call.

| What was tried | Traces per agent step | Where the server's work landed | What it took |
|---|---|---|---|
| Nothing passed, server tracing on | **2** | Its own separate trace | Nothing. This is the default, and the bad case. |
| LangSmith's headers in the call's `_meta` | 1 | Inside the agent's trace, under the tool call | Agent: pass `meta=` on `call_tool`. Server: read `_meta` in the handler. One long-lived client. |
| LangSmith's headers as HTTP headers | 1 | Inside the agent's trace, under the tool call | Works, but HTTP headers belong to the connection, so it needs a new client for every call. |
| Server tracing switched off | 1 | The server sends nothing | Nothing. The agent's own tool-call step still records the call's inputs, result, and duration. |

The second row is the one to use if the server's steps are wanted. Its trace looked like this:

```
- agent-step-meta (chain)            <- the LangGraph run
  - recall (chain)                   <- the graph node
    - memory.search_episodes (tool)  <- the agent's own step around the MCP call
      - snowflake_query (retriever)  <- created inside the memory server
```

The run was repeated once with the same result.

## What it took (the `_meta` route)

Agent side, inside a function decorated with LangSmith's `@traceable`:

```python
headers = get_current_run_tree().to_headers()   # {"langsmith-trace": ..., "baggage": ...}
result = await client.call_tool("search_episodes", args, meta=headers)
```

Server side, in the tool handler:

```python
meta = dict(ctx.request_context.meta or {})
parent = {k: meta[k] for k in ("langsmith-trace", "baggage") if k in meta}
with tracing_context(parent=parent):
    rows = run_the_query(...)
```

## Facts for later tickets

- **`call_tool` does take a per-call `meta` argument** in MCP SDK 2.3.0 (`mcp/client/client.py`), although the docs pages do not show it. Extra keys in `_meta` arrive in the handler untouched, next to the SDK's own `io.modelcontextprotocol/*` keys. The connection negotiated protocol version `2026-07-28`.
- **A `@traceable` function called inside a LangGraph node nests under that node** with no extra work, and `get_current_run_tree()` works inside it.
- **The server uploads its own steps**, so it needs its own `LANGSMITH_API_KEY`. Started without one, every tool call still succeeded: the server logged a `401 Unauthorized` warning and its steps were simply missing from the trace.
- **The extra-trace risk is real and silent.** With tracing on in the server and no parent passed, each tool call adds a trace. A full evaluation that made 4 memory calls would count as 5 traces instead of 1. The safe rule for the server: trace only when a parent arrives, otherwise switch tracing off for that call (`tracing_context(enabled=False)`).
- **Not tested: the OpenTelemetry route.** The MCP SDK already writes the standard `traceparent` value into `_meta` on every request and reads it on the server (`mcp/shared/_otel.py`, on by default), but only when an OpenTelemetry exporter is installed. The env has only `opentelemetry-api`, so those steps go nowhere. Using this route would mean two more packages and switching LangSmith to its OpenTelemetry mode. The `_meta` route above worked, so this was left alone.
- **Timings mean little here.** A call took about 110 to 170 ms with the server tracing and 54 ms with it off (50 ms of each is a pretend query). The gap is this spike forcing an upload before answering, so that nothing was lost when the server was killed. A real server uploads in the background.
- **Billing was not checked on an invoice.** The trace counts above were read back through LangSmith's API. That traces, not steps, are what is billed comes from the LangSmith research (issue #10).
- LangSmith's `list_runs()` is deprecated and goes away after 2027-01-31; `client.runs.query()` replaces it.
- The spike used 14 of the month's 5,000 free traces, in a LangSmith project named `mcp-trace-spike`.

## Versions

Python 3.12.16, `mcp` 2.3.0, `langgraph` 1.2.20, `langsmith` 0.14.17, `opentelemetry-api` 1.45.2, Windows 11. Server: `MCPServer` over Streamable HTTP on localhost. Client: `mcp.Client`.

## Run it again

Needs `LANGSMITH_API_KEY` in the environment. Sends only made-up data. About 5 traces per run.

```
conda run -n agentic-jev-trader python docs/research/mcp-trace-spike/run_spike.py
```

To see what happens when the server has no LangSmith key (the script then reports missing server steps, which is the expected result):

```
conda run -n agentic-jev-trader python docs/research/mcp-trace-spike/run_spike.py --server-no-key
```

## Files

- `server.py`: a stand-in for the memory server, with one tool that does one traced pretend query.
- `run_spike.py`: starts the server, runs a one-node LangGraph agent that calls the tool once per variant, then reads the traces back from LangSmith and prints the table.
