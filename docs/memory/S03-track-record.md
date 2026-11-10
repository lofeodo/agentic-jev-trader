# S03. Track record

**Status:** todo

**Summary:** Per-group trade statistics updated on each closed trade, counted only up to the current step, hidden below ten trades and rendered as one plain sentence.

## Goal

Maintain the table in spec section 13.3, grouped by pattern, direction, instrument type, trend alignment, volume level and time-of-day bucket. Implement `get_track_record`, the minimum sample rule, and the sentence shown to the agent with the trade count always included.

**Done when:** Arithmetic and the minimum sample rule are tested, and a test proves trades closing after the current step are not counted.

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

- Boundaries of the high or low volume and time-of-day buckets.
- How a trade triggered by several patterns is attributed.
- Whether the table stores running totals or is computed from outcomes on read.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `MEM` heading.
