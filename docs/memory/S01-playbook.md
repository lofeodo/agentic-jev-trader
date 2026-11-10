# S01. Playbook

**Status:** todo

**Summary:** The pattern playbook seeded from the spec table, with opposite versions as separate entries, and a lookup that returns only the requested patterns.

## Goal

Turn the table in spec section 12.4 into seed data, load it into `MEMORY.PLAYBOOK`, and implement `get_playbook`. The playbook is read only and shared by all runs.

**Done when:** The seed loads idempotently and a test confirms the lookup returns exactly the requested entries.

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

- Pattern names must match the shared pattern list used by the feature builder.
- How entries with one detector and two directions (for example three inside up or down) are keyed.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `MEM` heading.
