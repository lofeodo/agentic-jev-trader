# S03. Futures rules

**Status:** todo

**Summary:** Micro futures with contract multiplier, per-contract margin, valuation every step and a roll to the next front contract before expiry.

## Goal

Add futures to the engine: dollars mean margin committed, whole contracts only, profit and loss through the multiplier, valuation every step, and the roll before expiry. Total exposure is reported so the leverage limit can be checked.

**Done when:** Hand-calculated tests pass for margin, multiplier profit and loss, and a roll.

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

- Roll timing and the cost charged for a roll.
- What happens on a margin shortfall.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `BRK` heading.
