# S06. Namespaces and seeding

**Status:** todo

**Summary:** A separate memory namespace per run with tested isolation, and starting a run from a copy of another run's episodes and track record.

## Goal

Enforce that runs never share episodes or track records, and implement seeding from a `seed_namespace` as in spec section 13.8. This is how a test-period run starts with what was learned in the development period.

**Done when:** Tests prove two runs cannot see each other's memory and that a seeded run sees the copied records from its first step.

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

- How seeded episodes are ordered against the new run's steps so the no-lookahead rule still holds.
- Copy at start versus read-through to the seed namespace.
- Seeding must also carry whatever S5 stores for search.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `MEM` heading.
