# S06. Service skeleton and tracing

**Status:** todo

**Summary:** A shared MCP server factory over the verified HTTP transport, the four servers running as stubs on the fakes, an agent-side client check, and a tracing helper that does nothing when its keys are absent.

## Goal

Build the common server factory (transport, health check, tool registration from the S2 interfaces, trace-context intake) and give each of the four servers an entry point that serves its fake. Prove the agent side: connect through LangChain's MCP adapter (`langchain.mcp.MCPAdapter`, FND-011) and call one tool on each server. Add the tracing helper used by the agent and the servers; it becomes a no-op without LangSmith keys.

**Done when:** All four stub servers start locally with one command each, the client check calls a tool on each, and the test suite passes with no LangSmith key set.

Spec: [project breakdown](../project-breakdown.md). Feature index: [ROADMAP.md](ROADMAP.md).

## Detailed plan

Not written yet. It is filled in when the step starts, in plan mode, and opens with the
behaviour agreed in the planning interview.

## What was done

Nothing yet.

## Deviations from plan

None yet.

## Open issues

To settle in the planning interview:

- Transport and adapter usage come from S1.
- Whether the servers register tools from the interface definitions automatically or by hand.
- Each server's entry file is later edited by its own feature; keep it thin.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `FND` heading.
