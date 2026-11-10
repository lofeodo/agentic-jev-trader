# S03. Masking, asset key and instruments

**Status:** todo

**Summary:** Random masked IDs, day numbers in place of dates, prices rescaled so each series starts at 100, the asset key with scale factors, and the spot instrument list.

## Goal

Assign masked IDs in random order, replace dates with day numbers while keeping time of day, rescale prices, and write the mapping and scale factors as asset key rows. Build one spot instrument row per asset.

**Done when:** Masking is reversible through the asset key alone, and a test confirms no real symbol, name or date survives in masked output.

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

- Whether masking is seeded per dataset so a rebuild is reproducible.
- How volume is treated (kept, or rescaled too).
- Whether assets that trade on different calendars share one day-number line.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `DSB` heading.
