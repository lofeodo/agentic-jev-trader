# S03. Tier 1 screen and manage

**Status:** todo

**Summary:** The per-asset Jev screen and per-position manage call, the handling of hold, close, reduce and add, journal updates, and the rules that trigger a full evaluation.

## Goal

For an asset with no position, ask the screen question. For an open position, call manage with the journal and current snapshot and act on the answer. Decide when Tier 2 runs: a pattern fired, the screen said yes, or manage answered 'add'.

**Done when:** Scripted Jev answers produce the expected closes, reductions, journal entries and Tier 2 triggers.

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

- Probability threshold for acting on a screen or manage answer.
- What `thesis_intact` changes, if anything, beyond being recorded.
- Whether 'add' goes through the full evaluation unchanged or with the existing position as a constraint.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `AGT` heading.
