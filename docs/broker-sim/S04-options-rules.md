# S04. Options rules

**Status:** todo

**Summary:** Long single calls and puts bought at the ask and sold at the bid, with premium as the dollar amount and expired contracts settled at their final value.

## Goal

Add options to the engine: buy to open only, fill at the ask, close at the bid, dollars mean premium paid, whole contracts, and settlement at expiry. Selling to open and multi-leg trades are rejected.

**Done when:** Hand-calculated tests pass for buy, sell, expiry in and out of the money, and rejection of disallowed orders.

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

- How a stop works for an option (on the option price or on the underlying).
- Fill when the quote for the next bar is missing or the spread is very wide.
- Settlement value at expiry in masked price terms.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `BRK` heading.
