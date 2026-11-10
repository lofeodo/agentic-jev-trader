# S06. Replay suite

**Status:** todo

**Summary:** About thirty recorded scenarios replayed through the graph in CI, asserting that tool calls, stored records and orders are unchanged.

## Goal

Record LLM and Jev responses for about thirty fixed scenarios, replay the graph against them, and run the suite in CI on every change.

**Done when:** The replay suite runs in CI with no network access and fails when behaviour changes.

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

- How scenarios are chosen to cover each tier, instrument type and gate outcome.
- How recordings are refreshed when a prompt changes on purpose.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `INT` heading.
