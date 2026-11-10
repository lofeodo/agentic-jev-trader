# S01. Spot engine

**Status:** todo

**Summary:** A pure simulation engine for stocks and crypto, long and short: dollar-to-unit conversion, next-bar fills with slippage and fees, margin and daily short fees, per-step valuation and code-enforced stops.

## Goal

Build the engine for spot instruments from the rules in spec section 10.2 and assumptions 3 to 8: starting cash, dollars to whole shares (fractional for crypto), fill at next bar open plus slippage, commission or percentage fee, short margin and daily borrow fee, valuation every step, stop enforcement, and partial closes.

**Done when:** Hand-calculated tests pass for each rule: fills, costs, margin, short fees, rounding and stops.

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

- Slippage model and the default cost numbers for each asset class.
- Stop fill price when a bar gaps through the stop.
- How buying power is computed with shorts and overnight holds.
- What the daily loss limit does to open positions, if anything (see foundation S2).

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `BRK` heading.
