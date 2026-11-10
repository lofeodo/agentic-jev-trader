# Assumptions

The defaults the spec chose on the developer's behalf (spec section 6), as confirmed by
the author in foundation S1 on **2026-11-10**: all sixteen are kept as written (decision
FND-010). Changing one later is a decision logged in [DECISIONS.md](DECISIONS.md) and
noted here.

## The sixteen assumptions

| # | Assumption | Status |
| --- | --- | --- |
| 1 | Simulation only; no live or paper trading. The broker code is isolated so one could be added later. | Confirmed |
| 2 | A "live run" is a historical replay started from the web app and watched as it progresses, as fast as the models allow. | Confirmed |
| 3 | Starting account value is $10,000 simulated. | Confirmed |
| 4 | Risk limits: 10% of account value per position, total exposure 2x account value, no new trades for the rest of the day after losing 3%. | Confirmed (see ambiguities A1, A2) |
| 5 | Positions may be held overnight and across days; the agent decides when to exit. | Confirmed |
| 6 | Every position has a stop price set at entry, enforced by code; the profit target is advisory. | Confirmed (see A3) |
| 7 | Stocks: long and short, US regular session only, 09:30 to 16:00 Eastern. | Confirmed |
| 8 | Crypto: spot long and short only, around the clock; no crypto futures or options in version 1. | Confirmed |
| 9 | Futures: micro contracts only, regular US session only. | Confirmed (see A4) |
| 10 | Options: buying single calls and puts only; expiry at least 7 days away at entry. | Confirmed |
| 11 | Asset names, dates and price levels are masked before anything reaches a model; the web app shows real names through the asset key. | Confirmed |
| 12 | Data comes from official provider APIs, not scraping. | Confirmed; providers chosen in FND-009 |
| 13 | A track record group is shown to the agent only after at least 10 closed trades. | Confirmed |
| 14 | The LLM does not write lessons or rules; learning comes from records and computed statistics. | Confirmed |
| 15 | Single user on a local machine; no login. | Confirmed |
| 16 | The LLM provider and model are not chosen yet. | **Resolved:** DeepSeek, `deepseek-flash` (FND-007) |

## First dataset

SPY, QQQ, AAPL, NVDA and BTC (FND-010). This is the spec's default shape: four liquid
US stocks or index funds with active options, plus one major crypto asset. SPY and QQQ
also map to the micro futures MES and MNQ, so the futures steps can use the same
dataset.

## Ambiguities found while confirming

These are not changes; each is a reading the owner step must make explicit.

| ID | Question | Owner |
| --- | --- | --- |
| A1 | **What is a "day" for the 3% daily-loss stop?** Crypto trades around the clock and stocks trade 6.5 hours. Proposed reading: the US Eastern calendar day on the shared clock, measured on total account value, applied to all assets. | foundation S2 (config and clock), agent S2 |
| A2 | **What counts toward the 2x exposure limit** for options and futures? Proposed reading: notional for futures (price x multiplier x contracts), premium paid for bought options. | foundation S2, broker-sim S3 and S4 |
| A3 | **Can a stop be moved after entry?** The spec sets it at entry; `manage` can reduce or close but says nothing about moving the stop. Proposed reading: no, the stop is fixed for the position's life. | agent S2 |
| A4 | **What happens to a futures position held into expiry or overnight** given "regular session only"? Proposed reading: positions may be held overnight (assumption 5) but trade only during the session; the builder rolls the front contract. | dataset-builder S7, broker-sim S3 |
| A5 | **IEX-only stock volume** (Alpaca free plan, FND-009) is a fraction of market volume. "Volume compared with normal for that time of day" stays valid because both sides come from the same feed; the quality report says so. | dataset-builder S2 |
