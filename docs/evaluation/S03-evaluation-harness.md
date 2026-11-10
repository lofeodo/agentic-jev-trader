# S03. Evaluation harness

**Status:** todo

**Summary:** One command that runs every variant on the test period with at least three seeds, seeds memory from the development run, reports the spread and logs LangSmith experiments.

## Goal

Orchestrate the comparison: development-period run to build memory, then all variants on the test period, then metrics, a comparison report produced by code, and LangSmith experiments. The test period is never used for tuning.

**Done when:** One command produces the full comparison on the fixture dataset using fake models, with a report that shows the spread across seeds.

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

- Whether runs are started in-process or as cluster Jobs, or both behind the interface.
- Report format (table in the terminal, a file, or both).
- A guard that refuses to run tuning workflows on the test period.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `EVL` heading.
