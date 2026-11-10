# S05. Context features and situation text

**Status:** todo

**Summary:** Trend, relative volume, VWAP and level distances, ATR and bar-in-day for every bar, the normalised feature vector, and the one-paragraph situation text.

## Goal

Compute the context group from spec section 12.1: trend on 15-minute and daily bars, volume against normal for that time of day, distance from VWAP, from the day's and previous day's high and low, ATR, and bar number in the day. Build the normalised feature vector and the plain-language situation paragraph that memory search embeds.

**Done when:** Each feature is tested on constructed bars, the vector has the layout fixed in the contracts, and the situation text contains no symbol, date or price level.

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

- Definition of 'trend' on each timeframe.
- How 'normal volume for that time of day' is computed without looking ahead.
- Normalisation statistics must come only from data up to that bar.
- Wording template for the situation text.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `DSB` heading.
