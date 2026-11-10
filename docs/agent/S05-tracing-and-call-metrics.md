# S05. Tracing and call metrics

**Status:** todo

**Summary:** LangSmith traces with run metadata for every full evaluation and one grouped trace per step for Tier 1, the trace ID saved on the episode, and tokens, cost, latency and retries recorded per call.

## Goal

Apply spec section 15: trace layout, metadata on every trace, masked IDs only, trace ID on the episode, and trace context passed to the MCP servers. Record per-call metrics on every run whether or not tracing is on.

**Done when:** With keys set, a fixture run produces the expected traces; without keys, the same run passes and still records metrics.

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

- Whether Tier 1 tracing is reduced to fit LangSmith's free tier.
- Where per-call metrics are stored.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `AGT` heading.
