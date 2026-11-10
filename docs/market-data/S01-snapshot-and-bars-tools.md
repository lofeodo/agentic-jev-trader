# S01. Snapshot and bars tools

**Status:** todo

**Summary:** Snapshot and recent-bars tools reading a published dataset from Snowflake, with the never-after-this-step rule enforced in the server and tested.

## Goal

Implement `get_snapshot` (patterns, geometry and context for a step) and `get_bars` (recent bars up to and including a step) over Snowflake through the agent role.

**Done when:** Both tools return fixture data correctly, and a test proves no row after `step_id` can be returned for any input.

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

- Maximum lookback allowed for `get_bars`.
- Behaviour when the asset's market is closed at that step.
- Whether the server caches a dataset in memory, given datasets are immutable.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `MKD` heading.
