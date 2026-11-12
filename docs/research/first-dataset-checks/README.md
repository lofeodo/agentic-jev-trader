# First dataset checks (throwaway)

Assets for the map ticket "Data providers and the first dataset"
(https://github.com/lofeodo/agentic-jev-trader/issues/25). This branch is never merged; the
decisions live on the ticket. Run on 2026-11-12. No raw price files are committed: both
providers' terms forbid sharing them.

## Scripts

- `dividend_check.py <env file> <symbol> ...`: pulls a year of Twelve Data 15-minute bars with
  `adjust=splits` and `adjust=all` and prints the days where the two diverge.
- `td_crypto_check.py <env file>`: what Twelve Data's free plan returns for crypto bars.
- `bn_gaps.py BTCUSDT ETHUSDT`: downloads Binance's public monthly 15-minute files
  (data.binance.vision, no account) and counts missing bars.
- Stock gap counts used `twelvedata_sample.py` from the `research/data-provider-sample` branch.

Run each with `conda run -n agentic-jev-trader python <script> ...` from the repo root.

## Results

### Dividend correction on 15-minute bars (Twelve Data, `adjust=all`)

The ratio of dividend-corrected to split-corrected price steps on each dividend day by the
dividend's share of the price:

| Asset | Step days, 2025-10 to 2026-11 | Implied dividend per share |
|---|---|---|
| SPY | 2025-12-19, 2026-03-20, 2026-06-18, 2026-09-18 | $2.00, $1.76, $1.91, $1.88 |
| Exxon | 2025-11-14, 2026-02-12, 2026-05-15, 2026-08-17 | $1.03, $0.99, $1.06, $1.03 |

### Twelve Data crypto bars

BTC/USD and ETH/USD 15-minute bars exist (Binance feed from 2020-02, Coinbase feed from
2021-05) but carry no volume field. Not usable where volume is needed.

### Binance public files, 15-minute bars

BTCUSDT and ETHUSDT: first bar 2017-08-17 04:00 UTC, last file 2026-10, 322,270 bars each.

| Year | Missing bars | Zero-volume bars (BTCUSDT) |
|---|---|---|
| 2017 | 32 | 43 |
| 2018 | 260 (longest gap 33 hours from 2018-02-08) | 0 |
| 2019 | 117 | 4 |
| 2020 | 82 | 3 |
| 2021 | 65 | 5 |
| 2022 | 0 | 0 |
| 2023 | 5 (2023-03-24, 12:45 to 14:00 UTC) | 5 |
| 2024 to 2026-10 | 0 | 0 |

81 bars in the early years have timestamps off the 15-minute grid. Open times are in
milliseconds until the end of 2024 and in microseconds from 2025.

### Twelve Data stock gaps (full history, `adjust=splits`)

Days with a bar count other than 26, leaving out scheduled half days and anything before
2020-01-06. Weekdays with no bars are market holidays for every asset, except 2020-02-18 for
SPY and QQQ.

| Asset | First bar | Odd days from 2022-01-03 | Odd days before 2022 |
|---|---|---|---|
| SPY | 2020-02-10 | 2022-01-04 (19 bars), 2022-06-03 (27), 2023-03-22 (24) | 8 |
| Apple | 2019-09-16 | none | none (messy until 2020-01-03) |
| JPMorgan | 2019-09-16 | 2022-05-10 (2 bars), 2023-03-22 (24) | 5 |
| Exxon | 2019-09-16 | 2022-05-10 (2 bars), 2023-03-22 (24) | 5 |
| Microsoft | 2019-09-16 | 2023-03-22 (23) | 2 |
| Nvidia | 2019-09-16 | 2022-06-03 (27), 2023-03-22 (24) | 3 |
| QQQ | 2020-02-10 | 5 days in 2022, 2023-03-22 (23) | 9 |
| IWM | 2020-02-10 | 5 days in 2022 | 15 |

After 2023-03-22 every asset has only holidays and scheduled half days. Half days carry 14
to 16 bars, not 13.

## Licence terms read (2026-11-12)

- Coinbase Market Data Terms of Use (https://www.coinbase.com/legal/market_data, updated
  2026-08-07): forbids using market data to "develop, train, fine-tune, teach, validate,
  benchmark, or otherwise improve any artificial intelligence or machine learning model,
  algorithm, chatbot, agent, or other automated system".
- Binance Vision Dataset Terms
  (https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md,
  updated 2026-08-26): CC BY-NC-SA 4.0; permits "algorithmic historical backtesting for purely
  personal non-production research"; subject to the Binance Terms of Use, which could not be
  read (the page did not load).
- Twelve Data Terms of Use (https://twelvedata.com/terms, updated 2026-01-01): store data
  "solely for Internal Use"; no commercial use of free tier data; delete all data on
  termination. The "permitted timeframes specified in the Documentation" for storage were not
  found. The pricing page describes the free plan as internal, non-display, personal and
  non-commercial use.
- Kraken: the OHLCVT archive page carries no terms of its own; the Global Terms ban "data
  extraction methods" on "Our Content", and whether that covers the archive is unclear.
