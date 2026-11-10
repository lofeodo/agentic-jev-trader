# S01. Stock and crypto providers

**Status:** todo

**Summary:** One small provider interface per asset class, with a stock provider and a crypto provider that download 15-minute bars within rate limits, and asset search by name or ticker.

## Goal

Implement the provider interface and two providers: stocks and funds (candidate: Alpaca) and crypto (a major exchange's public market data API). Each downloads 15-minute bars for a date range, respects rate limits and licence terms, and supports asset search. Tests replay recorded responses; nothing calls a live API by default.

**Done when:** Bars for a sample stock and a sample crypto asset download through the interface, and the tests pass offline.

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

- VERIFY which crypto exchange API is reachable from the developer's region, and its terms.
- VERIFY Alpaca free-tier history depth and rate limits for 15-minute bars.
- Whether 15-minute bars are requested directly or aggregated from minute bars.
- Session filter: US regular session only for stocks.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `DSB` heading.
