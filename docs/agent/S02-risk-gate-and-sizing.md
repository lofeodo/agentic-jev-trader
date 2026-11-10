# S02. Risk gate and sizing

**Status:** todo

**Summary:** Plain-code position, exposure and daily-loss limits with the final say on every order, plus bucket building and the probability-weighted dollar size rounded down to whole units.

## Goal

Implement the limits in assumption 4 (10% of account value per position, total exposure of twice account value, no new trades after a 3% daily loss) and the option rule of at least seven days to expiry. Implement spec section 11.2: buckets from account value, the weighted average, rounding down, clipping to limits, and no trade at zero units.

**Done when:** Each limit and each sizing rule has a hand-calculated test, including futures exposure and option premium.

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

- Bucket percentages (default 1, 2, 4, 6 and 10 percent).
- Whether the gate shrinks an oversized order or rejects it.
- How 'the day' is defined for the loss limit when crypto trades around the clock.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `AGT` heading.
