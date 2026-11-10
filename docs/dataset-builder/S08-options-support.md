# S08. Options support

**Status:** todo

**Summary:** Quotes with implied volatility and Greeks for a filtered set of contracts, and option instrument rows with strike, expiry and type, added to builds.

## Goal

Add an options provider (candidate: Massive, formerly Polygon.io) that downloads 15-minute quotes for a filtered contract set, and write the option quotes table and option instrument rows.

**Done when:** A build that includes an options-enabled asset produces quote rows and instrument rows, tested on recorded data.

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
- The contract filter (strikes around the money, expiries) that keeps volume and cost manageable.
- Whether Greeks come from the provider or are computed.
- How strikes are rescaled so they stay consistent with masked prices.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `DSB` heading.
