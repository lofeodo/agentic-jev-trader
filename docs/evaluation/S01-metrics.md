# S01. Metrics

**Status:** todo

**Summary:** Money, risk, trading-behaviour, calibration and learning metrics computed from stored runs and written to the evaluation tables.

## Goal

Implement every metric in spec section 17.3: net profit before and after model costs, return, maximum drawdown, Sharpe, profit factor, win rate and averages, breakdowns by instrument type, asset class, pattern and exit reason, Brier score and confidence buckets, profit per day, share of decisions with relevant memories, and the cost of going against a negative track record.

**Done when:** Each metric has a hand-calculated test and results are written to `EVAL.RUN_METRICS` and `EVAL.CALIBRATION`.

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

- Steps per year used in the Sharpe ratio when stocks and crypto share a clock.
- What counts as the outcome for calibration (trade profitable, or direction correct).
- Precise definition of 'went against a negative track record'.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `EVL` heading.
