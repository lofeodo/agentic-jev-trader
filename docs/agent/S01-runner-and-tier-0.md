# S01. Runner and Tier 0

**Status:** todo

**Summary:** The replay loop over the shared clock that advances the broker, settles stops and closed trades, writes outcomes, logs a decision for every asset at every step, enforces a call budget and resumes from the last completed step.

## Goal

Build the loop from spec sections 9.1, 9.2 (Tier 0) and 9.5: walk the clock, skip assets whose market is closed, run the code tier, call into Tier 1 and Tier 2 through defined hooks, record the last completed step, resume after a restart, and stop the job when the per-run call budget is spent.

**Done when:** A run over the fixture dataset with the hooks stubbed logs one decision per open asset per step and resumes mid-run with identical results.

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

- What the call budget counts (calls, tokens or dollars) and what state a stopped run is left in.
- Whether assets within a step are processed in order or concurrently.
- How run status is reported for the live view.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `AGT` heading.
