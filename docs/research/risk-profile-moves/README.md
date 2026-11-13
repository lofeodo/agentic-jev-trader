# How far the five assets move: 15 minutes, a day, overnight

Throwaway measurement for issue #53 ("Risk profile: what medium risk means for a day trader, and which limits can be tuned"). Run on 2026-11-13. Branch `research/risk-profile-moves`, never merged. Only summary numbers are committed; the raw price bars are not (both data providers forbid sharing them) and live outside the repo.

## How to rerun

Needs the `agentic-jev-trader` conda env (Python 3.12, TA-Lib, numpy, pandas) and a Twelve Data free-plan key in an env file as `TWELVE_DATA_API_KEY`. Each command is one line and works in cmd and bash. `<bars_dir>` must be an existing directory outside the repo. Nothing costs money; the download takes about 2 minutes.

```
conda run -n agentic-jev-trader python docs/research/risk-profile-moves/get_bars.py <bars_dir> <env_file>
conda run -n agentic-jev-trader python docs/research/risk-profile-moves/measure.py <bars_dir>
```

`download_bars.py` is a copy of the script on the `research/candle-detector-counts` branch; `get_bars.py` calls it for a shorter date range.

## Data

- Stocks SPY, AAPL, JPM, XOM: Twelve Data, 15-minute bars, regular hours, `adjust=all`.
- BTCUSDT: Binance public monthly 15-minute files, UTC.
- Range: 2024-03-10 to 2025-03-09, the year of the build-up run. Nothing from the test period (10 March to 8 May 2025) was downloaded.
- Bars with zero volume are dropped. No bar is filled in.

## Plain-language definitions

- **Typical move in 15 minutes**: the median of TA-Lib's average true range over 14 bars (ATR), as a percent of the price. The stop prices of the candidate trades sit 1, 2, or 3 of these away from the entry price.
- **Day, open to close**: how far the price ended from where it started that day (a session for a stock, a UTC day for Bitcoin), ignoring direction.
- **Overnight jump**: for a stock, the difference between one session's last price and the next session's first price, ignoring direction. A stop price cannot protect against it. Bitcoin trades around the clock and has none.

## Results

All figures are percent of price. "p90" means 9 times in 10 the figure was smaller.

| Asset | 15-minute move: median (p10 to p90) | 1 hour: median / p90 | Day open to close: median / p90 / largest | Overnight jump: median / 1 night in 20 / 1 in 100 / largest |
|---|---|---|---|---|
| SPY | 0.167 (0.104 to 0.281) | 0.135 / 0.476 | 0.37 / 1.03 / 2.93 | 0.28 / 1.17 / 1.81 / 4.13 |
| AAPL | 0.317 (0.220 to 0.490) | 0.238 / 0.843 | 0.66 / 2.05 / 6.96 | 0.40 / 1.84 / 3.39 / 9.40 |
| JPM | 0.287 (0.208 to 0.447) | 0.228 / 0.768 | 0.69 / 1.87 / 5.41 | 0.33 / 1.49 / 2.72 / 6.06 |
| XOM | 0.306 (0.231 to 0.415) | 0.237 / 0.781 | 0.74 / 1.84 / 4.14 | 0.35 / 1.34 / 2.47 / 3.14 |
| BTCUSDT | 0.334 (0.175 to 0.610) | 0.238 / 0.820 | 1.40 / 4.18 / 11.88 | none |

Bars: 6,442 each for SPY and AAPL, 6,386 for JPM, 6,384 for XOM (249 sessions), 35,040 for BTCUSDT (365 days).

### What a losing trade costs at each size

Loss when a position closes at its stop price, for stops 1 / 2 / 3 typical 15-minute moves away, next to the trading costs of getting in and out (stocks: $1 commission each way plus 0.05% slippage each way; Bitcoin: 0.1% trading fee plus 0.05% slippage each way).

| Position | SPY loss | AAPL loss | BTCUSDT loss | Costs: stock / Bitcoin |
|---|---|---|---|---|
| $2,000 | $3 / $7 / $10 | $6 / $13 / $19 | $7 / $13 / $20 | $4 / $6 |
| $10,000 | $17 / $33 / $50 | $32 / $63 / $95 | $33 / $67 / $100 | $12 / $30 |
| $20,000 | $33 / $67 / $100 | $63 / $127 / $190 | $67 / $134 / $200 | $22 / $60 |
| $40,000 | $67 / $134 / $201 | $127 / $254 / $381 | $134 / $267 / $401 | $42 / $120 |

JPM and XOM sit within a few dollars of AAPL.

## What it shows

- Under the limits before issue #53 (largest position $2,000), a losing trade cost $3 to $20 and trading costs took $4 to $6 of it: at most 0.2% of a $10,000 account.
- A trade sized to lose $100 with the middle stop needs about $16,000 of AAPL or $30,000 of SPY, more than the account.
- Bitcoin's costs in and out (0.3% of the position) are about one typical 15-minute move, so a Bitcoin trade with the tightest stop pays in costs almost what it risks.
