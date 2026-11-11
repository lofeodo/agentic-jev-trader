# Stock and crypto data providers (issue #13)

Read dates: all pages read 2026-11-11 unless stated. Scope: 15-minute OHLCV, about 4 US stocks/ETFs plus 1 major crypto asset, 1 to 2 years through late 2026, spot only, developer in Ontario/Quebec, personal research, data stored in a private Snowflake account.

## Headline

- Alpaca's data is the best technical fit for stocks, but Alpaca staff said on 2026-08-14 that it does not offer market data to Canadian residents, with regulatory approval targeted for about November 2026. Treat Alpaca as blocked until a signup is tried.
- Crypto: Coinbase Exchange public candles (no account, pageable to any date) is the best reachable source. Kraken's bulk CSV archive is the fallback but ends 2026-09-30.

## Alpaca (stocks, free plan)

| Question | Finding | Source |
|---|---|---|
| Price | Free plan $0, IEX feed, 200 API calls/min, history "7+ years", crypto included. Paid Algo Trader Plus $99/mo: all US exchanges, unlimited calls. | https://alpaca.markets/data |
| Feed on free plan | Real-time is IEX only. IEX is a single exchange, so real-time volume covers only IEX executions. | https://docs.alpaca.markets/docs/about-market-data-api ; staff reply, forum, 2023-11-18: https://forum.alpaca.markets/t/what-does-realtime-data-in-free-account-mean/13165 |
| SIP (consolidated) history on free plan | The bars endpoint accepts `feed=sip` (all US exchanges). A 2023 staff forum reply says the Free plan gets full-market SIP bars delayed 15 minutes, and historical data older than 15 minutes is the same on both plans. Docs say only IEX "can be used without a subscription" and that without real-time access `end` defaults to 15 minutes ago. These two statements are in tension. Not tested (no account). | https://docs.alpaca.markets/reference/stockbars ; https://docs.alpaca.markets/docs/historical-stock-data-1 ; forum link above |
| Volume | If SIP works, bars carry consolidated volume ("100% of market volume"). If only IEX, volume is a small fraction of total and is not comparable to real volume; for a volume-as-signal project this matters. | https://docs.alpaca.markets/docs/historical-stock-data-1 |
| Adjustment | `adjustment` param: `raw` (default), `split`, `dividend`, `spin-off`, `all`. So default bars are NOT adjusted; request `all` explicitly. | https://docs.alpaca.markets/reference/stockbars |
| Paging | Max 10000 data points per request. 2 years of 15-min regular-session bars is roughly 13,000 per symbol, so 2 pages each. | same |
| License | Alpaca T&C (per search snippets, not read in full): content "exclusively for personal and noncommercial access and use". Support: "you cannot redistribute Alpaca API data". Storing for your own research in a private Snowflake account is not redistribution, but no document I could read speaks to storage or caching explicitly. | https://alpaca.markets/support/redistribute-alpaca-api ; T&C PDF https://files.alpaca.markets/disclosures/alpaca_terms_and_conditions.pdf (text not extractable by my tools) |
| Canada | Staff, 2026-08-14: "Alpaca does not offer market data subscriptions to Canadian residents" for regulatory reasons; individual accounts for Canadians come first, regulatory approval targeted around November 2026. Country list page (Feb 2026) does not name Canada; the signup country field lacked Canada. Older forum posts say paper accounts are open to anyone by email, IEX only; the 2026 thread reports Canada missing from the country field. I found no confirmation of launch. | https://forum.alpaca.markets/t/is-the-market-data-subscription-available-in-canada/19519 ; https://alpaca.markets/support/countries-alpaca-is-available |

## Alpaca (crypto)

- Crypto bars use `loc` values `us` (Alpaca), `us-1` (Kraken US), `eu-1` (Kraken EU); timeframes `[1-59]Min` accepted; max 10000 per request; auth required; history depth not stated. Source: https://docs.alpaca.markets/reference/cryptobars-1
- Docs state crypto data now comes "from Alpaca itself", with quote-midpoint prices in bars. Source: https://docs.alpaca.markets/docs/historical-crypto-data-1
- So it is one account, but the volume is Alpaca's own venue volume (size unverified) and it inherits the Canada block.

## Stock alternatives

| Provider | Free tier | 15-min / adjustment | License / Canada | Source |
|---|---|---|---|---|
| Twelve Data | Basic: 8 requests/min, 800/day, real-time US equities/ETFs and crypto listed. Paid $79/$229/$999 per month (page structured data shows different amounts; unresolved). | `15min` interval, outputsize up to 5000, `adjust` = all/splits/dividends/none (default splits). Free-plan intraday history depth and volume source (single exchange or consolidated) not stated. | Personal-use terms not spelled out on pricing page; no Canada block seen. | https://twelvedata.com/pricing ; https://twelvedata.com/docs/market-data/time-series |
| Tiingo | Starter free: 50 requests/hour, 1,000/day, 500 symbols/mo, 1 GB/mo; Power $30/mo. IEX intraday depth not stated. | Not verified. | "Internal use only": own personal use, no sharing; fits personal research. | https://www.tiingo.com/about/pricing |
| Databento (US equities, not derivatives) | $125 free credit on signup, expires 6 months; then pay per GB. OHLCV-1m/1h/1d (build 15-min yourself). 16+ years history generally. Equities rate/depth not stated. | Not verified. | Redistribution after 24h for most datasets; no Canada note. | https://databento.com/pricing |
| Massive (Polygon) | Pricing page now shows only Stocks Advanced $199/mo (individual use only). Free tier not shown. Too costly. | n/a | n/a | https://massive.com/pricing |
| Alpha Vantage | Free: 25 requests/day. Premium from $49.99/mo (75 requests/min). Intraday depth not stated. | n/a | n/a | https://www.alphavantage.co/premium/ |

## Crypto exchanges

| Exchange | 15-min history | Limits | Canada access | Terms | Source |
|---|---|---|---|---|---|
| Coinbase Exchange | Public candles endpoint, granularity 900 = 15 min, max 300 candles/request, no stated lookback (page back by start/end). 2 years is about 70,000 candles = about 234 requests. No auth. | 10 req/s per IP (bursts 15). Docs: do not poll historical rates frequently. | Coinbase Canada Inc. restricted dealer in all provinces and territories (2026 filing). Public API needs no account. | Coinbase Market Data Terms (copy seen via search dated 2023-02-06, refers to Coinbase Pro; live page returned 403). Clauses seen: revocable, non-sublicensable, no altering/misrepresenting data. Personal-use and storage not verified. | https://docs.cdp.coinbase.com/exchange/reference/exchangerestapi_getproductcandles ; https://docs.cdp.coinbase.com/exchange/docs/rate-limits ; https://www.fcnb.ca/sites/default/files/2026-07/2026-04-01%20Coinbase%20Canada%20Inc..pdf ; https://www.coinbase.com/legal/market_data (not readable) |
| Kraken | REST OHLC returns only the most recent 720 candles (7.5 days at 15 min), regardless of `since`. Bulk CSV archive: 15-min candles per pair, full history through 2026-09-30 (quarterly updates; 2026Q3 latest; page updated 2026-11-02). | Not checked. | Registered restricted dealer in Canada; Canadians cannot use margin or derivatives. Archive download should not need an account (not confirmed). | Archive page states no license terms. | https://docs.kraken.com/api/docs/rest-api/get-ohlc-data ; https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data |
| Binance.com | Not read. | Not checked. | Ontario is a restricted jurisdiction under a binding 2022 OSC undertaking. Not usable if the developer is in Ontario. | n/a | https://www.binance.com/en/support/faq/aee57c04b4dd49afb85682bd1b53027c |
| Alpaca crypto | See above. | | Blocked with account. | | |

Which best represents the market: not verified by a primary source. Coinbase and Kraken are both large USD spot venues; no official volume comparison found. Coinbase USD pairs are the natural single-venue choice for BTC/USD.

## Recommendation

- Stocks: first choice Alpaca with `feed=sip`, `adjustment=all` if a Canadian can create any account and SIP bars work on the free plan (test by trying signup; costs nothing). Today that is doubtful. Fallback: Twelve Data Basic (free, adjust param, 15min, 5000 rows per call; confirm intraday depth and volume source first). Databento's $125 credit is the third option if consolidated volume proves essential.
- Crypto: Coinbase Exchange public candles. Fallback: Kraken OHLCVT CSV archive (through 2026-09-30) plus REST for recent days (about 7.5 days only, so a gap from 2026-10-01 may remain; trades endpoint not assessed).

## Not verified

- Whether Alpaca launched Canada accounts after 2026-08-14.
- Whether the free Alpaca plan really serves SIP bars older than 15 minutes (only a 2023 staff forum post).
- Alpaca T&C text on storage; current Coinbase Market Data Terms (403); Kraken API terms.
- Twelve Data free-plan intraday depth and volume feed; Tiingo and Databento equity details; Binance data terms.
- Kraken/Coinbase Quebec-specific restrictions.
