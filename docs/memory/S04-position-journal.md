# S04. Position journal

**Status:** todo

**Summary:** A journal per open position holding entry, exit plan, running state and manage history, returned for all open positions and kept and linked to its episode on close.

## Goal

Implement `get_open_positions` and `update_position` for the journal in spec section 13.4. This is the one kind of memory that is always on, including in the memory-off variant.

**Done when:** Tests cover creation, per-step updates, partial closes and adds, and the link to the episode on close.

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

- The wording of the 'condition that would invalidate the trade' and who supplies it.
- How the all-positions summary shown in a full evaluation is condensed.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `MEM` heading.
