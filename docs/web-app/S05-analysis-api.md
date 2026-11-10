# S05. Analysis API

**Status:** todo

**Summary:** Overview, trades, trade detail, learning, patterns, calibration and playbook data with real names and a link to each LangSmith trace.

## Goal

Replace the stubbed analysis routes with queries over the `SIM`, `MEMORY` and `EVAL` tables. Trade detail gathers everything behind one decision: bars around it, patterns, the memory that was shown, candidates, probabilities, the LLM's reason, the journal, outcomes and the trace link.

**Done when:** Tests cover each route against fake storage, and every asset in a response carries both its real name and masked ID.

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

- Filters on the trades list.
- How the LangSmith trace URL is built.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `WEB` heading.
