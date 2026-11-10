# S04. Candle patterns and geometry

**Status:** todo

**Summary:** Every playbook pattern detected per bar through TA-Lib plus custom tweezer detectors, and candle geometry for the last eight bars, each checked against hand-built bars.

## Goal

Detect the patterns in spec section 12.4, each returning bullish, bearish or none, using the named TA-Lib functions and custom code for tweezer top and bottom. Compute geometry per bar: direction, body share, wick shares, range against ATR, gap from the previous close.

**Done when:** Every detector has a test on hand-checked bars, and any relaxed definition is written down.

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

- VERIFY each TA-Lib function name and exact definition.
- Several definitions rely on gaps, which are rare inside a day on 15-minute bars: decide which to relax and document it.
- Pattern names must match the shared pattern list used by the playbook.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `DSB` heading.
