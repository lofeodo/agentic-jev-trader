# S07. Futures support

**Status:** todo

**Summary:** Micro futures front-contract bars with roll dates, and futures instrument rows with multiplier, margin and expiry, added to builds.

## Goal

Add a futures provider (candidate: Databento) for micro contracts in the regular US session, front contracts only, with the data the broker needs to roll before expiry. Add futures rows to the instrument list.

**Done when:** A build that includes a futures-enabled asset produces contract bars and instrument rows, tested on recorded data.

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

- Paid data: needs the author's budget decision and provider choice.
- VERIFY pricing, history depth and licence terms.
- How a futures contract maps to a masked asset, and how its prices are rescaled.
- Where margin per contract comes from.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `DSB` heading.
