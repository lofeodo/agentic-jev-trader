# Where to get full-market US stock volume for 15-minute bars

Research note, read on 2026-11-13. Throwaway branch `research/stock-volume-providers`; never merged.
No accounts were created and nothing was bought. Only public documentation and pricing pages were read.
"Not confirmed" means the primary page did not say, could not be loaded (HTTP 403/404/500), or the fact came only from a secondary source.

## Plain-language terms

- **Volume**: how many shares changed hands in a period. If 1,000,000 shares of SPY traded between 10:00 and 10:15, the bar's volume is 1,000,000.
- **Consolidated tape / SIP**: the combined official record of trades from every US exchange and off-exchange venue. Volume taken from it is "full-market" volume. Example: if 100 shares trade on NYSE and 300 on Nasdaq, the tape shows 400.
- **Single-venue feed (for example IEX)**: a feed from one exchange only. Its volume is just that exchange's trades, often a few percent of the total, so the same example would show 100 or 300, not 400.
- **OHLCV bar**: open, high, low, close prices and volume for one time slice (here 15 minutes).
- **Adjusted**: past prices (and volumes) restated to account for stock splits and dividends so old and new prices compare fairly.
- **Regular hours**: 9:30 am to 4:00 pm Eastern. **Extended hours**: the pre-market and after-hours sessions around it.

## A. Twelve Data

### A1. Where does its US volume come from?

Twelve Data has a support article that answers this directly. Source: https://support.twelvedata.com/en/articles/9935903-us-equities-market-data (read 2026-11-13).

- Its real-time default US feed comes from "compliant, low-latency venues that allow redistribution without additional licensing" and captures roughly 5% of total US trading volume. Consolidated feeds from all major US exchanges are a separate licensed upgrade. The article does not say whether the default feed is SIP.
- Historical and end-of-day data "becomes available after midnight ET on the next trading day" and covers 100% of US volume aggregated across every stock exchange, with no extra licence.
- Plan differences: every plan includes the real-time default feed; historical and end-of-day data are available from the Basic plan. The article gives no fuller plan-by-plan table.

So Twelve Data's own words say historical volume should be full-market on every plan including free Basic, and that real-time volume is about 5%. Our measurements (zero-volume bars; "thin days" at 3% to 8% of normal) look like the roughly-5% real-time feed leaking into data that should have been replaced by the full-market version. That is an inference, not something Twelve Data says. Whether intraday bars are "historical" (replaced after midnight) or stay on the real-time feed is Not confirmed.

The pricing page (https://twelvedata.com/pricing, read 2026-11-13) lists Basic $0, Grow $79/month, Pro $229/month, Ultra $999/month. The page does not name the US data source, intraday history depth, or volume coverage. The page's own structured data lists different prices ($29/$99/$329), so the page is internally inconsistent; treat the visible prices as unconfirmed.

### A2. Documented explanation of zero-volume bars or partial days?

Not found. The time_series docs (https://twelvedata.com/docs/market-data/time-series, read 2026-11-13) say only that volume is "Trading volume which occurred during the current bar", and that extended-hours bars are supplied without volume. They do not discuss zero-volume bars. The support article "Why Close and OHLC prices can differ" (https://support.twelvedata.com/en/articles/6374888-why-close-and-ohlc-prices-can-differ, read 2026-11-13) only says different data sources and aggregation can change reported prices and volume.

### A3. Would a paid plan return different historical intraday volume?

Not documented. Nothing read says historical intraday volume differs by plan; the article above implies it is the same (100% of volume) on all plans. The cheapest paid plan is Grow at $79/month (visible price, unconfirmed against the page's structured data). Paying is a gamble until Twelve Data support confirms; asking their support, with a failing example (a date and symbol), is free and is the cheapest next step.

## B. Alternative sources

Rate and price facts are from the page cited in each row. "Canada" cells say what the page showed; no page read said Canadians are blocked, but none confirmed they are allowed, except where stated.

### B1. Massive (formerly Polygon.io) - strongest candidate

- Volume: states every US trade prints to one consolidated tape, claims 100% of US market volume, individual plans are SIP-based. Source: https://massive.com/stocks (read 2026-11-13).
- Plans: Basic $0 (end-of-day, 2 years of history, 5 calls/min); Starter $29/month (15-minute delayed, 5 years, unlimited calls); Developer $79/month (10 years); Advanced $199/month (real-time, 20+ years); Business $2,499/month. Same page. The pricing page itself (https://massive.com/pricing) only showed Advanced $199 and Financials $29 when fetched, so confirm Starter's price in a browser.
- History by plan (aggregates endpoint): Basic 2 years, Starter 5 years, Developer 10 years, Advanced all history, data from 2003-09-10. Source: https://massive.com/docs/rest/stocks/aggregates/custom-bars (read 2026-11-13).
- Minute aggregates are shown on every tier on https://massive.com/stocks, including free Basic, but a search summary described Basic as end-of-day only. Which tiers allow intraday bars is Not confirmed.
- Adjusted: `adjusted` parameter, on by default (split adjustment); `adjusted=false` gives raw. Dividend adjustment is Not confirmed. Same docs page.
- Hours: Not confirmed (docs page does not say). Extended-hours bars would need filtering by timestamp.
- Rate limits and effort: Basic 5 calls/min. Pull size: 4 stocks x about 17 months of 15-minute bars is a few requests if one request can return the whole range; the per-request bar cap is Not confirmed from a read page.
- Free-tier reach: Basic's 2 years of history, read on 2026-11-13, reaches back only to about 2024-11, so it cannot cover 2023-12 to 2025-05. Starter's 5 years reaches 2021 and covers everything needed.
- Terms: individual plans are licensed for personal and non-professional use; brokerage, redistribution, customer-facing display or 200+ users need Business (https://massive.com/stocks). AI/ML or benchmarking terms: Not confirmed.
- Canada: Not confirmed. Registration decides professional/non-professional status (https://massive.com/knowledge-base).
- Price: $29/month for Starter (cancel after one month of pulling) = US$29.

### B2. Databento

- Free credit: "$125 in free credits" for new sign-ups, expiring 6 months after sign-up, one claim per team. Source: https://databento.com/pricing and https://databento.com/signup (read 2026-11-13). Sign-up needs only an email and password; no country list on the page. Canada is Not confirmed.
- Datasets for US stocks:
  - Databento US Equities Mini (EQUS.MINI): OHLCV 1s/1m/1h/1d, "sourced from the proprietary market data feeds of both alternative trading systems (ATS) and RegNMS venues", bars aggregated across component venues. Historical data starts 2023-03-28. Sources: https://databento.com/docs/datasets/equs-mini and https://databento.com/blog/databento-us-equities-mini-now-available (read 2026-11-13). Databento calls it a composite built from several venues; it does not say it equals the full consolidated tape, so whether its volume matches SIP volume is Not confirmed. The pages do not say which trades are included.
  - Databento US Equities (DBEQ.MAX / main dataset): historical from $0.40/GB, since 2018, built from direct exchange feeds, "not an SIP", but venues listed include all major exchanges, the Nasdaq and NYSE trade-reporting facilities (off-exchange prints) and IEX. Source: https://databento.com/datasets/DBEQ.MAX. 1-minute OHLCV bars summed over these venues is the closest thing to full-market volume that Databento sells; "same as SIP" is Not confirmed.
  - Databento US Equities Summary (EQUS.SUMMARY): consolidated volume across all US exchanges, but only daily bars, no 1-minute (https://databento.com/docs/venues-and-datasets/equs-summary). Useful only as a daily cross-check.
- Cost: pay-as-you-go, metered by uncompressed size; no per-GB rate shown for EQUS.MINI. A rough estimate (our arithmetic, not Databento's): 4 stocks x about 390 one-minute bars x about 540 trading days is under 1 million records, tens of megabytes. At $0.40/GB that is cents, well inside the $125 credit. The exact figure comes from Databento's cost estimator (`metadata.get_cost`), which needs an account; Not confirmed.
- Adjusted: Not confirmed. Databento sells raw trade-derived bars; split/dividend adjustment would be done by us (corporate actions are a separate Databento product, same pricing page).
- Hours: bars are built from trades, so extended-hours trades appear and need filtering. If no trade occurs in an interval, no bar is produced (https://databento.com/docs/schemas-and-data-formats/ohlcv).
- Rate limits: Not confirmed. Standard plan is $199/month (not needed).
- Terms: AI/ML and personal-use terms: Not confirmed (the pricing page shows a licensing comparison but its layout was unclear).
- Price: $0 for this pull using the free credit, if the account is accepted from Canada. Pay-as-you-go otherwise, estimated cents.

### B3. Alpha Vantage

- Intraday: `TIME_SERIES_INTRADAY` supports any month since 2000-01 via a `month` parameter, `adjusted=true` by default (splits and dividends), `extended_hours` defaults to true (set false for regular hours). Source: https://www.alphavantage.co/documentation/ (read 2026-11-13). The docs mention "consolidated NBBO quotes/trades/volumes" generally, but do not tie it to this endpoint; consolidated volume for intraday is Not confirmed.
- Price: free tier 25 requests/day (https://www.alphavantage.co/support/); the docs tip says historical intraday data needs a premium plan, but whether the free key can use the `month` parameter is Not confirmed. Premium starts at $49.99/month for 75 requests/minute, no daily cap (https://www.alphavantage.co/premium/).
- Effort: one request per stock per month; 4 stocks x 18 months = 72 requests; fits the free 25/day in 3 days if free access works.
- Canada: Not confirmed. Terms of service PDF could not be read as text; personal-use and AI/ML terms Not confirmed. The support page says Alpha Vantage is "a NASDAQ-licensed data provider".

### B4. Tiingo

- Intraday volume is IEX only: "The number of shares traded on IEX only." Source: https://www.tiingo.com/documentation/iex (read 2026-11-13). This is the same kind of problem we have. Not a fit.
- Price: free Starter $0 (50 requests/hour, 1,000/day); Power $30/month personal, $50/month commercial (https://www.tiingo.com/about/pricing). "Internal use" licence means your own personal use.

### B5. Financial Modeling Prep (FMP)

- Pricing page returned HTTP 403. From a search summary of FMP pages (secondary, Not confirmed): Starter about $19 to $29/month with 5 years of history and 5-minute charts for US symbols; Premium $49 to $69/month with intraday charts; Ultimate with 1-minute. Intraday volume source: Not confirmed. Free tier intraday: Not confirmed. Canada and terms: Not confirmed.

### B6. EODHD

- Intraday US stocks: 1-minute from 2004, 5-minute and other intervals from October 2020; US 1-minute includes pre- and after-hours. Max range per request: 1m 120 days, 5m 600 days. 5 API calls per intraday request. Source: https://eodhd.com/financial-apis/intraday-historical-data-api and https://eodhd.com/pricing (read 2026-11-13).
- Intraday bars are raw only: "EODHD does not retroactively adjust historical intraday prices for later stock splits or dividends." Volume source (consolidated?): Not confirmed.
- Price: free $0 (20 calls/day, no intraday, 1 year of end-of-day); Active trader (EOD + intraday) $29.99/month ($24.99/month billed yearly); paid limit 100,000 calls/day, 1,000/minute.
- Canada and personal-use terms: Not confirmed (pricing page links "Personal Plans" but terms not read).

### B7. Finnhub

- Pricing page and docs fetches gave no plan details. Free-tier access to US intraday candles, history depth, price and volume source: Not confirmed.

### B8. Marketstack

- Free $0 (100 requests/month, 1 year, end-of-day only). Basic $9.99/month ($8.99 billed yearly), 10,000 requests/month, 10 years, "IEX intraday (US)". Professional $49.99/month. Source: https://marketstack.com/product (read 2026-11-13). Intraday is IEX, so single-venue volume. Not a fit.

### B9. FirstRate Data

- One-off purchase of downloadable files, not an API. Stock bundle: 1-minute, 5-minute, 30-minute, 1-hour, 1-day bars; all prices and volumes adjusted for dividends and splits (unadjusted also included); out-of-hours trades included; history from 2000. Source: https://firstratedata.com/b/22/stock-complete-historical-intraday and https://firstratedata.com/i/stock/AAPL (read 2026-11-13).
- Volume source: the AAPL page says data is "collected and aggregated from 25 exchanges (including dark pools)", which suggests consolidated; the word "consolidated" is not used, so Not confirmed.
- Price: the pages show only a "Buy Now" button for the one-off purchase price. Update fees: $99.95 per year for a single ticker after one free month; $59.95 per month for the bundle. One-off single-ticker price: Not confirmed. Canada and terms: Not confirmed (FAQ page 404).

### B10. Kibot

- 1-minute stock bars back to 1998; tick data with NBBO back to 2009. Custom orders from $19; examples: SPY + QQQ 1-minute full history $125, prices exclude tax. Unadjusted, split-adjusted and fully adjusted series offered. Free samples exist. Source: https://www.kibot.com/ (read 2026-11-13).
- Volume consolidated or primary-exchange: Not confirmed. Hours and Canada: Not confirmed.

### B11. Interactive Brokers (IBKR)

- Needs a brokerage account. Historical bars of 15 minutes are allowed up to 365 days per request; pacing limits are strict only for bars of 30 seconds or smaller. Sources via search: https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-bars/max-duration-per-bar-size (page itself returned 403), https://www.interactivebrokers.com/docs/tws-api/doc/md/introduction.
- Whether the volume is consolidated, whether a market-data subscription is required, account minimum, and Canadian availability: Not confirmed. Opening a brokerage account is a bigger step than the project needs. Not a first choice.

### B12. Stooq

- The download page returned HTTP 403. Intraday US coverage, history and terms: Not confirmed. Not pursued.

### B13. Yahoo Finance via yfinance

- Valid intervals include 15m, but "Intraday data cannot extend last 60 days" for 15-minute bars (1-hour: 730 days). Source: yfinance source docstring and code, https://raw.githubusercontent.com/ranaroussi/yfinance/main/yfinance/scrapers/history.py (read 2026-11-13). It cannot reach 2023-12 to 2025-05. Not a fit.
- yfinance says it is "intended for research and educational purposes" and that the Yahoo API is "intended for personal use only" (https://ranaroussi.github.io/yfinance/).

## Summary table

| Candidate | Volume coverage (as documented) | Intraday history depth | Price (USD) | Canada access | Licence note |
|---|---|---|---|---|---|
| Twelve Data (current) | Says historical is 100% of US volume; real-time default about 5% | n/a | Basic $0; Grow $79/month | Works today | Not reviewed |
| Massive Starter | Consolidated tape (SIP), "100% of US volume" | 5 years (covers 2023-04 on); free Basic only 2 years | $29/month | Not confirmed | Individual plans: personal, non-professional use |
| Databento | EQUS.MINI: multi-venue composite; main dataset: all exchanges plus off-exchange prints, not SIP | From 2023-03-28 (Mini); since 2018 (main) | $125 free credit; est. cents for this pull | Not confirmed | Not confirmed |
| Alpha Vantage | Not confirmed for intraday | Since 2000 via `month` | Free 25 requests/day (intraday on free: not confirmed); $49.99/month premium | Not confirmed | Terms not read |
| Tiingo | IEX only | Not stated | $0; $30/month | Not confirmed | Personal use |
| FMP | Not confirmed | Not confirmed | $19 to $29+/month (secondary) | Not confirmed | Not confirmed |
| EODHD | Not confirmed | 1m from 2004; 5m from Oct 2020 | $29.99/month | Not confirmed | Not confirmed |
| Finnhub | Not confirmed | Not confirmed | Not confirmed | Not confirmed | Not confirmed |
| Marketstack | IEX | 10 years (Basic) | $9.99/month | Not confirmed | Not confirmed |
| FirstRate Data | "25 exchanges including dark pools" | From 2000 | One-off price not confirmed; update $99.95/year | Not confirmed | Not confirmed |
| Kibot | Not confirmed | 1m from 1998 | From $19 one-off (SPY+QQQ $125) | Not confirmed | Not confirmed |
| IBKR | Not confirmed | 15-minute bars: 365 days per request | Needs account | Not confirmed | Not confirmed |
| Stooq | Not confirmed | Not confirmed | Not confirmed | Not confirmed | Not confirmed |
| yfinance | Not confirmed | 15m: last 60 days only | $0 | Works | "Personal use only" |

## C. Ranked recommendation

1. **Massive Starter, US$29 for one month.** The only candidate whose own page says consolidated tape (SIP) with 5 years of history, which covers 2023-04 onward, at a price that fits the budget. Pull all four stocks over the full range in one month and cancel. The free Basic key can first show whether minute bars, the `adjusted` flag and volume look right, but its 2-year limit hides the April 2024 dates, so Starter is the cheapest way to check those.
2. **Databento free credit ($125).** Pull 1-minute OHLCV for the four stocks, sum into 15-minute bars. Likely free. Prefer the main US Equities dataset (all exchanges and trade-reporting facilities) over EQUS.MINI if its volume is closer to the daily totals. Cost: our own adjustment of prices for splits and dividends, since bars are raw trade-derived.

Also worth doing for free: ask Twelve Data support why intraday volume is 0 on specific dates, quoting its own article that historical volume covers 100% of US volume.

## Still unconfirmed (needs an account or a page that would not load)

- Whether Twelve Data's intraday bars are replaced by the full-market version after midnight; whether paid plans change it.
- Massive: Canadian sign-up; which tiers serve minute bars; dividend adjustment; extended-hours handling; per-request bar cap; AI/ML terms.
- Databento: Canadian sign-up; exact cost from the estimator; whether EQUS.MINI volume matches full-market volume; adjustment; licence terms.
- Alpha Vantage: free-key access to historical intraday; consolidated volume; terms (PDF unreadable).
- FMP, Finnhub, Stooq, IBKR, Kibot, FirstRate (one-off price, terms), EODHD (volume source): details above marked Not confirmed.
