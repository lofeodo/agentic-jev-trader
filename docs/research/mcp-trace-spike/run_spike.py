"""Throwaway spike: does a LangSmith trace started in the agent reach an MCP tool handler?

Starts the stand-in memory server (server.py) as its own process, runs a one-node
LangGraph agent that calls its tool once per variant, then reads the traces back from
LangSmith and prints, per variant, how many traces were created and where the
server's work landed.

Run from the repo root:

    conda run -n agentic-jev-trader python docs/research/mcp-trace-spike/run_spike.py

Needs LANGSMITH_API_KEY in the environment. Sends only made-up data, to a LangSmith
project named mcp-trace-spike. Creates about 5 traces per run.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, TypedDict

os.environ["LANGSMITH_TRACING"] = "true"
os.environ.setdefault("LANGSMITH_PROJECT", "mcp-trace-spike")

import httpx2
from langchain_core.tracers.langchain import wait_for_all_tracers
from langgraph.graph import END, START, StateGraph
from langsmith import Client as LangSmithClient
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree
from langsmith.run_trees import get_cached_client
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

PORT = 8765
URL = f"http://127.0.0.1:{PORT}/mcp"
PROJECT = os.environ["LANGSMITH_PROJECT"]
VARIANTS = ("none", "meta", "http", "off")
SERVER_RUN_NAME = "snowflake_query"


class State(TypedDict, total=False):
    spike_id: str
    variant: str
    result: dict[str, Any]


def build_graph(shared: Client) -> Any:
    @traceable(name="memory.search_episodes", run_type="tool")
    async def call_memory_tool(spike_id: str, variant: str) -> dict[str, Any]:
        args = {"query": "similar past episodes", "spike_id": spike_id, "variant": variant}
        trace_headers = get_current_run_tree().to_headers()
        if variant == "meta":
            # One long-lived client; the trace headers ride in this call's `_meta`.
            res = await shared.call_tool("search_episodes", args, meta=trace_headers)
        elif variant == "http":
            # HTTP headers belong to the connection, so this needs a client per call.
            async with httpx2.AsyncClient(headers=trace_headers) as http:
                async with Client(streamable_http_client(URL, http_client=http)) as per_call:
                    res = await per_call.call_tool("search_episodes", args)
        else:
            res = await shared.call_tool("search_episodes", args)
        if res.structured_content is not None:
            return dict(res.structured_content)
        return {"text": [getattr(c, "text", "") for c in res.content]}

    async def recall(state: State) -> State:
        return {"result": await call_memory_tool(state["spike_id"], state["variant"])}

    graph = StateGraph(State)
    graph.add_node("recall", recall)
    graph.add_edge(START, "recall")
    graph.add_edge("recall", END)
    return graph.compile()


async def run_agent(spike_id: str) -> None:
    async with Client(URL) as shared:
        print("MCP protocol version:", shared.protocol_version)
        graph = build_graph(shared)
        for variant in VARIANTS:
            t0 = time.perf_counter()
            out = await graph.ainvoke(
                {"spike_id": spike_id, "variant": variant},
                config={
                    "run_name": f"agent-step-{variant}",
                    "metadata": {"spike_id": spike_id, "variant": variant},
                },
            )
            ms = (time.perf_counter() - t0) * 1000
            print(f"[{variant}] {ms:.0f} ms, handler saw: {json.dumps(out['result'].get('handler_saw'))}")
    wait_for_all_tracers()
    get_cached_client().flush()


def wait_for_port(port: int, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.3)
    raise RuntimeError(f"server did not open port {port}")


def fetch_runs(ls: LangSmithClient, started: dt.datetime, spike_id: str) -> list[Any]:
    runs = list(ls.list_runs(project_name=PROJECT, start_time=started))
    by_id = {r.id: r for r in runs}

    def belongs(r: Any) -> bool:
        if spike_id in json.dumps(r.inputs or {}, default=str):
            return True
        return ((r.extra or {}).get("metadata") or {}).get("spike_id") == spike_id

    trace_ids = {r.trace_id for r in runs if belongs(r)}
    return [r for r in by_id.values() if r.trace_id in trace_ids]


def variant_of(r: Any, roots: dict[Any, Any]) -> str | None:
    v = (r.inputs or {}).get("variant")
    if isinstance(v, str):
        return v
    root = roots.get(r.trace_id)
    if root is not None:
        return (root.inputs or {}).get("variant")
    return None


def report(runs: list[Any]) -> bool:
    by_id = {r.id: r for r in runs}
    roots = {r.trace_id: r for r in runs if r.parent_run_id is None}
    complete = True
    print()
    print(f"{'variant':8} {'traces':6} {'server run':28} parent of server run")
    for variant in VARIANTS:
        mine = [r for r in runs if variant_of(r, roots) == variant]
        traces = {r.trace_id for r in mine}
        agent_roots = [r for r in mine if r.parent_run_id is None and r.name == f"agent-step-{variant}"]
        server_runs = [r for r in mine if r.name == SERVER_RUN_NAME]
        if not agent_roots or (variant != "off" and not server_runs):
            complete = False
        if not server_runs:
            where, parent = "none sent", "-"
        else:
            s = server_runs[0]
            same = bool(agent_roots) and s.trace_id == agent_roots[0].trace_id
            where = "inside the agent's trace" if same else "its own separate trace"
            p = by_id.get(s.parent_run_id) if s.parent_run_id else None
            parent = p.name if p is not None else ("(root)" if s.parent_run_id is None else str(s.parent_run_id))
        print(f"{variant:8} {len(traces):<6} {where:28} {parent}")

    print()
    for variant in VARIANTS:
        print(f"trace tree(s) for [{variant}]:")
        mine = [r for r in runs if variant_of(r, roots) == variant]
        children: dict[Any, list[Any]] = {}
        for r in mine:
            children.setdefault(r.parent_run_id, []).append(r)

        def show(r: Any, depth: int) -> None:
            print("  " + "  " * depth + f"- {r.name} ({r.run_type})")
            for c in sorted(children.get(r.id, []), key=lambda x: x.start_time):
                show(c, depth + 1)

        for root in sorted(children.get(None, []), key=lambda x: x.start_time):
            show(root, 0)
    return complete


def main() -> int:
    if not os.environ.get("LANGSMITH_API_KEY"):
        print("LANGSMITH_API_KEY is not set")
        return 2
    spike_id = uuid.uuid4().hex[:12]
    started = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)
    here = Path(__file__).parent
    # --server-no-key: start the server without a LangSmith key, to see what a tool
    # call does when the server cannot upload its own steps.
    no_key = "--server-no-key" in sys.argv
    server_env = dict(os.environ)
    if no_key:
        server_env.pop("LANGSMITH_API_KEY", None)
        server_env.pop("LANGCHAIN_API_KEY", None)
    server = subprocess.Popen([sys.executable, str(here / "server.py"), str(PORT)], env=server_env)
    try:
        wait_for_port(PORT)
        asyncio.run(run_agent(spike_id))
        time.sleep(3)
    finally:
        server.terminate()
        server.wait(timeout=10)

    ls = LangSmithClient()
    print(f"\nspike id {spike_id}; reading traces back from LangSmith project {PROJECT!r}")
    deadline = time.time() + (30 if no_key else 120)
    runs: list[Any] = []
    while time.time() < deadline:
        runs = fetch_runs(ls, started, spike_id)
        roots = {r.trace_id: r for r in runs if r.parent_run_id is None}
        got_server = {variant_of(r, roots) for r in runs if r.name == SERVER_RUN_NAME}
        got_agent = {r.name for r in runs if r.parent_run_id is None}
        if {"none", "meta", "http"} <= got_server and {f"agent-step-{v}" for v in VARIANTS} <= got_agent:
            time.sleep(5)  # let stragglers land
            runs = fetch_runs(ls, started, spike_id)
            break
        time.sleep(5)
    complete = report(runs)
    if not complete:
        print("\nWARNING: some expected runs never showed up in LangSmith within 2 minutes")
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
