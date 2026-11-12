# Candle detector firing counts on real 15-minute bars

Throwaway measurement for issue #28 ("Final candle detector set for 15-minute bars"). Run on 2026-11-12. Branch `research/candle-detector-counts`, never merged. Only counts and rates are committed; the raw price bars are not (both data providers forbid sharing them) and live outside the repo.

## How to rerun

Needs the `agentic-jev-trader` conda env (Python 3.12, TA-Lib 0.8.3, numpy, pandas) and a Twelve Data free-plan key in an env file as `TWELVE_DATA_API_KEY`. Each command is one line and works in cmd and bash.

```
conda run -n agentic-jev-trader python docs/research/candle-detector-counts/download_bars.py <bars_dir> <env_file> all
conda run -n agentic-jev-trader python docs/research/candle-detector-counts/analyze.py <bars_dir> docs/research/candle-detector-counts/results.md
```

`<bars_dir>` must be a directory outside the repo (it must exist before the first command). Download takes about 6 minutes (36 Twelve Data requests at the free-plan rate limit, plus Binance public monthly files). `results.md` is the same text as the "Results" part below. Nothing costs money.

## Data

- Stocks SPY, AAPL, JPM, XOM: Twelve Data, 15min, regular hours, `adjust=all`, exchange local (New York) time.
- BTCUSDT: Binance public monthly 15m kline files (data.binance.vision), UTC.
- Range 2022-01-03 to 2026-04-30 only. Nothing from 2026-05-01 on was downloaded (the project's test period); `analyze.py` asserts it.
- Missing bars are never filled. Zero-volume bars are dropped (counted in the bar-count table). Each asset is one continuous series of its own existing bars, so yesterday's last stock bar is directly followed by today's first bar.

## Plain-language definitions

- **Bar / candle**: one 15-minute interval with open, high, low, close prices. Body = distance between open and close; shadows = the thin lines above and below the body.
- **Firing**: a detector says its shape is present on that bar (for a multi-bar pattern, the bar that completes it).
- **ATR(14)**: average true range over 14 bars, the typical bar-to-bar price swing. Moves are measured in ATR units so a $0.30 move in SPY and a $300 move in BTC are comparable.
- **Prior-move test (i)**: close 1 bar before the pattern's first bar is lower (decline) or higher (advance) than the close 5 bars before it. **(ii)**: that 4-bar move is at least 1.0 x ATR(14) in size.
- **Overnight straddle**: the pattern's bars are on two different trading days. **Missing-bar straddle**: the pattern's bars have a gap of more than 15 minutes between them inside a session (BTC: anywhere).
- Example of the rate columns: "3786 (13.57%)" means 3,786 firings, on 13.57% of all bars.

## Choices and guesses (read these)

- "Bars" for a pattern = the bars the TA-Lib detector looks at: 1 for doji family, spinning top, marubozu; 2 for hammer, hanging man, inverted hammer, shooting star (they test the previous bar), engulfing, harami, piercing, dark cloud; 3 for stars, three inside, three white soldiers; 4 for three black crows (needs a white bar first); 5 for rise/fall three methods.
- Prior-move first bar f: for the single-bar shapes (hammer, hanging man, inverted hammer, shooting star, doji family) f is the firing bar itself; otherwise the first of the pattern's bars. ATR is TA-Lib's Wilder ATR(14) on the continuous series. The 4-bar look-back is taken as-is, even if it crosses an overnight or a missing bar.
- "First bar of the session" = the first existing bar of that calendar date, and refers to the firing (last) bar of the pattern. Missing-bar straddles inside a stock session use a time jump over 15 minutes; overnight = the date changes.
- Positive/negative TA-Lib outputs are separate entries. Engulfing and harami include their +-80 (touching) outputs; strict +-100 engulfing is listed as extra rows.
- B "doji left out" means TA-Lib's plain `CDLDOJI` only (dragonfly and gravestone kept); a second row also removes dragonfly and gravestone. Co-fire pairs are on the firing bar; "harami" in named pairs is either direction. Rates in B skip the first 14 warm-up bars; rates in A use all bars.
- TA-Lib's doji fires on bars where high equals low; those are not removed (counts shown in the bar-count table).
- D custom detectors follow the TA-Lib C source (v0.8.3): body long = body > mean body of the previous 10 bars (measured at the bar the test applies to), short = body < that mean (the middle star bar uses <=, as TA-Lib does), upper/lower shadow "very short" = under 0.1 x mean high-low range of previous 10, shadow "long" = longer than the body, doji-like small body for hammer shapes = body < mean body. Piercing midpoint = close1 + 0.5 x body1; dark cloud the mirror. Morning/evening star third-bar close beyond close1 -/+ 0.3 x body1, third body > mean body. Colour: up means close >= open, down means close < open. As a check, every TA-Lib firing of hammer/hanging man, inverted hammer/shooting star, piercing and morning/evening star is also a firing of the matching relaxed or shape version (verified on BTC, zero exceptions).
- "morning_star_relaxed_any" still requires bar 2 to be a short body; it only drops the position condition. Bar-3 test is the same as TA-Lib.
- E tweezers: same-session pairs need two consecutive bars exactly 15 minutes apart. Overnight pairs (stocks, bar 2 is the first bar of a new date) are separate `_overnight` rows. Tolerance uses ATR(14) at bar 2. Prior-move f = bar 1.
- F: moves that cross a missing bar are always dropped. Both "excluding" and "including" overnight-crossing tables are given for stocks. Directions: spinning top and marubozu use their colour; plain doji is left out (no direction). Standard errors are naive (overlapping bars are not independent; the 4-bar rows are less reliable). F is descriptive only, not a basis for choosing patterns. For the hammer/inverted-hammer shapes, F uses them after a decline (bullish) or after an advance (bearish) under test (i).

## Results

### Bar counts

| asset | bars used | rows downloaded | zero-volume bars dropped | first bar | last bar | calendar days with bars | bars with high == low (TA-Lib doji fires on these) | missing-bar gaps inside sessions (count) |
|---|---|---|---|---|---|---|---|---|
| SPY | 27905 | 28111 | 206 | 2022-01-03 09:30:00 | 2026-04-30 15:45:00 | 1085 | 5 | 12 |
| AAPL | 27393 | 28119 | 726 | 2022-01-03 09:30:00 | 2026-04-30 15:45:00 | 1071 | 2 | 17 |
| JPM | 26994 | 28093 | 1099 | 2022-01-04 09:30:00 | 2026-04-30 15:45:00 | 1063 | 1 | 47 |
| XOM | 27019 | 28093 | 1074 | 2022-01-04 09:30:00 | 2026-04-30 15:45:00 | 1063 | 1 | 50 |
| BTCUSDT | 151574 | 151579 | 5 | 2022-01-03 00:00:00 | 2026-04-30 23:45:00 | 1579 | 0 | 1 |

## A. Firing rates (TA-Lib, default settings)

#### A. All 19 TA-Lib detectors as 25 entries (plus strict 100 engulfing rows, extra)

Firings (percent of all bars)

| entry | SPY | AAPL | JPM | XOM | BTCUSDT |
|---|---|---|---|---|---|
| doji | 3786 (13.57%) | 4063 (14.83%) | 3885 (14.39%) | 3722 (13.78%) | 19663 (12.97%) |
| dragonfly_doji | 403 (1.44%) | 493 (1.80%) | 534 (1.98%) | 524 (1.94%) | 3029 (2.00%) |
| gravestone_doji | 353 (1.27%) | 475 (1.73%) | 536 (1.99%) | 499 (1.85%) | 2748 (1.81%) |
| spinning_top_up | 3074 (11.02%) | 3023 (11.04%) | 2991 (11.08%) | 2798 (10.36%) | 14133 (9.32%) |
| spinning_top_down | 2989 (10.71%) | 2889 (10.55%) | 2596 (9.62%) | 2479 (9.18%) | 14295 (9.43%) |
| marubozu_up | 710 (2.54%) | 747 (2.73%) | 841 (3.12%) | 793 (2.93%) | 4674 (3.08%) |
| marubozu_down | 548 (1.96%) | 646 (2.36%) | 691 (2.56%) | 736 (2.72%) | 4419 (2.92%) |
| hammer | 602 (2.16%) | 751 (2.74%) | 821 (3.04%) | 826 (3.06%) | 4468 (2.95%) |
| hanging_man | 456 (1.63%) | 443 (1.62%) | 417 (1.54%) | 447 (1.65%) | 2576 (1.70%) |
| inverted_hammer | 196 (0.70%) | 183 (0.67%) | 197 (0.73%) | 183 (0.68%) | 655 (0.43%) |
| shooting_star | 238 (0.85%) | 245 (0.89%) | 301 (1.12%) | 212 (0.78%) | 755 (0.50%) |
| engulfing_bull | 1919 (6.88%) | 1954 (7.13%) | 1815 (6.72%) | 1897 (7.02%) | 14268 (9.41%) |
| engulfing_bear | 2006 (7.19%) | 1943 (7.09%) | 1901 (7.04%) | 1958 (7.25%) | 14415 (9.51%) |
| harami_bull | 901 (3.23%) | 889 (3.25%) | 866 (3.21%) | 931 (3.45%) | 7102 (4.69%) |
| harami_bear | 972 (3.48%) | 917 (3.35%) | 883 (3.27%) | 916 (3.39%) | 7258 (4.79%) |
| piercing | 11 (0.04%) | 16 (0.06%) | 22 (0.08%) | 23 (0.09%) | 4 (0.00%) |
| dark_cloud | 15 (0.05%) | 17 (0.06%) | 34 (0.13%) | 21 (0.08%) | 9 (0.01%) |
| morning_star | 109 (0.39%) | 125 (0.46%) | 114 (0.42%) | 105 (0.39%) | 385 (0.25%) |
| evening_star | 120 (0.43%) | 128 (0.47%) | 124 (0.46%) | 104 (0.38%) | 393 (0.26%) |
| three_inside_up | 135 (0.48%) | 100 (0.37%) | 96 (0.36%) | 96 (0.36%) | 455 (0.30%) |
| three_inside_down | 108 (0.39%) | 112 (0.41%) | 105 (0.39%) | 97 (0.36%) | 447 (0.29%) |
| three_white_soldiers | 33 (0.12%) | 37 (0.14%) | 38 (0.14%) | 34 (0.13%) | 180 (0.12%) |
| three_black_crows | 2 (0.01%) | 8 (0.03%) | 7 (0.03%) | 5 (0.02%) | 24 (0.02%) |
| rise_fall_3_up | 6 (0.02%) | 10 (0.04%) | 4 (0.01%) | 9 (0.03%) | 28 (0.02%) |
| rise_fall_3_down | 4 (0.01%) | 5 (0.02%) | 6 (0.02%) | 3 (0.01%) | 23 (0.02%) |
| engulfing_bull_strict100 | 1227 (4.40%) | 1336 (4.88%) | 1187 (4.40%) | 1099 (4.07%) | 4734 (3.12%) |
| engulfing_bear_strict100 | 1335 (4.78%) | 1299 (4.74%) | 1249 (4.63%) | 1106 (4.09%) | 4869 (3.21%) |

Average firings per calendar day with bars

| entry | SPY | AAPL | JPM | XOM | BTCUSDT |
|---|---|---|---|---|---|
| doji | 3.489 | 3.794 | 3.655 | 3.501 | 12.453 |
| dragonfly_doji | 0.371 | 0.460 | 0.502 | 0.493 | 1.918 |
| gravestone_doji | 0.325 | 0.444 | 0.504 | 0.469 | 1.740 |
| spinning_top_up | 2.833 | 2.823 | 2.814 | 2.632 | 8.951 |
| spinning_top_down | 2.755 | 2.697 | 2.442 | 2.332 | 9.053 |
| marubozu_up | 0.654 | 0.697 | 0.791 | 0.746 | 2.960 |
| marubozu_down | 0.505 | 0.603 | 0.650 | 0.692 | 2.799 |
| hammer | 0.555 | 0.701 | 0.772 | 0.777 | 2.830 |
| hanging_man | 0.420 | 0.414 | 0.392 | 0.421 | 1.631 |
| inverted_hammer | 0.181 | 0.171 | 0.185 | 0.172 | 0.415 |
| shooting_star | 0.219 | 0.229 | 0.283 | 0.199 | 0.478 |
| engulfing_bull | 1.769 | 1.824 | 1.707 | 1.785 | 9.036 |
| engulfing_bear | 1.849 | 1.814 | 1.788 | 1.842 | 9.129 |
| harami_bull | 0.830 | 0.830 | 0.815 | 0.876 | 4.498 |
| harami_bear | 0.896 | 0.856 | 0.831 | 0.862 | 4.597 |
| piercing | 0.010 | 0.015 | 0.021 | 0.022 | 0.003 |
| dark_cloud | 0.014 | 0.016 | 0.032 | 0.020 | 0.006 |
| morning_star | 0.100 | 0.117 | 0.107 | 0.099 | 0.244 |
| evening_star | 0.111 | 0.120 | 0.117 | 0.098 | 0.249 |
| three_inside_up | 0.124 | 0.093 | 0.090 | 0.090 | 0.288 |
| three_inside_down | 0.100 | 0.105 | 0.099 | 0.091 | 0.283 |
| three_white_soldiers | 0.030 | 0.035 | 0.036 | 0.032 | 0.114 |
| three_black_crows | 0.002 | 0.007 | 0.007 | 0.005 | 0.015 |
| rise_fall_3_up | 0.006 | 0.009 | 0.004 | 0.008 | 0.018 |
| rise_fall_3_down | 0.004 | 0.005 | 0.006 | 0.003 | 0.015 |
| engulfing_bull_strict100 | 1.131 | 1.247 | 1.117 | 1.034 | 2.998 |
| engulfing_bear_strict100 | 1.230 | 1.213 | 1.175 | 1.040 | 3.084 |

Stocks: firing bar is the first bar of the session / any other bar (the first bar is about 1 in 26 of all bars)

| entry | SPY | AAPL | JPM | XOM |
|---|---|---|---|---|
| doji | 87 first / 3699 other | 49 first / 4014 other | 42 first / 3843 other | 32 first / 3690 other |
| dragonfly_doji | 3 first / 400 other | 2 first / 491 other | 1 first / 533 other | 0 first / 524 other |
| gravestone_doji | 1 first / 352 other | 1 first / 474 other | 1 first / 535 other | 0 first / 499 other |
| spinning_top_up | 99 first / 2975 other | 63 first / 2960 other | 85 first / 2906 other | 69 first / 2729 other |
| spinning_top_down | 118 first / 2871 other | 85 first / 2804 other | 79 first / 2517 other | 70 first / 2409 other |
| marubozu_up | 16 first / 694 other | 10 first / 737 other | 6 first / 835 other | 9 first / 784 other |
| marubozu_down | 12 first / 536 other | 6 first / 640 other | 5 first / 686 other | 4 first / 732 other |
| hammer | 7 first / 595 other | 0 first / 751 other | 3 first / 818 other | 2 first / 824 other |
| hanging_man | 15 first / 441 other | 4 first / 439 other | 3 first / 414 other | 3 first / 444 other |
| inverted_hammer | 12 first / 184 other | 3 first / 180 other | 3 first / 194 other | 0 first / 183 other |
| shooting_star | 17 first / 221 other | 2 first / 243 other | 4 first / 297 other | 3 first / 209 other |
| engulfing_bull | 15 first / 1904 other | 47 first / 1907 other | 50 first / 1765 other | 39 first / 1858 other |
| engulfing_bear | 14 first / 1992 other | 50 first / 1893 other | 33 first / 1868 other | 31 first / 1927 other |
| harami_bull | 11 first / 890 other | 13 first / 876 other | 7 first / 859 other | 6 first / 925 other |
| harami_bear | 16 first / 956 other | 7 first / 910 other | 13 first / 870 other | 4 first / 912 other |
| piercing | 4 first / 7 other | 5 first / 11 other | 5 first / 17 other | 3 first / 20 other |
| dark_cloud | 5 first / 10 other | 4 first / 13 other | 6 first / 28 other | 4 first / 17 other |
| morning_star | 3 first / 106 other | 3 first / 122 other | 8 first / 106 other | 8 first / 97 other |
| evening_star | 4 first / 116 other | 8 first / 120 other | 7 first / 117 other | 6 first / 98 other |
| three_inside_up | 7 first / 128 other | 7 first / 93 other | 4 first / 92 other | 5 first / 91 other |
| three_inside_down | 5 first / 103 other | 3 first / 109 other | 12 first / 93 other | 7 first / 90 other |
| three_white_soldiers | 0 first / 33 other | 1 first / 36 other | 0 first / 38 other | 0 first / 34 other |
| three_black_crows | 0 first / 2 other | 0 first / 8 other | 0 first / 7 other | 0 first / 5 other |
| rise_fall_3_up | 2 first / 4 other | 0 first / 10 other | 0 first / 4 other | 0 first / 9 other |
| rise_fall_3_down | 0 first / 4 other | 0 first / 5 other | 1 first / 5 other | 0 first / 3 other |
| engulfing_bull_strict100 | 13 first / 1214 other | 46 first / 1290 other | 46 first / 1141 other | 37 first / 1062 other |
| engulfing_bear_strict100 | 14 first / 1321 other | 49 first / 1250 other | 32 first / 1217 other | 28 first / 1078 other |

Multi-bar entries: firings whose bars straddle an overnight boundary (stocks; share of firings and count) and the count straddling a missing bar (all assets). 'bars' = number of bars the detector looks at

| entry | bars | SPY | AAPL | JPM | XOM | BTCUSDT |
|---|---|---|---|---|---|---|
| hammer | 2 | overnight 1.2% (7); missing-bar 0 | overnight 0.0% (0); missing-bar 1 | overnight 0.4% (3); missing-bar 0 | overnight 0.2% (2); missing-bar 1 | missing-bar 0 |
| hanging_man | 2 | overnight 3.3% (15); missing-bar 3 | overnight 0.9% (4); missing-bar 3 | overnight 0.7% (3); missing-bar 5 | overnight 0.7% (3); missing-bar 3 | missing-bar 0 |
| inverted_hammer | 2 | overnight 6.1% (12); missing-bar 0 | overnight 1.6% (3); missing-bar 0 | overnight 1.5% (3); missing-bar 2 | overnight 0.0% (0); missing-bar 0 | missing-bar 0 |
| shooting_star | 2 | overnight 7.1% (17); missing-bar 0 | overnight 0.8% (2); missing-bar 0 | overnight 1.3% (4); missing-bar 1 | overnight 1.4% (3); missing-bar 1 | missing-bar 0 |
| engulfing_bull | 2 | overnight 0.8% (15); missing-bar 0 | overnight 2.4% (47); missing-bar 1 | overnight 2.8% (50); missing-bar 0 | overnight 2.1% (39); missing-bar 0 | missing-bar 0 |
| engulfing_bear | 2 | overnight 0.7% (14); missing-bar 0 | overnight 2.6% (50); missing-bar 0 | overnight 1.7% (33); missing-bar 0 | overnight 1.6% (31); missing-bar 0 | missing-bar 0 |
| harami_bull | 2 | overnight 1.2% (11); missing-bar 0 | overnight 1.5% (13); missing-bar 0 | overnight 0.8% (7); missing-bar 4 | overnight 0.6% (6); missing-bar 2 | missing-bar 0 |
| harami_bear | 2 | overnight 1.6% (16); missing-bar 0 | overnight 0.8% (7); missing-bar 0 | overnight 1.5% (13); missing-bar 0 | overnight 0.4% (4); missing-bar 0 | missing-bar 0 |
| piercing | 2 | overnight 36.4% (4); missing-bar 0 | overnight 31.2% (5); missing-bar 0 | overnight 22.7% (5); missing-bar 0 | overnight 13.0% (3); missing-bar 1 | missing-bar 0 |
| dark_cloud | 2 | overnight 33.3% (5); missing-bar 0 | overnight 23.5% (4); missing-bar 0 | overnight 17.6% (6); missing-bar 0 | overnight 19.0% (4); missing-bar 0 | missing-bar 0 |
| morning_star | 3 | overnight 2.8% (3); missing-bar 0 | overnight 3.2% (4); missing-bar 0 | overnight 8.8% (10); missing-bar 1 | overnight 9.5% (10); missing-bar 0 | missing-bar 0 |
| evening_star | 3 | overnight 9.2% (11); missing-bar 0 | overnight 7.8% (10); missing-bar 0 | overnight 8.1% (10); missing-bar 0 | overnight 8.7% (9); missing-bar 0 | missing-bar 0 |
| three_inside_up | 3 | overnight 7.4% (10); missing-bar 0 | overnight 10.0% (10); missing-bar 0 | overnight 6.2% (6); missing-bar 0 | overnight 5.2% (5); missing-bar 0 | missing-bar 0 |
| three_inside_down | 3 | overnight 5.6% (6); missing-bar 0 | overnight 3.6% (4); missing-bar 0 | overnight 16.2% (17); missing-bar 0 | overnight 8.2% (8); missing-bar 0 | missing-bar 0 |
| three_white_soldiers | 3 | overnight 0.0% (0); missing-bar 0 | overnight 2.7% (1); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | missing-bar 0 |
| three_black_crows | 4 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | missing-bar 0 |
| rise_fall_3_up | 5 | overnight 33.3% (2); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | missing-bar 0 |
| rise_fall_3_down | 5 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 16.7% (1); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | missing-bar 0 |
| engulfing_bull_strict100 | 2 | overnight 1.1% (13); missing-bar 0 | overnight 3.4% (46); missing-bar 1 | overnight 3.9% (46); missing-bar 0 | overnight 3.4% (37); missing-bar 0 | missing-bar 0 |
| engulfing_bear_strict100 | 2 | overnight 1.0% (14); missing-bar 0 | overnight 3.8% (49); missing-bar 0 | overnight 2.6% (32); missing-bar 0 | overnight 2.5% (28); missing-bar 0 | missing-bar 0 |

## B. Overlap

Percent of bars (after the first 14 warm-up bars) on which none of the listed entries fires

| entries counted | SPY | AAPL | JPM | XOM | BTCUSDT |
|---|---|---|---|---|---|
| all 25 TA-Lib entries | 51.7% | 50.6% | 50.9% | 51.6% | 47.0% |
| without doji, spinning top (both), engulfing (both), harami (both) | 86.9% | 85.3% | 84.1% | 84.5% | 85.1% |
| same, also without dragonfly and gravestone doji (whole doji family) | 88.5% | 87.3% | 86.2% | 86.7% | 87.5% |
| without engulfing at +-80 only (strict +-100 engulfing kept) | 55.7% | 54.3% | 54.7% | 56.4% | 57.0% |

Top 15 pairs of entries firing on the same bar, ranked by the four stocks pooled (counts of bars). Pairs where one entry is a special case of the other (doji with dragonfly doji) are expected at the top.

| pair | stocks pooled | SPY | AAPL | JPM | XOM | BTCUSDT |
|---|---|---|---|---|---|---|
| doji + spinning_top_up | 7310 | 1804 | 1856 | 1883 | 1767 | 8093 |
| doji + spinning_top_down | 6309 | 1647 | 1746 | 1482 | 1434 | 8076 |
| doji + dragonfly_doji | 1954 | 403 | 493 | 534 | 524 | 3029 |
| doji + gravestone_doji | 1863 | 353 | 475 | 536 | 499 | 2748 |
| spinning_top_up + harami_bull | 1322 | 346 | 330 | 311 | 335 | 2323 |
| spinning_top_down + harami_bear | 1232 | 378 | 326 | 274 | 254 | 2399 |
| doji + harami_bear | 981 | 252 | 258 | 242 | 229 | 1511 |
| doji + harami_bull | 938 | 221 | 226 | 245 | 246 | 1405 |
| marubozu_up + engulfing_bull | 746 | 142 | 198 | 202 | 204 | 1674 |
| marubozu_down + engulfing_bear | 741 | 170 | 176 | 193 | 202 | 1602 |
| doji + hanging_man | 645 | 149 | 156 | 174 | 166 | 1019 |
| dragonfly_doji + hanging_man | 643 | 149 | 156 | 173 | 165 | 996 |
| doji + hammer | 570 | 86 | 142 | 176 | 166 | 884 |
| dragonfly_doji + hammer | 568 | 85 | 142 | 175 | 166 | 866 |
| dragonfly_doji + spinning_top_up | 557 | 109 | 143 | 143 | 162 | 694 |

Top 15 pairs for BTCUSDT

| pair | BTCUSDT | stocks pooled |
|---|---|---|
| doji + spinning_top_up | 8093 | 7310 |
| doji + spinning_top_down | 8076 | 6309 |
| doji + dragonfly_doji | 3029 | 1954 |
| doji + gravestone_doji | 2748 | 1863 |
| spinning_top_down + harami_bear | 2399 | 1232 |
| spinning_top_up + harami_bull | 2323 | 1322 |
| marubozu_up + engulfing_bull | 1674 | 746 |
| marubozu_down + engulfing_bear | 1602 | 741 |
| doji + harami_bear | 1511 | 981 |
| doji + harami_bull | 1405 | 938 |
| doji + hanging_man | 1019 | 645 |
| dragonfly_doji + hanging_man | 996 | 643 |
| doji + hammer | 884 | 570 |
| dragonfly_doji + hammer | 866 | 568 |
| dragonfly_doji + spinning_top_up | 694 | 557 |

Named pairs: bars where both fire (of: firings of the first / of the second)

| pair | SPY | AAPL | JPM | XOM | BTCUSDT |
|---|---|---|---|---|---|
| doji + dragonfly_doji | 403 (of 3786 / 403) | 493 (of 4063 / 493) | 534 (of 3885 / 534) | 524 (of 3722 / 524) | 3029 (of 19663 / 3029) |
| doji + gravestone_doji | 353 (of 3786 / 353) | 475 (of 4063 / 475) | 536 (of 3885 / 536) | 499 (of 3722 / 499) | 2748 (of 19663 / 2748) |
| doji + harami (either direction) | 473 (of 3786 / 1873) | 484 (of 4063 / 1806) | 487 (of 3885 / 1749) | 475 (of 3722 / 1847) | 2916 (of 19663 / 14360) |
| hammer + dragonfly_doji | 85 (of 602 / 403) | 142 (of 751 / 493) | 175 (of 821 / 534) | 166 (of 826 / 524) | 866 (of 4468 / 3029) |
| engulfing (either) + three_inside (either) | 5 (of 3925 / 243) | 0 (of 3897 / 212) | 7 (of 3716 / 201) | 4 (of 3855 / 193) | 0 (of 28683 / 902) |
| engulfing_bull + piercing | 0 (of 1919 / 11) | 0 (of 1954 / 16) | 0 (of 1815 / 22) | 0 (of 1897 / 23) | 0 (of 14268 / 4) |
| engulfing_bear + dark_cloud | 0 (of 2006 / 15) | 0 (of 1943 / 17) | 0 (of 1901 / 34) | 0 (of 1958 / 21) | 0 (of 14415 / 9) |
| engulfing (either) + piercing or dark_cloud | 0 (of 3925 / 26) | 0 (of 3897 / 33) | 0 (of 3716 / 56) | 0 (of 3855 / 44) | 0 (of 28683 / 13) |

## C. Prior-move filter

#### Baseline

| share of ALL bars satisfying | SPY | AAPL | JPM | XOM | BTCUSDT |
|---|---|---|---|---|---|
| decline (i) | 46.5% | 48.7% | 46.9% | 47.7% | 49.4% |
| decline (ii) | 19.5% | 19.1% | 19.0% | 19.2% | 18.1% |
| advance (i) | 53.3% | 51.1% | 52.6% | 51.8% | 50.6% |
| advance (ii) | 22.1% | 20.3% | 21.2% | 21.1% | 18.6% |

#### C. TA-Lib reversal entries

Cells: firings, then how many (percent of firings) survive prior-move test (i) = close[f-1] vs close[f-5], and (ii) = move of at least 1.0 x ATR(14) at f-1. Bearish entries need a prior advance, bullish a prior decline. Rows marked 'after decline'/'after advance' belong to shape entries with no direction of their own.

| entry | SPY | AAPL | JPM | XOM | BTCUSDT |
|---|---|---|---|---|---|
| dragonfly_doji | 403: (i) 161 (40.0%), (ii) 56 (13.9%) | 493: (i) 232 (47.1%), (ii) 77 (15.6%) | 534: (i) 248 (46.4%), (ii) 72 (13.5%) | 524: (i) 251 (47.9%), (ii) 85 (16.2%) | 3029: (i) 1352 (44.6%), (ii) 357 (11.8%) |
| gravestone_doji | 353: (i) 220 (62.3%), (ii) 90 (25.5%) | 475: (i) 236 (49.7%), (ii) 86 (18.1%) | 536: (i) 310 (57.8%), (ii) 103 (19.2%) | 499: (i) 243 (48.7%), (ii) 87 (17.4%) | 2748: (i) 1375 (50.0%), (ii) 409 (14.9%) |
| hammer | 602: (i) 347 (57.6%), (ii) 157 (26.1%) | 751: (i) 446 (59.4%), (ii) 179 (23.8%) | 821: (i) 472 (57.5%), (ii) 198 (24.1%) | 826: (i) 498 (60.3%), (ii) 203 (24.6%) | 4468: (i) 2477 (55.4%), (ii) 809 (18.1%) |
| hanging_man | 456: (i) 318 (69.7%), (ii) 158 (34.6%) | 443: (i) 298 (67.3%), (ii) 136 (30.7%) | 417: (i) 282 (67.6%), (ii) 133 (31.9%) | 447: (i) 313 (70.0%), (ii) 150 (33.6%) | 2576: (i) 1565 (60.8%), (ii) 552 (21.4%) |
| inverted_hammer | 196: (i) 113 (57.7%), (ii) 59 (30.1%) | 183: (i) 136 (74.3%), (ii) 65 (35.5%) | 197: (i) 125 (63.5%), (ii) 50 (25.4%) | 183: (i) 113 (61.7%), (ii) 54 (29.5%) | 655: (i) 385 (58.8%), (ii) 125 (19.1%) |
| shooting_star | 238: (i) 176 (73.9%), (ii) 75 (31.5%) | 245: (i) 159 (64.9%), (ii) 87 (35.5%) | 301: (i) 202 (67.1%), (ii) 93 (30.9%) | 212: (i) 133 (62.7%), (ii) 65 (30.7%) | 755: (i) 446 (59.1%), (ii) 158 (20.9%) |
| engulfing_bull | 1919: (i) 959 (50.0%), (ii) 389 (20.3%) | 1954: (i) 939 (48.1%), (ii) 339 (17.3%) | 1815: (i) 877 (48.3%), (ii) 347 (19.1%) | 1897: (i) 938 (49.4%), (ii) 376 (19.8%) | 14268: (i) 7006 (49.1%), (ii) 2557 (17.9%) |
| engulfing_bear | 2006: (i) 1101 (54.9%), (ii) 471 (23.5%) | 1943: (i) 1029 (53.0%), (ii) 415 (21.4%) | 1901: (i) 1042 (54.8%), (ii) 425 (22.4%) | 1958: (i) 1019 (52.0%), (ii) 420 (21.5%) | 14415: (i) 7358 (51.0%), (ii) 2645 (18.3%) |
| harami_bull | 901: (i) 424 (47.1%), (ii) 182 (20.2%) | 889: (i) 435 (48.9%), (ii) 182 (20.5%) | 866: (i) 427 (49.3%), (ii) 172 (19.9%) | 931: (i) 432 (46.4%), (ii) 178 (19.1%) | 7102: (i) 3392 (47.8%), (ii) 1204 (17.0%) |
| harami_bear | 972: (i) 488 (50.2%), (ii) 200 (20.6%) | 917: (i) 475 (51.8%), (ii) 175 (19.1%) | 883: (i) 439 (49.7%), (ii) 170 (19.3%) | 916: (i) 473 (51.6%), (ii) 202 (22.1%) | 7258: (i) 3515 (48.4%), (ii) 1244 (17.1%) |
| piercing | 11: (i) 7 (63.6%), (ii) 6 (54.5%) | 16: (i) 8 (50.0%), (ii) 6 (37.5%) | 22: (i) 7 (31.8%), (ii) 1 (4.5%) | 23: (i) 16 (69.6%), (ii) 8 (34.8%) | 4: (i) 2 (50.0%), (ii) 0 (0.0%) |
| dark_cloud | 15: (i) 11 (73.3%), (ii) 5 (33.3%) | 17: (i) 8 (47.1%), (ii) 1 (5.9%) | 34: (i) 15 (44.1%), (ii) 6 (17.6%) | 21: (i) 10 (47.6%), (ii) 3 (14.3%) | 9: (i) 6 (66.7%), (ii) 3 (33.3%) |
| morning_star | 109: (i) 58 (53.2%), (ii) 29 (26.6%) | 125: (i) 60 (48.0%), (ii) 26 (20.8%) | 114: (i) 58 (50.9%), (ii) 17 (14.9%) | 105: (i) 43 (41.0%), (ii) 19 (18.1%) | 385: (i) 180 (46.8%), (ii) 57 (14.8%) |
| evening_star | 120: (i) 58 (48.3%), (ii) 22 (18.3%) | 128: (i) 53 (41.4%), (ii) 21 (16.4%) | 124: (i) 66 (53.2%), (ii) 34 (27.4%) | 104: (i) 53 (51.0%), (ii) 22 (21.2%) | 393: (i) 182 (46.3%), (ii) 65 (16.5%) |
| three_inside_up | 135: (i) 63 (46.7%), (ii) 27 (20.0%) | 100: (i) 47 (47.0%), (ii) 18 (18.0%) | 96: (i) 41 (42.7%), (ii) 17 (17.7%) | 96: (i) 42 (43.8%), (ii) 20 (20.8%) | 455: (i) 249 (54.7%), (ii) 79 (17.4%) |
| three_inside_down | 108: (i) 54 (50.0%), (ii) 18 (16.7%) | 112: (i) 50 (44.6%), (ii) 23 (20.5%) | 105: (i) 52 (49.5%), (ii) 26 (24.8%) | 97: (i) 54 (55.7%), (ii) 25 (25.8%) | 447: (i) 237 (53.0%), (ii) 93 (20.8%) |

## D. Relaxed versions and shapes without the gap or previous-bar test

#### D. Same breakdown as A

Firings (percent of all bars)

| entry | SPY | AAPL | JPM | XOM | BTCUSDT |
|---|---|---|---|---|---|
| piercing_relaxed | 290 (1.04%) | 243 (0.89%) | 274 (1.02%) | 279 (1.03%) | 2226 (1.47%) |
| dark_cloud_relaxed | 240 (0.86%) | 244 (0.89%) | 279 (1.03%) | 254 (0.94%) | 2071 (1.37%) |
| morning_star_relaxed_touch | 167 (0.60%) | 166 (0.61%) | 154 (0.57%) | 168 (0.62%) | 1158 (0.76%) |
| morning_star_relaxed_any | 634 (2.27%) | 561 (2.05%) | 558 (2.07%) | 535 (1.98%) | 3464 (2.29%) |
| evening_star_relaxed_touch | 175 (0.63%) | 166 (0.61%) | 169 (0.63%) | 168 (0.62%) | 1129 (0.74%) |
| evening_star_relaxed_any | 570 (2.04%) | 581 (2.12%) | 519 (1.92%) | 519 (1.92%) | 3494 (2.31%) |
| hammer_shape_no_prev_test | 1929 (6.91%) | 2051 (7.49%) | 2040 (7.56%) | 2096 (7.76%) | 12266 (8.09%) |
| inverted_hammer_shape_no_gap | 1665 (5.97%) | 1874 (6.84%) | 2037 (7.55%) | 1949 (7.21%) | 11294 (7.45%) |

Average firings per calendar day with bars

| entry | SPY | AAPL | JPM | XOM | BTCUSDT |
|---|---|---|---|---|---|
| piercing_relaxed | 0.267 | 0.227 | 0.258 | 0.262 | 1.410 |
| dark_cloud_relaxed | 0.221 | 0.228 | 0.262 | 0.239 | 1.312 |
| morning_star_relaxed_touch | 0.154 | 0.155 | 0.145 | 0.158 | 0.733 |
| morning_star_relaxed_any | 0.584 | 0.524 | 0.525 | 0.503 | 2.194 |
| evening_star_relaxed_touch | 0.161 | 0.155 | 0.159 | 0.158 | 0.715 |
| evening_star_relaxed_any | 0.525 | 0.542 | 0.488 | 0.488 | 2.213 |
| hammer_shape_no_prev_test | 1.778 | 1.915 | 1.919 | 1.972 | 7.768 |
| inverted_hammer_shape_no_gap | 1.535 | 1.750 | 1.916 | 1.833 | 7.153 |

Stocks: firing bar is the first bar of the session / any other bar (the first bar is about 1 in 26 of all bars)

| entry | SPY | AAPL | JPM | XOM |
|---|---|---|---|---|
| piercing_relaxed | 7 first / 283 other | 6 first / 237 other | 5 first / 269 other | 6 first / 273 other |
| dark_cloud_relaxed | 8 first / 232 other | 8 first / 236 other | 6 first / 273 other | 6 first / 248 other |
| morning_star_relaxed_touch | 5 first / 162 other | 7 first / 159 other | 11 first / 143 other | 11 first / 157 other |
| morning_star_relaxed_any | 16 first / 618 other | 22 first / 539 other | 36 first / 522 other | 28 first / 507 other |
| evening_star_relaxed_touch | 6 first / 169 other | 11 first / 155 other | 14 first / 155 other | 12 first / 156 other |
| evening_star_relaxed_any | 15 first / 555 other | 29 first / 552 other | 35 first / 484 other | 35 first / 484 other |
| hammer_shape_no_prev_test | 26 first / 1903 other | 5 first / 2046 other | 8 first / 2032 other | 5 first / 2091 other |
| inverted_hammer_shape_no_gap | 35 first / 1630 other | 6 first / 1868 other | 9 first / 2028 other | 3 first / 1946 other |

Multi-bar entries: firings whose bars straddle an overnight boundary (stocks; share of firings and count) and the count straddling a missing bar (all assets). 'bars' = number of bars the detector looks at

| entry | bars | SPY | AAPL | JPM | XOM | BTCUSDT |
|---|---|---|---|---|---|---|
| piercing_relaxed | 2 | overnight 2.4% (7); missing-bar 0 | overnight 2.5% (6); missing-bar 0 | overnight 1.8% (5); missing-bar 0 | overnight 2.2% (6); missing-bar 1 | missing-bar 0 |
| dark_cloud_relaxed | 2 | overnight 3.3% (8); missing-bar 1 | overnight 3.3% (8); missing-bar 0 | overnight 2.2% (6); missing-bar 0 | overnight 2.4% (6); missing-bar 0 | missing-bar 0 |
| morning_star_relaxed_touch | 3 | overnight 3.0% (5); missing-bar 0 | overnight 4.8% (8); missing-bar 0 | overnight 8.4% (13); missing-bar 1 | overnight 7.7% (13); missing-bar 0 | missing-bar 0 |
| morning_star_relaxed_any | 3 | overnight 5.2% (33); missing-bar 0 | overnight 6.2% (35); missing-bar 0 | overnight 8.4% (47); missing-bar 2 | overnight 7.3% (39); missing-bar 1 | missing-bar 0 |
| evening_star_relaxed_touch | 3 | overnight 7.4% (13); missing-bar 0 | overnight 7.8% (13); missing-bar 0 | overnight 10.1% (17); missing-bar 0 | overnight 8.9% (15); missing-bar 0 | missing-bar 0 |
| evening_star_relaxed_any | 3 | overnight 6.3% (36); missing-bar 0 | overnight 7.1% (41); missing-bar 0 | overnight 10.2% (53); missing-bar 0 | overnight 8.7% (45); missing-bar 0 | missing-bar 0 |

#### D. Prior-move survival (same as C)

Cells: firings, then how many (percent of firings) survive prior-move test (i) = close[f-1] vs close[f-5], and (ii) = move of at least 1.0 x ATR(14) at f-1. Bearish entries need a prior advance, bullish a prior decline. Rows marked 'after decline'/'after advance' belong to shape entries with no direction of their own.

| entry | SPY | AAPL | JPM | XOM | BTCUSDT |
|---|---|---|---|---|---|
| piercing_relaxed | 290: (i) 128 (44.1%), (ii) 53 (18.3%) | 243: (i) 113 (46.5%), (ii) 50 (20.6%) | 274: (i) 136 (49.6%), (ii) 64 (23.4%) | 279: (i) 155 (55.6%), (ii) 66 (23.7%) | 2226: (i) 1218 (54.7%), (ii) 474 (21.3%) |
| dark_cloud_relaxed | 240: (i) 127 (52.9%), (ii) 63 (26.2%) | 244: (i) 125 (51.2%), (ii) 51 (20.9%) | 279: (i) 141 (50.5%), (ii) 60 (21.5%) | 254: (i) 134 (52.8%), (ii) 55 (21.7%) | 2071: (i) 1114 (53.8%), (ii) 451 (21.8%) |
| morning_star_relaxed_touch | 167: (i) 89 (53.3%), (ii) 43 (25.7%) | 166: (i) 78 (47.0%), (ii) 31 (18.7%) | 154: (i) 85 (55.2%), (ii) 27 (17.5%) | 168: (i) 77 (45.8%), (ii) 33 (19.6%) | 1158: (i) 554 (47.8%), (ii) 203 (17.5%) |
| morning_star_relaxed_any | 634: (i) 335 (52.8%), (ii) 153 (24.1%) | 561: (i) 253 (45.1%), (ii) 101 (18.0%) | 558: (i) 284 (50.9%), (ii) 99 (17.7%) | 535: (i) 243 (45.4%), (ii) 101 (18.9%) | 3464: (i) 1717 (49.6%), (ii) 604 (17.4%) |
| evening_star_relaxed_touch | 175: (i) 88 (50.3%), (ii) 40 (22.9%) | 166: (i) 74 (44.6%), (ii) 27 (16.3%) | 169: (i) 90 (53.3%), (ii) 42 (24.9%) | 168: (i) 84 (50.0%), (ii) 32 (19.0%) | 1129: (i) 524 (46.4%), (ii) 194 (17.2%) |
| evening_star_relaxed_any | 570: (i) 269 (47.2%), (ii) 107 (18.8%) | 581: (i) 288 (49.6%), (ii) 117 (20.1%) | 519: (i) 259 (49.9%), (ii) 118 (22.7%) | 519: (i) 259 (49.9%), (ii) 106 (20.4%) | 3494: (i) 1702 (48.7%), (ii) 621 (17.8%) |
| hammer_shape_no_prev_test after decline | 1929: (i) 864 (44.8%), (ii) 332 (17.2%) | 2051: (i) 959 (46.8%), (ii) 341 (16.6%) | 2040: (i) 935 (45.8%), (ii) 334 (16.4%) | 2096: (i) 977 (46.6%), (ii) 357 (17.0%) | 12266: (i) 6023 (49.1%), (ii) 1921 (15.7%) |
| hammer_shape_no_prev_test after advance | 1929: (i) 1062 (55.1%), (ii) 434 (22.5%) | 2051: (i) 1091 (53.2%), (ii) 414 (20.2%) | 2040: (i) 1102 (54.0%), (ii) 413 (20.2%) | 2096: (i) 1108 (52.9%), (ii) 426 (20.3%) | 12266: (i) 6243 (50.9%), (ii) 2061 (16.8%) |
| inverted_hammer_shape_no_gap after decline | 1665: (i) 714 (42.9%), (ii) 283 (17.0%) | 1874: (i) 915 (48.8%), (ii) 358 (19.1%) | 2037: (i) 906 (44.5%), (ii) 339 (16.6%) | 1949: (i) 952 (48.8%), (ii) 373 (19.1%) | 11294: (i) 5332 (47.2%), (ii) 1667 (14.8%) |
| inverted_hammer_shape_no_gap after advance | 1665: (i) 949 (57.0%), (ii) 395 (23.7%) | 1874: (i) 952 (50.8%), (ii) 386 (20.6%) | 2037: (i) 1123 (55.1%), (ii) 431 (21.2%) | 1949: (i) 984 (50.5%), (ii) 358 (18.4%) | 11294: (i) 5962 (52.8%), (ii) 2030 (18.0%) |

## E. Tweezers

Entries without the suffix are two bars in the same session with no missing bar between (for BTC: consecutive bars). Entries ending `_overnight` (stocks only) are pairs where bar 2 is the first bar of a new day. Variant a = no colour test, b = colour test. Tolerance is a multiple of ATR(14) at bar 2.

#### E. Tweezer counts

Firings (percent of all bars)

| entry | SPY | AAPL | JPM | XOM | BTCUSDT |
|---|---|---|---|---|---|
| tweezer_bottom_a_tol0.05 | 2427 (8.70%) | 2502 (9.13%) | 2551 (9.45%) | 2581 (9.55%) | 14665 (9.68%) |
| tweezer_bottom_b_tol0.05 | 1214 (4.35%) | 1207 (4.41%) | 1201 (4.45%) | 1209 (4.47%) | 7649 (5.05%) |
| tweezer_top_a_tol0.05 | 2786 (9.98%) | 2767 (10.10%) | 2596 (9.62%) | 2706 (10.02%) | 15423 (10.18%) |
| tweezer_top_b_tol0.05 | 1386 (4.97%) | 1322 (4.83%) | 1195 (4.43%) | 1319 (4.88%) | 7968 (5.26%) |
| tweezer_bottom_a_tol0.05_overnight | 14 (0.05%) | 21 (0.08%) | 24 (0.09%) | 14 (0.05%) | n/a |
| tweezer_bottom_b_tol0.05_overnight | 4 (0.01%) | 5 (0.02%) | 4 (0.01%) | 4 (0.01%) | n/a |
| tweezer_top_a_tol0.05_overnight | 24 (0.09%) | 19 (0.07%) | 22 (0.08%) | 18 (0.07%) | n/a |
| tweezer_top_b_tol0.05_overnight | 9 (0.03%) | 4 (0.01%) | 10 (0.04%) | 3 (0.01%) | n/a |
| tweezer_bottom_a_tol0.10 | 4791 (17.17%) | 5033 (18.37%) | 5007 (18.55%) | 4995 (18.49%) | 27648 (18.24%) |
| tweezer_bottom_b_tol0.10 | 2231 (7.99%) | 2312 (8.44%) | 2288 (8.48%) | 2280 (8.44%) | 13552 (8.94%) |
| tweezer_top_a_tol0.10 | 5357 (19.20%) | 5441 (19.86%) | 5079 (18.82%) | 5255 (19.45%) | 29027 (19.15%) |
| tweezer_top_b_tol0.10 | 2558 (9.17%) | 2478 (9.05%) | 2298 (8.51%) | 2449 (9.06%) | 14125 (9.32%) |
| tweezer_bottom_a_tol0.10_overnight | 32 (0.11%) | 39 (0.14%) | 50 (0.19%) | 28 (0.10%) | n/a |
| tweezer_bottom_b_tol0.10_overnight | 9 (0.03%) | 9 (0.03%) | 9 (0.03%) | 12 (0.04%) | n/a |
| tweezer_top_a_tol0.10_overnight | 39 (0.14%) | 31 (0.11%) | 39 (0.14%) | 29 (0.11%) | n/a |
| tweezer_top_b_tol0.10_overnight | 13 (0.05%) | 8 (0.03%) | 13 (0.05%) | 9 (0.03%) | n/a |
| tweezer_bottom_a_tol0.20 | 9282 (33.26%) | 9490 (34.64%) | 9375 (34.73%) | 9301 (34.42%) | 51386 (33.90%) |
| tweezer_bottom_b_tol0.20 | 3928 (14.08%) | 4048 (14.78%) | 3914 (14.50%) | 3864 (14.30%) | 22565 (14.89%) |
| tweezer_top_a_tol0.20 | 10176 (36.47%) | 9990 (36.47%) | 9654 (35.76%) | 9723 (35.99%) | 53404 (35.23%) |
| tweezer_top_b_tol0.20 | 4302 (15.42%) | 4209 (15.37%) | 4018 (14.88%) | 4138 (15.32%) | 23569 (15.55%) |
| tweezer_bottom_a_tol0.20_overnight | 61 (0.22%) | 87 (0.32%) | 78 (0.29%) | 60 (0.22%) | n/a |
| tweezer_bottom_b_tol0.20_overnight | 15 (0.05%) | 18 (0.07%) | 15 (0.06%) | 23 (0.09%) | n/a |
| tweezer_top_a_tol0.20_overnight | 70 (0.25%) | 65 (0.24%) | 77 (0.29%) | 52 (0.19%) | n/a |
| tweezer_top_b_tol0.20_overnight | 18 (0.06%) | 18 (0.07%) | 25 (0.09%) | 19 (0.07%) | n/a |

Average firings per calendar day with bars

| entry | SPY | AAPL | JPM | XOM | BTCUSDT |
|---|---|---|---|---|---|
| tweezer_bottom_a_tol0.05 | 2.237 | 2.336 | 2.400 | 2.428 | 9.288 |
| tweezer_bottom_b_tol0.05 | 1.119 | 1.127 | 1.130 | 1.137 | 4.844 |
| tweezer_top_a_tol0.05 | 2.568 | 2.584 | 2.442 | 2.546 | 9.768 |
| tweezer_top_b_tol0.05 | 1.277 | 1.234 | 1.124 | 1.241 | 5.046 |
| tweezer_bottom_a_tol0.05_overnight | 0.013 | 0.020 | 0.023 | 0.013 | n/a |
| tweezer_bottom_b_tol0.05_overnight | 0.004 | 0.005 | 0.004 | 0.004 | n/a |
| tweezer_top_a_tol0.05_overnight | 0.022 | 0.018 | 0.021 | 0.017 | n/a |
| tweezer_top_b_tol0.05_overnight | 0.008 | 0.004 | 0.009 | 0.003 | n/a |
| tweezer_bottom_a_tol0.10 | 4.416 | 4.699 | 4.710 | 4.699 | 17.510 |
| tweezer_bottom_b_tol0.10 | 2.056 | 2.159 | 2.152 | 2.145 | 8.583 |
| tweezer_top_a_tol0.10 | 4.937 | 5.080 | 4.778 | 4.944 | 18.383 |
| tweezer_top_b_tol0.10 | 2.358 | 2.314 | 2.162 | 2.304 | 8.946 |
| tweezer_bottom_a_tol0.10_overnight | 0.029 | 0.036 | 0.047 | 0.026 | n/a |
| tweezer_bottom_b_tol0.10_overnight | 0.008 | 0.008 | 0.008 | 0.011 | n/a |
| tweezer_top_a_tol0.10_overnight | 0.036 | 0.029 | 0.037 | 0.027 | n/a |
| tweezer_top_b_tol0.10_overnight | 0.012 | 0.007 | 0.012 | 0.008 | n/a |
| tweezer_bottom_a_tol0.20 | 8.555 | 8.861 | 8.819 | 8.750 | 32.543 |
| tweezer_bottom_b_tol0.20 | 3.620 | 3.780 | 3.682 | 3.635 | 14.291 |
| tweezer_top_a_tol0.20 | 9.379 | 9.328 | 9.082 | 9.147 | 33.821 |
| tweezer_top_b_tol0.20 | 3.965 | 3.930 | 3.780 | 3.893 | 14.927 |
| tweezer_bottom_a_tol0.20_overnight | 0.056 | 0.081 | 0.073 | 0.056 | n/a |
| tweezer_bottom_b_tol0.20_overnight | 0.014 | 0.017 | 0.014 | 0.022 | n/a |
| tweezer_top_a_tol0.20_overnight | 0.065 | 0.061 | 0.072 | 0.049 | n/a |
| tweezer_top_b_tol0.20_overnight | 0.017 | 0.017 | 0.024 | 0.018 | n/a |

Stocks: firing bar is the first bar of the session / any other bar (the first bar is about 1 in 26 of all bars)

| entry | SPY | AAPL | JPM | XOM |
|---|---|---|---|---|
| tweezer_bottom_a_tol0.05 | 0 first / 2427 other | 0 first / 2502 other | 0 first / 2551 other | 0 first / 2581 other |
| tweezer_bottom_b_tol0.05 | 0 first / 1214 other | 0 first / 1207 other | 0 first / 1201 other | 0 first / 1209 other |
| tweezer_top_a_tol0.05 | 0 first / 2786 other | 0 first / 2767 other | 0 first / 2596 other | 0 first / 2706 other |
| tweezer_top_b_tol0.05 | 0 first / 1386 other | 0 first / 1322 other | 0 first / 1195 other | 0 first / 1319 other |
| tweezer_bottom_a_tol0.05_overnight | 14 first / 0 other | 21 first / 0 other | 24 first / 0 other | 14 first / 0 other |
| tweezer_bottom_b_tol0.05_overnight | 4 first / 0 other | 5 first / 0 other | 4 first / 0 other | 4 first / 0 other |
| tweezer_top_a_tol0.05_overnight | 24 first / 0 other | 19 first / 0 other | 22 first / 0 other | 18 first / 0 other |
| tweezer_top_b_tol0.05_overnight | 9 first / 0 other | 4 first / 0 other | 10 first / 0 other | 3 first / 0 other |
| tweezer_bottom_a_tol0.10 | 0 first / 4791 other | 0 first / 5033 other | 0 first / 5007 other | 0 first / 4995 other |
| tweezer_bottom_b_tol0.10 | 0 first / 2231 other | 0 first / 2312 other | 0 first / 2288 other | 0 first / 2280 other |
| tweezer_top_a_tol0.10 | 0 first / 5357 other | 0 first / 5441 other | 0 first / 5079 other | 0 first / 5255 other |
| tweezer_top_b_tol0.10 | 0 first / 2558 other | 0 first / 2478 other | 0 first / 2298 other | 0 first / 2449 other |
| tweezer_bottom_a_tol0.10_overnight | 32 first / 0 other | 39 first / 0 other | 50 first / 0 other | 28 first / 0 other |
| tweezer_bottom_b_tol0.10_overnight | 9 first / 0 other | 9 first / 0 other | 9 first / 0 other | 12 first / 0 other |
| tweezer_top_a_tol0.10_overnight | 39 first / 0 other | 31 first / 0 other | 39 first / 0 other | 29 first / 0 other |
| tweezer_top_b_tol0.10_overnight | 13 first / 0 other | 8 first / 0 other | 13 first / 0 other | 9 first / 0 other |
| tweezer_bottom_a_tol0.20 | 0 first / 9282 other | 0 first / 9490 other | 0 first / 9375 other | 0 first / 9301 other |
| tweezer_bottom_b_tol0.20 | 0 first / 3928 other | 0 first / 4048 other | 0 first / 3914 other | 0 first / 3864 other |
| tweezer_top_a_tol0.20 | 0 first / 10176 other | 0 first / 9990 other | 0 first / 9654 other | 0 first / 9723 other |
| tweezer_top_b_tol0.20 | 0 first / 4302 other | 0 first / 4209 other | 0 first / 4018 other | 0 first / 4138 other |
| tweezer_bottom_a_tol0.20_overnight | 61 first / 0 other | 87 first / 0 other | 78 first / 0 other | 60 first / 0 other |
| tweezer_bottom_b_tol0.20_overnight | 15 first / 0 other | 18 first / 0 other | 15 first / 0 other | 23 first / 0 other |
| tweezer_top_a_tol0.20_overnight | 70 first / 0 other | 65 first / 0 other | 77 first / 0 other | 52 first / 0 other |
| tweezer_top_b_tol0.20_overnight | 18 first / 0 other | 18 first / 0 other | 25 first / 0 other | 19 first / 0 other |

Multi-bar entries: firings whose bars straddle an overnight boundary (stocks; share of firings and count) and the count straddling a missing bar (all assets). 'bars' = number of bars the detector looks at

| entry | bars | SPY | AAPL | JPM | XOM | BTCUSDT |
|---|---|---|---|---|---|---|
| tweezer_bottom_a_tol0.05 | 2 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | missing-bar 0 |
| tweezer_bottom_b_tol0.05 | 2 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | missing-bar 0 |
| tweezer_top_a_tol0.05 | 2 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | missing-bar 0 |
| tweezer_top_b_tol0.05 | 2 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | missing-bar 0 |
| tweezer_bottom_a_tol0.05_overnight | 2 | overnight 100.0% (14); missing-bar 0 | overnight 100.0% (21); missing-bar 0 | overnight 100.0% (24); missing-bar 0 | overnight 100.0% (14); missing-bar 0 | n/a |
| tweezer_bottom_b_tol0.05_overnight | 2 | overnight 100.0% (4); missing-bar 0 | overnight 100.0% (5); missing-bar 0 | overnight 100.0% (4); missing-bar 0 | overnight 100.0% (4); missing-bar 0 | n/a |
| tweezer_top_a_tol0.05_overnight | 2 | overnight 100.0% (24); missing-bar 0 | overnight 100.0% (19); missing-bar 0 | overnight 100.0% (22); missing-bar 0 | overnight 100.0% (18); missing-bar 0 | n/a |
| tweezer_top_b_tol0.05_overnight | 2 | overnight 100.0% (9); missing-bar 0 | overnight 100.0% (4); missing-bar 0 | overnight 100.0% (10); missing-bar 0 | overnight 100.0% (3); missing-bar 0 | n/a |
| tweezer_bottom_a_tol0.10 | 2 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | missing-bar 0 |
| tweezer_bottom_b_tol0.10 | 2 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | missing-bar 0 |
| tweezer_top_a_tol0.10 | 2 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | missing-bar 0 |
| tweezer_top_b_tol0.10 | 2 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | missing-bar 0 |
| tweezer_bottom_a_tol0.10_overnight | 2 | overnight 100.0% (32); missing-bar 0 | overnight 100.0% (39); missing-bar 0 | overnight 100.0% (50); missing-bar 0 | overnight 100.0% (28); missing-bar 0 | n/a |
| tweezer_bottom_b_tol0.10_overnight | 2 | overnight 100.0% (9); missing-bar 0 | overnight 100.0% (9); missing-bar 0 | overnight 100.0% (9); missing-bar 0 | overnight 100.0% (12); missing-bar 0 | n/a |
| tweezer_top_a_tol0.10_overnight | 2 | overnight 100.0% (39); missing-bar 0 | overnight 100.0% (31); missing-bar 0 | overnight 100.0% (39); missing-bar 0 | overnight 100.0% (29); missing-bar 0 | n/a |
| tweezer_top_b_tol0.10_overnight | 2 | overnight 100.0% (13); missing-bar 0 | overnight 100.0% (8); missing-bar 0 | overnight 100.0% (13); missing-bar 0 | overnight 100.0% (9); missing-bar 0 | n/a |
| tweezer_bottom_a_tol0.20 | 2 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | missing-bar 0 |
| tweezer_bottom_b_tol0.20 | 2 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | missing-bar 0 |
| tweezer_top_a_tol0.20 | 2 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | missing-bar 0 |
| tweezer_top_b_tol0.20 | 2 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | overnight 0.0% (0); missing-bar 0 | missing-bar 0 |
| tweezer_bottom_a_tol0.20_overnight | 2 | overnight 100.0% (61); missing-bar 0 | overnight 100.0% (87); missing-bar 0 | overnight 100.0% (78); missing-bar 0 | overnight 100.0% (60); missing-bar 0 | n/a |
| tweezer_bottom_b_tol0.20_overnight | 2 | overnight 100.0% (15); missing-bar 0 | overnight 100.0% (18); missing-bar 0 | overnight 100.0% (15); missing-bar 0 | overnight 100.0% (23); missing-bar 0 | n/a |
| tweezer_top_a_tol0.20_overnight | 2 | overnight 100.0% (70); missing-bar 0 | overnight 100.0% (65); missing-bar 0 | overnight 100.0% (77); missing-bar 0 | overnight 100.0% (52); missing-bar 0 | n/a |
| tweezer_top_b_tol0.20_overnight | 2 | overnight 100.0% (18); missing-bar 0 | overnight 100.0% (18); missing-bar 0 | overnight 100.0% (25); missing-bar 0 | overnight 100.0% (19); missing-bar 0 | n/a |

#### E. Tweezer prior-move survival

Cells: firings, then how many (percent of firings) survive prior-move test (i) = close[f-1] vs close[f-5], and (ii) = move of at least 1.0 x ATR(14) at f-1. Bearish entries need a prior advance, bullish a prior decline. Rows marked 'after decline'/'after advance' belong to shape entries with no direction of their own.

| entry | SPY | AAPL | JPM | XOM | BTCUSDT |
|---|---|---|---|---|---|
| tweezer_bottom_a_tol0.05 | 2427: (i) 1099 (45.3%), (ii) 403 (16.6%) | 2502: (i) 1201 (48.0%), (ii) 446 (17.8%) | 2551: (i) 1176 (46.1%), (ii) 455 (17.8%) | 2581: (i) 1207 (46.8%), (ii) 424 (16.4%) | 14665: (i) 6611 (45.1%), (ii) 2070 (14.1%) |
| tweezer_bottom_b_tol0.05 | 1214: (i) 566 (46.6%), (ii) 207 (17.1%) | 1207: (i) 594 (49.2%), (ii) 211 (17.5%) | 1201: (i) 553 (46.0%), (ii) 209 (17.4%) | 1209: (i) 557 (46.1%), (ii) 185 (15.3%) | 7649: (i) 3381 (44.2%), (ii) 1017 (13.3%) |
| tweezer_top_a_tol0.05 | 2786: (i) 1630 (58.5%), (ii) 659 (23.7%) | 2767: (i) 1419 (51.3%), (ii) 507 (18.3%) | 2596: (i) 1376 (53.0%), (ii) 529 (20.4%) | 2706: (i) 1440 (53.2%), (ii) 561 (20.7%) | 15423: (i) 7545 (48.9%), (ii) 2328 (15.1%) |
| tweezer_top_b_tol0.05 | 1386: (i) 814 (58.7%), (ii) 330 (23.8%) | 1322: (i) 688 (52.0%), (ii) 246 (18.6%) | 1195: (i) 639 (53.5%), (ii) 244 (20.4%) | 1319: (i) 705 (53.4%), (ii) 270 (20.5%) | 7968: (i) 3834 (48.1%), (ii) 1155 (14.5%) |
| tweezer_bottom_a_tol0.05_overnight | 14: (i) 5 (35.7%), (ii) 2 (14.3%) | 21: (i) 9 (42.9%), (ii) 3 (14.3%) | 24: (i) 10 (41.7%), (ii) 6 (25.0%) | 14: (i) 10 (71.4%), (ii) 1 (7.1%) | n/a |
| tweezer_bottom_b_tol0.05_overnight | 4: (i) 2 (50.0%), (ii) 0 (0.0%) | 5: (i) 2 (40.0%), (ii) 2 (40.0%) | 4: (i) 2 (50.0%), (ii) 1 (25.0%) | 4: (i) 1 (25.0%), (ii) 0 (0.0%) | n/a |
| tweezer_top_a_tol0.05_overnight | 24: (i) 13 (54.2%), (ii) 5 (20.8%) | 19: (i) 11 (57.9%), (ii) 5 (26.3%) | 22: (i) 12 (54.5%), (ii) 6 (27.3%) | 18: (i) 12 (66.7%), (ii) 6 (33.3%) | n/a |
| tweezer_top_b_tol0.05_overnight | 9: (i) 4 (44.4%), (ii) 2 (22.2%) | 4: (i) 2 (50.0%), (ii) 1 (25.0%) | 10: (i) 6 (60.0%), (ii) 3 (30.0%) | 3: (i) 3 (100.0%), (ii) 1 (33.3%) | n/a |
| tweezer_bottom_a_tol0.10 | 4791: (i) 2128 (44.4%), (ii) 811 (16.9%) | 5033: (i) 2442 (48.5%), (ii) 915 (18.2%) | 5007: (i) 2297 (45.9%), (ii) 889 (17.8%) | 4995: (i) 2386 (47.8%), (ii) 869 (17.4%) | 27648: (i) 12548 (45.4%), (ii) 3955 (14.3%) |
| tweezer_bottom_b_tol0.10 | 2231: (i) 1034 (46.3%), (ii) 389 (17.4%) | 2312: (i) 1124 (48.6%), (ii) 412 (17.8%) | 2288: (i) 1057 (46.2%), (ii) 409 (17.9%) | 2280: (i) 1109 (48.6%), (ii) 411 (18.0%) | 13552: (i) 6035 (44.5%), (ii) 1842 (13.6%) |
| tweezer_top_a_tol0.10 | 5357: (i) 3094 (57.8%), (ii) 1261 (23.5%) | 5441: (i) 2779 (51.1%), (ii) 1011 (18.6%) | 5079: (i) 2705 (53.3%), (ii) 1011 (19.9%) | 5255: (i) 2769 (52.7%), (ii) 1076 (20.5%) | 29027: (i) 14125 (48.7%), (ii) 4501 (15.5%) |
| tweezer_top_b_tol0.10 | 2558: (i) 1466 (57.3%), (ii) 596 (23.3%) | 2478: (i) 1270 (51.3%), (ii) 475 (19.2%) | 2298: (i) 1205 (52.4%), (ii) 444 (19.3%) | 2449: (i) 1281 (52.3%), (ii) 496 (20.3%) | 14125: (i) 6738 (47.7%), (ii) 2101 (14.9%) |
| tweezer_bottom_a_tol0.10_overnight | 32: (i) 16 (50.0%), (ii) 8 (25.0%) | 39: (i) 16 (41.0%), (ii) 5 (12.8%) | 50: (i) 23 (46.0%), (ii) 15 (30.0%) | 28: (i) 18 (64.3%), (ii) 3 (10.7%) | n/a |
| tweezer_bottom_b_tol0.10_overnight | 9: (i) 6 (66.7%), (ii) 3 (33.3%) | 9: (i) 4 (44.4%), (ii) 3 (33.3%) | 9: (i) 4 (44.4%), (ii) 1 (11.1%) | 12: (i) 6 (50.0%), (ii) 1 (8.3%) | n/a |
| tweezer_top_a_tol0.10_overnight | 39: (i) 21 (53.8%), (ii) 8 (20.5%) | 31: (i) 17 (54.8%), (ii) 6 (19.4%) | 39: (i) 19 (48.7%), (ii) 10 (25.6%) | 29: (i) 18 (62.1%), (ii) 8 (27.6%) | n/a |
| tweezer_top_b_tol0.10_overnight | 13: (i) 6 (46.2%), (ii) 2 (15.4%) | 8: (i) 5 (62.5%), (ii) 2 (25.0%) | 13: (i) 7 (53.8%), (ii) 3 (23.1%) | 9: (i) 6 (66.7%), (ii) 2 (22.2%) | n/a |
| tweezer_bottom_a_tol0.20 | 9282: (i) 4087 (44.0%), (ii) 1623 (17.5%) | 9490: (i) 4581 (48.3%), (ii) 1694 (17.9%) | 9375: (i) 4296 (45.8%), (ii) 1626 (17.3%) | 9301: (i) 4349 (46.8%), (ii) 1603 (17.2%) | 51386: (i) 23597 (45.9%), (ii) 7502 (14.6%) |
| tweezer_bottom_b_tol0.20 | 3928: (i) 1821 (46.4%), (ii) 719 (18.3%) | 4048: (i) 1975 (48.8%), (ii) 719 (17.8%) | 3914: (i) 1825 (46.6%), (ii) 704 (18.0%) | 3864: (i) 1833 (47.4%), (ii) 696 (18.0%) | 22565: (i) 10175 (45.1%), (ii) 3176 (14.1%) |
| tweezer_top_a_tol0.20 | 10176: (i) 5749 (56.5%), (ii) 2384 (23.4%) | 9990: (i) 5133 (51.4%), (ii) 1893 (18.9%) | 9654: (i) 5117 (53.0%), (ii) 1926 (20.0%) | 9723: (i) 5052 (52.0%), (ii) 1943 (20.0%) | 53404: (i) 26065 (48.8%), (ii) 8556 (16.0%) |
| tweezer_top_b_tol0.20 | 4302: (i) 2407 (56.0%), (ii) 991 (23.0%) | 4209: (i) 2161 (51.3%), (ii) 810 (19.2%) | 4018: (i) 2117 (52.7%), (ii) 789 (19.6%) | 4138: (i) 2141 (51.7%), (ii) 838 (20.3%) | 23569: (i) 11236 (47.7%), (ii) 3658 (15.5%) |
| tweezer_bottom_a_tol0.20_overnight | 61: (i) 31 (50.8%), (ii) 14 (23.0%) | 87: (i) 39 (44.8%), (ii) 13 (14.9%) | 78: (i) 31 (39.7%), (ii) 18 (23.1%) | 60: (i) 35 (58.3%), (ii) 10 (16.7%) | n/a |
| tweezer_bottom_b_tol0.20_overnight | 15: (i) 11 (73.3%), (ii) 4 (26.7%) | 18: (i) 8 (44.4%), (ii) 4 (22.2%) | 15: (i) 7 (46.7%), (ii) 2 (13.3%) | 23: (i) 13 (56.5%), (ii) 3 (13.0%) | n/a |
| tweezer_top_a_tol0.20_overnight | 70: (i) 36 (51.4%), (ii) 12 (17.1%) | 65: (i) 35 (53.8%), (ii) 8 (12.3%) | 77: (i) 39 (50.6%), (ii) 16 (20.8%) | 52: (i) 34 (65.4%), (ii) 12 (23.1%) | n/a |
| tweezer_top_b_tol0.20_overnight | 18: (i) 7 (38.9%), (ii) 2 (11.1%) | 18: (i) 11 (61.1%), (ii) 3 (16.7%) | 25: (i) 12 (48.0%), (ii) 5 (20.0%) | 19: (i) 11 (57.9%), (ii) 2 (10.5%) | n/a |

## F. Forward moves (DESCRIPTIVE ONLY, NOT a basis for choosing patterns)

Move = close of the firing bar to the close 1 or 4 bars later, in ATR(14) units at the firing bar, signed so that positive = the entry's direction. Directions: bullish entries up, bearish down; spinning top and marubozu use their colour; continuation entries (three white soldiers, three black crows, rise/fall three methods) use their own direction; plain doji has no direction and is left out. Standard errors are naive (they treat moves as independent; neighbouring bars overlap, especially for 4-bar moves). Hammer/inverted-hammer shape entries in F are the shapes after a decline (bullish) or advance (bearish) under prior-move test (i).

##### Stocks pooled (SPY, AAPL, JPM, XOM), moves that cross an overnight boundary EXCLUDED

Columns per horizon: n moves | mean move in the entry's direction (ATR units) | standard error | share of moves in the entry's direction

| entry | 1 bar(s) later: n | 1 bar(s) later: mean | 1 bar(s) later: SE | 1 bar(s) later: share | 4 bar(s) later: n | 4 bar(s) later: mean | 4 bar(s) later: SE | 4 bar(s) later: share |
|---|---|---|---|---|---|---|---|---|
| ALL BARS (baseline, up) | 104847 | +0.003 | 0.002 | 50.9% | 91964 | +0.009 | 0.004 | 51.8% |
| dragonfly_doji | 1931 | -0.004 | 0.012 | 49.8% | 1778 | -0.029 | 0.024 | 50.9% |
| gravestone_doji (down = bearish) | 1846 | -0.028 | 0.012 | 45.9% | 1701 | -0.042 | 0.026 | 46.1% |
| spinning_top_up | 11391 | +0.016 | 0.006 | 52.0% | 9952 | +0.023 | 0.012 | 52.5% |
| spinning_top_down (down = bearish) | 10526 | +0.002 | 0.006 | 49.0% | 9216 | -0.008 | 0.012 | 47.3% |
| marubozu_up | 3038 | +0.009 | 0.009 | 49.7% | 2688 | +0.034 | 0.020 | 52.9% |
| marubozu_down (down = bearish) | 2568 | +0.010 | 0.012 | 49.0% | 2269 | +0.031 | 0.024 | 49.0% |
| hammer | 2945 | -0.008 | 0.010 | 49.1% | 2667 | -0.011 | 0.020 | 51.0% |
| hanging_man (down = bearish) | 1733 | +0.015 | 0.013 | 50.5% | 1571 | +0.021 | 0.026 | 48.5% |
| inverted_hammer | 747 | +0.030 | 0.021 | 53.1% | 668 | -0.013 | 0.043 | 53.3% |
| shooting_star (down = bearish) | 981 | -0.037 | 0.018 | 45.3% | 881 | -0.067 | 0.036 | 47.0% |
| engulfing_bull | 7114 | +0.005 | 0.007 | 51.3% | 6098 | +0.017 | 0.014 | 52.3% |
| engulfing_bear (down = bearish) | 7438 | +0.008 | 0.007 | 49.0% | 6436 | +0.003 | 0.015 | 48.4% |
| harami_bull | 3467 | +0.015 | 0.010 | 51.7% | 3050 | -0.010 | 0.021 | 51.5% |
| harami_bear (down = bearish) | 3527 | -0.009 | 0.010 | 48.4% | 3044 | -0.030 | 0.021 | 47.4% |
| piercing | 68 | +0.036 | 0.093 | 58.8% | 63 | +0.051 | 0.158 | 54.0% |
| dark_cloud (down = bearish) | 83 | +0.078 | 0.078 | 53.0% | 78 | +0.059 | 0.180 | 48.7% |
| morning_star | 424 | +0.055 | 0.032 | 51.2% | 362 | +0.083 | 0.063 | 49.2% |
| evening_star (down = bearish) | 453 | +0.004 | 0.029 | 49.7% | 389 | +0.036 | 0.066 | 51.2% |
| three_inside_up | 401 | +0.006 | 0.029 | 50.6% | 354 | +0.053 | 0.063 | 51.4% |
| three_inside_down (down = bearish) | 401 | -0.037 | 0.034 | 46.4% | 336 | -0.207 | 0.069 | 42.6% |
| three_white_soldiers | 137 | -0.032 | 0.043 | 42.3% | 119 | +0.039 | 0.087 | 52.1% |
| three_black_crows (down = bearish) | 22 | -0.008 | 0.103 | 54.5% | 19 | +0.296 | 0.167 | 63.2% |
| rise_fall_3_up | 28 | +0.012 | 0.147 | 57.1% | 25 | +0.495 | 0.243 | 64.0% |
| rise_fall_3_down (down = bearish) | 17 | -0.136 | 0.149 | 29.4% | 14 | -0.177 | 0.288 | 42.9% |
| piercing_relaxed | 1026 | +0.013 | 0.020 | 51.3% | 878 | +0.042 | 0.040 | 52.6% |
| dark_cloud_relaxed (down = bearish) | 976 | +0.011 | 0.021 | 47.6% | 846 | -0.009 | 0.044 | 46.0% |
| morning_star_relaxed_touch | 618 | +0.032 | 0.026 | 51.0% | 526 | +0.056 | 0.050 | 50.0% |
| morning_star_relaxed_any | 2156 | +0.018 | 0.014 | 50.8% | 1840 | +0.049 | 0.029 | 50.8% |
| evening_star_relaxed_touch (down = bearish) | 645 | +0.002 | 0.026 | 49.8% | 545 | +0.034 | 0.056 | 51.6% |
| evening_star_relaxed_any (down = bearish) | 2061 | -0.012 | 0.014 | 48.4% | 1758 | -0.029 | 0.030 | 47.0% |
| hammer_shape_after_decline_i | 3664 | -0.020 | 0.009 | 48.1% | 3326 | -0.043 | 0.019 | 50.1% |
| hammer_shape_after_advance_i (down = bearish) | 4264 | +0.008 | 0.008 | 49.6% | 3776 | +0.027 | 0.017 | 49.2% |
| inverted_hammer_shape_after_decline_i | 3436 | +0.015 | 0.010 | 51.1% | 3090 | -0.005 | 0.020 | 50.2% |
| inverted_hammer_shape_after_advance_i (down = bearish) | 3938 | -0.029 | 0.009 | 46.8% | 3520 | -0.046 | 0.018 | 46.8% |
| tweezer_bottom_b_tol0.10 | 8774 | +0.013 | 0.006 | 51.6% | 7670 | +0.008 | 0.012 | 51.8% |
| tweezer_top_b_tol0.10 (down = bearish) | 9460 | +0.006 | 0.006 | 48.6% | 8245 | +0.009 | 0.012 | 48.3% |

##### Stocks pooled, moves crossing overnight INCLUDED (missing-bar moves still excluded)

Columns per horizon: n moves | mean move in the entry's direction (ATR units) | standard error | share of moves in the entry's direction

| entry | 1 bar(s) later: n | 1 bar(s) later: mean | 1 bar(s) later: SE | 1 bar(s) later: share | 4 bar(s) later: n | 4 bar(s) later: mean | 4 bar(s) later: SE | 4 bar(s) later: share |
|---|---|---|---|---|---|---|---|---|
| ALL BARS (baseline, up) | 109125 | +0.011 | 0.003 | 51.0% | 108857 | +0.045 | 0.006 | 52.2% |
| dragonfly_doji | 1949 | -0.001 | 0.013 | 49.9% | 1940 | +0.011 | 0.031 | 51.2% |
| gravestone_doji (down = bearish) | 1862 | -0.008 | 0.015 | 46.2% | 1854 | -0.015 | 0.036 | 46.5% |
| spinning_top_up | 11869 | +0.020 | 0.009 | 52.0% | 11844 | +0.052 | 0.018 | 52.7% |
| spinning_top_down (down = bearish) | 10944 | -0.007 | 0.008 | 48.8% | 10915 | -0.038 | 0.018 | 47.2% |
| marubozu_up | 3087 | +0.004 | 0.012 | 49.7% | 3082 | +0.048 | 0.031 | 53.1% |
| marubozu_down (down = bearish) | 2617 | +0.024 | 0.015 | 48.9% | 2606 | +0.035 | 0.034 | 49.0% |
| hammer | 2996 | -0.002 | 0.012 | 49.3% | 2987 | +0.032 | 0.028 | 51.4% |
| hanging_man (down = bearish) | 1756 | +0.013 | 0.015 | 50.3% | 1743 | +0.013 | 0.034 | 48.3% |
| inverted_hammer | 758 | +0.024 | 0.024 | 53.2% | 753 | -0.031 | 0.060 | 53.3% |
| shooting_star (down = bearish) | 996 | -0.025 | 0.024 | 45.5% | 991 | -0.094 | 0.051 | 46.7% |
| engulfing_bull | 7574 | +0.026 | 0.012 | 51.5% | 7550 | +0.034 | 0.024 | 52.3% |
| engulfing_bear (down = bearish) | 7798 | -0.001 | 0.010 | 48.8% | 7777 | -0.036 | 0.022 | 48.0% |
| harami_bull | 3580 | +0.019 | 0.015 | 51.7% | 3574 | +0.015 | 0.033 | 52.1% |
| harami_bear (down = bearish) | 3686 | +0.002 | 0.016 | 48.4% | 3682 | -0.077 | 0.033 | 47.2% |
| piercing | 72 | -0.048 | 0.103 | 56.9% | 71 | -0.096 | 0.163 | 50.7% |
| dark_cloud (down = bearish) | 87 | -0.029 | 0.100 | 51.7% | 86 | -0.277 | 0.243 | 46.5% |
| morning_star | 453 | +0.131 | 0.048 | 51.9% | 453 | +0.172 | 0.090 | 50.6% |
| evening_star (down = bearish) | 476 | +0.031 | 0.038 | 49.4% | 474 | +0.022 | 0.089 | 51.3% |
| three_inside_up | 427 | -0.030 | 0.053 | 50.6% | 427 | +0.095 | 0.088 | 53.2% |
| three_inside_down (down = bearish) | 422 | -0.061 | 0.040 | 45.7% | 422 | -0.185 | 0.091 | 43.8% |
| three_white_soldiers | 142 | -0.022 | 0.049 | 43.0% | 142 | +0.033 | 0.132 | 52.1% |
| three_black_crows (down = bearish) | 22 | -0.008 | 0.103 | 54.5% | 22 | +0.408 | 0.264 | 63.6% |
| rise_fall_3_up | 29 | -0.032 | 0.149 | 55.2% | 29 | +0.221 | 0.300 | 58.6% |
| rise_fall_3_down (down = bearish) | 18 | -0.226 | 0.167 | 27.8% | 18 | -0.771 | 0.513 | 38.9% |
| piercing_relaxed | 1086 | +0.042 | 0.030 | 51.8% | 1079 | +0.120 | 0.062 | 52.9% |
| dark_cloud_relaxed (down = bearish) | 1016 | -0.023 | 0.028 | 47.1% | 1015 | -0.079 | 0.058 | 46.5% |
| morning_star_relaxed_touch | 655 | +0.072 | 0.038 | 51.1% | 655 | +0.074 | 0.073 | 50.4% |
| morning_star_relaxed_any | 2285 | +0.054 | 0.022 | 51.1% | 2281 | +0.100 | 0.041 | 52.0% |
| evening_star_relaxed_touch (down = bearish) | 678 | +0.022 | 0.036 | 49.7% | 676 | -0.021 | 0.076 | 51.0% |
| evening_star_relaxed_any (down = bearish) | 2187 | -0.042 | 0.021 | 48.0% | 2181 | -0.088 | 0.042 | 47.0% |
| hammer_shape_after_decline_i | 3727 | -0.010 | 0.011 | 48.4% | 3716 | -0.026 | 0.025 | 50.3% |
| hammer_shape_after_advance_i (down = bearish) | 4351 | +0.009 | 0.010 | 49.5% | 4329 | -0.010 | 0.024 | 48.6% |
| inverted_hammer_shape_after_decline_i | 3483 | +0.016 | 0.012 | 51.1% | 3473 | -0.019 | 0.029 | 50.6% |
| inverted_hammer_shape_after_advance_i (down = bearish) | 4006 | -0.022 | 0.010 | 47.0% | 3995 | -0.052 | 0.025 | 47.1% |
| tweezer_bottom_b_tol0.10 | 9106 | +0.033 | 0.009 | 51.8% | 9092 | +0.024 | 0.019 | 52.0% |
| tweezer_top_b_tol0.10 (down = bearish) | 9776 | +0.004 | 0.008 | 48.6% | 9763 | -0.031 | 0.019 | 48.1% |

##### BTCUSDT (no overnight; moves across a missing bar excluded)

Columns per horizon: n moves | mean move in the entry's direction (ATR units) | standard error | share of moves in the entry's direction

| entry | 1 bar(s) later: n | 1 bar(s) later: mean | 1 bar(s) later: SE | 1 bar(s) later: share | 4 bar(s) later: n | 4 bar(s) later: mean | 4 bar(s) later: SE | 4 bar(s) later: share |
|---|---|---|---|---|---|---|---|---|
| ALL BARS (baseline, up) | 151558 | +0.002 | 0.002 | 50.2% | 151552 | +0.010 | 0.004 | 50.6% |
| dragonfly_doji | 3028 | -0.021 | 0.012 | 47.5% | 3027 | -0.052 | 0.026 | 48.7% |
| gravestone_doji (down = bearish) | 2748 | -0.030 | 0.012 | 47.0% | 2748 | -0.059 | 0.027 | 49.6% |
| spinning_top_up | 14130 | -0.005 | 0.006 | 49.9% | 14130 | -0.013 | 0.013 | 50.0% |
| spinning_top_down (down = bearish) | 14294 | +0.002 | 0.006 | 49.8% | 14293 | -0.012 | 0.012 | 48.9% |
| marubozu_up | 4674 | +0.020 | 0.011 | 46.7% | 4674 | +0.081 | 0.023 | 49.9% |
| marubozu_down (down = bearish) | 4419 | -0.027 | 0.011 | 44.9% | 4419 | -0.006 | 0.022 | 48.0% |
| hammer | 4467 | -0.031 | 0.010 | 48.4% | 4467 | -0.014 | 0.022 | 50.3% |
| hanging_man (down = bearish) | 2576 | +0.037 | 0.013 | 55.1% | 2574 | +0.009 | 0.028 | 51.9% |
| inverted_hammer | 655 | +0.020 | 0.026 | 55.4% | 655 | -0.007 | 0.058 | 52.4% |
| shooting_star (down = bearish) | 755 | -0.000 | 0.023 | 50.2% | 755 | -0.034 | 0.051 | 50.7% |
| engulfing_bull | 14265 | +0.014 | 0.006 | 48.6% | 14264 | -0.015 | 0.013 | 47.8% |
| engulfing_bear (down = bearish) | 14414 | +0.008 | 0.006 | 48.0% | 14414 | -0.017 | 0.013 | 47.5% |
| harami_bull | 7102 | -0.007 | 0.009 | 52.0% | 7101 | +0.019 | 0.018 | 51.6% |
| harami_bear (down = bearish) | 7258 | -0.012 | 0.009 | 50.6% | 7258 | -0.011 | 0.019 | 51.0% |
| piercing | 4 | -0.167 | 0.282 | 50.0% | 4 | -0.177 | 0.471 | 25.0% |
| dark_cloud (down = bearish) | 9 | +0.221 | 0.148 | 66.7% | 9 | -0.023 | 0.375 | 44.4% |
| morning_star | 385 | -0.061 | 0.032 | 45.5% | 385 | -0.053 | 0.073 | 48.1% |
| evening_star (down = bearish) | 393 | +0.023 | 0.039 | 49.1% | 393 | +0.092 | 0.086 | 49.1% |
| three_inside_up | 455 | -0.008 | 0.037 | 46.6% | 455 | +0.092 | 0.118 | 44.6% |
| three_inside_down (down = bearish) | 447 | -0.075 | 0.034 | 43.6% | 447 | -0.086 | 0.078 | 43.8% |
| three_white_soldiers | 180 | +0.130 | 0.095 | 44.4% | 180 | +0.155 | 0.122 | 47.2% |
| three_black_crows (down = bearish) | 24 | -0.081 | 0.131 | 37.5% | 24 | -0.401 | 0.273 | 29.2% |
| rise_fall_3_up | 28 | -0.051 | 0.169 | 35.7% | 28 | -0.237 | 0.325 | 57.1% |
| rise_fall_3_down (down = bearish) | 23 | -0.044 | 0.137 | 56.5% | 23 | -0.212 | 0.291 | 34.8% |
| piercing_relaxed | 2226 | +0.015 | 0.016 | 51.0% | 2226 | +0.034 | 0.033 | 53.5% |
| dark_cloud_relaxed (down = bearish) | 2071 | +0.017 | 0.016 | 50.8% | 2071 | +0.008 | 0.035 | 51.7% |
| morning_star_relaxed_touch | 1158 | -0.016 | 0.021 | 49.0% | 1158 | -0.009 | 0.044 | 49.7% |
| morning_star_relaxed_any | 3464 | +0.003 | 0.013 | 48.7% | 3464 | +0.030 | 0.030 | 49.0% |
| evening_star_relaxed_touch (down = bearish) | 1129 | +0.011 | 0.022 | 48.2% | 1129 | +0.020 | 0.048 | 50.0% |
| evening_star_relaxed_any (down = bearish) | 3494 | +0.004 | 0.012 | 47.3% | 3494 | +0.021 | 0.026 | 49.0% |
| hammer_shape_after_decline_i | 6023 | -0.020 | 0.008 | 49.3% | 6021 | -0.005 | 0.019 | 50.9% |
| hammer_shape_after_advance_i (down = bearish) | 6242 | +0.029 | 0.009 | 54.9% | 6242 | +0.007 | 0.019 | 51.6% |
| inverted_hammer_shape_after_decline_i | 5331 | +0.047 | 0.009 | 55.3% | 5331 | +0.054 | 0.020 | 54.0% |
| inverted_hammer_shape_after_advance_i (down = bearish) | 5962 | -0.018 | 0.009 | 49.4% | 5962 | -0.022 | 0.018 | 51.1% |
| tweezer_bottom_b_tol0.10 | 13552 | +0.007 | 0.006 | 49.9% | 13550 | +0.019 | 0.013 | 50.1% |
| tweezer_top_b_tol0.10 (down = bearish) | 14125 | +0.009 | 0.006 | 49.6% | 14125 | -0.012 | 0.012 | 48.3% |
