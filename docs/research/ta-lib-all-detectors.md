# TA-Lib: all 61 candlestick detectors, what each output sign means

Research branch `research/ta-lib-all-detectors` (never merged). Read on 2026-11-13.

## Sources and method

- TA-Lib C source, tag v0.8.3 (commit `62021c1d14ef5499505af5547384cab509adf3fc`): `src/ta_func/ta_CDL*.c`, 61 files. https://github.com/TA-Lib/ta-lib/tree/v0.8.3/src/ta_func . I read, in each file, the "Must have:" comment, the condition under it, the `outInteger[...] = ...` assignment, and `TA_CDLxxx_Lookback`.
- Machine-readable function metadata in the same tag: `ta_func_api.xml` (https://github.com/TA-Lib/ta-lib/blob/v0.8.3/ta_func_api.xml). Each CDL function's output argument carries flags such as `Pattern Bull Bear`, `Pattern Bool`, `Positive`, `Negative`, `Zero`, `Pattern Weak`, `Pattern Confirm`. These are TA-Lib's own declaration of what the sign means and are used as the class evidence below.
- Candle-setting defaults (what "long", "short", "near", "doji" mean): `src/ta_common/ta_global.c` (see the earlier note `docs/research/ta-lib.md` on branch `research/ta-lib`; not re-read here).
- Python wrapper: TA-Lib 0.8.3 wheel in conda env `agentic-jev-trader`, called through `talib` and `talib.abstract` (lookback, display names). I did not read the wrapper's source; its behaviour was checked by running it (see section 4).
- Empirical check: `docs/research/ta-lib-all-detectors-observed.py` runs all 61 detectors over real 15-minute bars of SPY, AAPL, JPM, XOM and BTCUSDT (volume 0 rows dropped; 27,905 / 27,393 / 26,994 / 27,019 / 151,574 bars). Only aggregate counts are kept in this note; the raw bars are not in the repo (licence). Full per-asset counts are in the appendix.
- `docs/research/ta-lib-all-detectors-synthetic.py`: 3 million random bars with frequent gaps, used only to confirm the sign of the six detectors that never fired on real bars (and three rare ones). Synthetic, so it confirms signs, not real-world frequency.

## What the source does and does not say

- The "Must have:" comment in each C file describes the **shape** (candles, colours, gaps). It almost never states what the pattern **means** for the market. The one comment that names a direction is `ta_CDLSEPARATINGLINES.c` ("bullish (bearish) belt hold"), and `ta_CDLHIKKAKE.c` / `ta_CDLHIKKAKEMOD.c` label the shapes "(bull)" / "(bear)". `ta_CDLHAMMER.c` also carries a change-log line "Remove the outInteger comment, which misstated the values": the old per-function value comments were removed because they were wrong, so the code and the XML flags are the reliable evidence for the output values.
- So for "traditional meaning" I mostly write "source silent" and give the meaning from Steve Nison, "Japanese Candlestick Charting Techniques" (the book the TA-Lib comments themselves name, along with Greg Morris). **These Nison attributions come from my recollection of the book; I could not open it in this session and have not re-verified them.** Treat the meaning column as "standard textbook reading, unverified", not as source-confirmed.
- Output values: every detector returns integers. Most are 0 or +/-100. ENGULFING, HARAMI and HARAMICROSS also return +/-80 ("weak": a body edge equals the previous body's edge; XML flag `Pattern Weak`). HIKKAKE and HIKKAKEMOD return +/-100 on the pattern and +/-200 on a confirmation up to 3 bars later (XML flag `Pattern Confirm`).
- "Bar colour": white = close >= open (a bar with close == open counts as white, so +1), black = close < open.

## Terms used in the table

- **Span**: number of consecutive bars the pattern itself looks at, counted from the highest `[i - n]` index in the source condition (plus 1). Single-bar shapes = 1. HAMMER, HANGINGMAN, INVERTEDHAMMER, SHOOTINGSTAR compare with the previous bar, so they span 2. HIKKAKE spans 3 and may confirm up to 3 bars later.
- **Lookback**: `talib.abstract.Function(name).lookback` (matches `TA_CDLxxx_Lookback` in the C source). It is the number of leading bars that always return 0 and includes the averaging window for "long/short/near", so it is bigger than the span. It is not always span minus 1: CDL3OUTSIDE returns 3 although it only reads 3 bars (so 2 would do), CDLENGULFING returns 2 for a 2-bar pattern, CDLXSIDEGAP3METHODS returns 2 for a 3-bar pattern (it uses no averages).
- **Jump**: "yes" when the source condition forces an open (or body, or shadow) strictly beyond the previous bar's body or high/low, i.e. a gap or an open past the prior high/low. "weak" when the only requirement is a strict inequality such as "opens above the prior close" with no size, so a one-cent move satisfies it; those are not counted as jumps.
- **Classes** (sign meaning):
  - (a) sign is a real hint: positive = bullish, negative = bearish.
  - (b) one sign only, and it matches the pattern's traditional meaning.
  - (c) one sign only, but the traditional meaning is the opposite or neutral.
  - (d) sign is only the bar's colour and the pattern itself is neutral (not a hint).
- Lean = proposed lean per sign. **EXCEPTION** marks every case where the lean differs from TA-Lib's raw sign (+ = bullish, - = bearish as the raw reading).

## 1. The table

Observed = values seen on the real bars, all assets pooled (values only; counts in the appendix). Evidence = what in the source supports the class.

| # | Function / plain name | Span / lookback | Source values; observed | Class | Evidence for class (source) | Traditional meaning | Jump | Lean |
|---|---|---|---|---|---|---|---|---|
| 1 | CDL2CROWS, two crows | 3 / 12 | -100 only; -100 | b | Code always writes -100; XML `Negative Zero`, `Pattern Bull Bear`. Shape: long white, black bar gapping up, black bar opening inside the 2nd body and closing inside the 1st. | Source silent. Nison: bearish reversal after an uptrend. | yes (2nd body gaps above 1st body) | - bearish |
| 2 | CDL3BLACKCROWS, three black crows | 4 / 13 | -100 only; -100 | b | Code always -100; XML `Negative Zero`. Needs a white bar before three declining black bars, each opening inside the previous black body. | Source silent. Nison: bearish reversal after an advance. | no | - bearish |
| 3 | CDL3INSIDE, three inside up/down | 3 / 12 | +/-100; -100, 100 | a | Code: `-colour(1st bar) * 100`: a white 1st bar gives -100 (three inside down), a black 1st bar gives +100 (three inside up). XML `Positive Negative`, `Bull Bear`. | Source silent. Nison: harami followed by a confirming bar; up = bullish reversal, down = bearish reversal. | no | + bullish, - bearish |
| 4 | CDL3LINESTRIKE, three-line strike | 4 / 8 | +/-100; -100, 100 | a | Code: sign = colour of the three same-coloured bars (+ = three white soldiers then a black 4th bar that opens above the 3rd close and closes below the 1st open). | Source silent. Nison: continuation of the three-bar trend (bullish three-line strike after three white lines, bearish after three black). | weak (4th opens above/below prior close) | + bullish, - bearish |
| 5 | CDL3OUTSIDE, three outside up/down | 3 / 3 | +/-100; -100, 100 | a | Code: sign = colour of the 2nd (engulfing) bar; 3rd bar must close beyond the 2nd close. | Source silent. Nison: engulfing plus confirmation; up = bullish reversal, down = bearish reversal. | no | + bullish, - bearish |
| 6 | CDL3STARSINSOUTH, three stars in the south | 3 / 12 | +100 only; never fired on real bars (synthetic: +100) | b | Code always +100; XML `Positive Zero`. Three black bars with shrinking bodies/ranges. | Source silent. Nison: rare bullish reversal at the end of a decline. | no | + bullish |
| 7 | CDL3WHITESOLDIERS, three advancing white soldiers | 3 / 12 | +100 only; 100 | b | Code always +100; XML `Positive Zero`. | Source silent. Nison: bullish reversal/continuation after a decline. Source comment notes Greg Morris wants long bodies, Nison does not. | no | + bullish |
| 8 | CDLABANDONEDBABY, abandoned baby | 3 / 12 | +/-100; never fired on real bars (synthetic: -100, 100) | a | Code: sign = colour of the 3rd bar; shadow gaps (doji isolated by gaps on both sides). | Source silent. Nison: major reversal; bullish after a decline (white 3rd bar), bearish after an advance (black 3rd bar). | yes (shadow gaps both sides of the doji) | + bullish, - bearish |
| 9 | CDLADVANCEBLOCK, advance block | 3 / 12 | -100 only; -100 | b | Code always -100; XML `Negative Zero`. Three white bars with fading bodies / growing upper shadows. | Source silent. Nison: bearish warning (stalling advance). | no | - bearish |
| 10 | CDLBELTHOLD, belt-hold | 1 / 10 | +/-100; -100, 100 | a | Code: sign = bar colour; + = long white bar with very short lower shadow, - = long black bar with very short upper shadow. The SEPARATINGLINES comment names the + form "bullish belt hold" and the - form "bearish belt hold". | Nison: white belt hold bullish, black belt hold bearish (reversal at extremes). Source comment names the two forms bullish/bearish. | no | + bullish, - bearish |
| 11 | CDLBREAKAWAY, breakaway | 5 / 14 | +/-100; -100, 100 | a | Code: sign = colour of the 5th bar (+ when the 1st bar is black: bullish). | Source silent. Nison: reversal; bullish after a decline, bearish after an advance. | yes (2nd body gaps beyond 1st body) | + bullish, - bearish |
| 12 | CDLCLOSINGMARUBOZU, closing marubozu | 1 / 10 | +/-100; -100, 100 | a | Code: sign = bar colour; long body, no/very short shadow on the closing side only (upper for white, lower for black). | Source silent. Nison on marubozu: white = bullish strength, black = bearish strength. Colour-only sign (see judgement call below). | no | + bullish, - bearish |
| 13 | CDLCONCEALBABYSWALL, concealing baby swallow | 4 / 13 | +100 only; never fired on real bars (synthetic: +100) | b | Code always +100; XML `Positive Zero`. Four black bars (two marubozu, a gapping bar, an engulfing bar). | Source silent. Nison: rare bullish bottom reversal. | yes (3rd bar body gaps down below 2nd body) | + bullish |
| 14 | CDLCOUNTERATTACK, counterattack lines | 2 / 11 | +/-100; -100, 100 | a | Code: sign = colour of the 2nd bar (long, closing at the 1st bar's close, opposite colour). | Source silent. Nison: white 2nd bar after a black 1st = bullish, black after white = bearish. | no | + bullish, - bearish |
| 15 | CDLDARKCLOUDCOVER, dark cloud cover | 2 / 11 | -100 only; -100 | b | Code always -100; XML `Negative Zero`. | Source silent. Nison: bearish reversal after an advance. Default `optInPenetration` is 0.5 (from `ta_func_api.xml`; the 3-bar star/abandoned-baby patterns default to 0.3, MATHOLD to 0.5). | yes (opens above the prior high) | - bearish |
| 16 | CDLDOJI, doji | 1 / 10 | +100 only; 100 | c | Code always +100; XML `Pattern Bool` (flag is "bool", not "bull/bear"): only says "a doji happened". Comment: "open quite equal to close". | Source silent. Nison: indecision, neutral on its own. | no | neutral. **EXCEPTION** (raw + vs neutral) |
| 17 | CDLDOJISTAR, doji star | 2 / 11 | +/-100; -100, 100 | a | Code: `-colour(1st bar) * 100`: after a long white bar the star gaps up and the output is -100; after a long black bar it gaps down and the output is +100. XML `Bull Bear`. | Source silent. Nison: warning of reversal; bearish after an advance, bullish after a decline. | yes (star body gaps beyond 1st body) | + bullish, - bearish |
| 18 | CDLDRAGONFLYDOJI, dragonfly doji | 1 / 10 | +100 only; 100 | b | Code always +100; XML `Pattern Bool Positive Zero`. Doji body, no/very short upper shadow, lower shadow not very short. | Source silent. Nison: bullish at market bottoms (neutral elsewhere). | no | + bullish (the sign is + but is a bool, no sign hint) |
| 19 | CDLENGULFING, engulfing pattern | 2 / 2 | +/-100, +/-80; -100, -80, 80, 100 | a | Code: sign = colour of the 2nd bar (white engulfs black = +). 100 when neither open nor close equals the previous close/open (strict), 80 when one edge matches. XML `Bull Bear`, `Pattern Weak`. | Source silent. Nison: bullish engulfing after a decline, bearish after an advance. | no (open must differ from prior close for 100; no required gap) | + bullish, - bearish (use sign, ignore 80 vs 100) |
| 20 | CDLEVENINGDOJISTAR, evening doji star | 3 / 12 | -100 only; -100 | b | Code always -100; XML `Negative Zero`. | Source silent. Nison: bearish top reversal. | yes (doji body gaps above 1st body) | - bearish |
| 21 | CDLEVENINGSTAR, evening star | 3 / 12 | -100 only; -100 | b | Code always -100; XML `Negative Zero`. | Source silent. Nison: bearish top reversal. | yes (star body gaps above 1st body) | - bearish |
| 22 | CDLGAPSIDESIDEWHITE, up/down-gap side-by-side white lines | 3 / 7 | +/-100; -100, 100 | a | Code: `+100` if the gap is upside, `-100` if downside; both of the last two bars white. XML `Bull Bear`. | Source silent. Nison: upside gap = bullish continuation, downside gap = bearish continuation. | yes (gap between bodies) | + bullish, - bearish |
| 23 | CDLGRAVESTONEDOJI, gravestone doji | 1 / 10 | +100 only; 100 | c | Code always +100; XML `Pattern Bool Positive Zero`. Doji body, no/very short lower shadow, upper shadow not very short. The + is a "yes" flag, not bullish. | Source silent. Nison: bearish when it appears at market tops (can matter at bottoms, per the book; treated as bearish here as the brief asks). | no | - bearish. **EXCEPTION** (raw + vs bearish) |
| 24 | CDLHAMMER, hammer | 2 / 11 | +100 only; 100 | b | Code always +100; XML `Positive Zero`. Small body, long lower shadow, no/very short upper shadow, body near/below the previous bar's low. | Source silent. Nison: bullish reversal after a decline. | no (uses prior low as a weak proxy for a decline) | + bullish |
| 25 | CDLHANGINGMAN, hanging man | 2 / 11 | -100 only; -100 | b | Code always -100; XML `Negative Zero`. Same shape as hammer, body near/above the previous bar's high. | Source silent. Nison: bearish after an advance (needs confirmation). | no | - bearish |
| 26 | CDLHARAMI, harami | 2 / 11 | +/-100, +/-80; -100, -80, 80, 100 | a | Code: `-colour(1st bar) * 100` (or * 80 when an edge of the 2nd body matches the 1st body): black 1st bar = +. XML `Bull Bear`, `Pattern Weak`. | Source silent. Nison: potential reversal; bullish after a long black bar, bearish after a long white bar. | no | + bullish, - bearish (ignore 80 vs 100) |
| 27 | CDLHARAMICROSS, harami cross | 2 / 11 | +/-100, +/-80; -100, -80, 80, 100 | a | Same sign rule as harami; 2nd bar is a doji. | Source silent. Nison: stronger reversal warning than harami. | no | + bullish, - bearish |
| 28 | CDLHIGHWAVE, high-wave candle | 1 / 10 | +/-100; -100, 100 | d | Code: sign = bar colour. XML flags only `Positive Negative Zero`, with **no** `Pattern Bull Bear` flag, i.e. TA-Lib does not call it a bull/bear signal. Comment: short body, very long upper and lower shadow. | Source silent. Nison: indecision, neutral. | no | neutral both signs. **EXCEPTION** (both signs) |
| 29 | CDLHIKKAKE, hikkake pattern | 3 (+ confirm within 3 more bars) / 5 | +/-100, +/-200; -200, -100, 100, 200 | a | Code: `+100` when the 3rd bar has lower high and lower low than the 2nd ("(bull) 3rd: lower high and lower low"), `-100` for higher high and higher low ("(bear)"); +/-200 when a later close (within 3 bars) breaks the 2nd bar's high (low) in the same direction. XML `Bull Bear`, `Pattern Confirm`. | Source: no meaning stated, only the "(bull)/(bear)" labels. Reference: Daniel Chesler's hikkake (a failed inside-bar breakout), bullish when the false move is down; my recollection, unverified. | no | + bullish, - bearish (200 = confirmed) |
| 30 | CDLHIKKAKEMOD, modified hikkake | 4 (+ confirm within 3 more) / 10 | +/-100, +/-200; -200, -100, 100, 200 | a | Same sign rule as hikkake, one extra inside bar; 2nd bar's close near its extreme. | As hikkake. | no | + bullish, - bearish |
| 31 | CDLHOMINGPIGEON, homing pigeon | 2 / 11 | +100 only; 100 | b | Code always +100; XML `Positive Zero`. Long black bar then a short black bar inside it. | Source silent. Nison: bullish (like a black-on-black harami). | no | + bullish |
| 32 | CDLIDENTICAL3CROWS, identical three crows | 3 / 12 | -100 only; -100 | b | Code always -100; XML `Negative Zero`. Each black bar opens at/very near the prior close (an `Equal` tolerance). | Source silent. Nison: bearish. | no | - bearish |
| 33 | CDLINNECK, in-neck pattern | 2 / 11 | -100 only; -100 | b | Code always -100; XML `Negative Zero`. Long black, then white bar opening below the prior low and closing slightly into the prior body. | Source silent. Nison: bearish continuation. | yes (opens below the prior low) | - bearish |
| 34 | CDLINVERTEDHAMMER, inverted hammer | 2 / 11 | +100 only; 100 | b | Code always +100; XML `Positive Zero`. Small body, long upper shadow, no/very short lower shadow, **gap down** from the prior body. Identical shape test to shooting star; only the gap direction differs. | Source silent. Nison: bullish after a decline (needs confirmation). | yes (body gaps below the prior body) | + bullish |
| 35 | CDLKICKING, kicking | 2 / 11 | +/-100; never fired on real bars (synthetic: -100, 100) | a | Code: sign = colour of the 2nd marubozu (black then white with an upside gap = +). XML `Bull Bear`. | Source silent. Nison: strong reversal; bullish after black then white with an up gap. | yes (gap between shadows) | + bullish, - bearish |
| 36 | CDLKICKINGBYLENGTH, kicking by length | 2 / 11 | +/-100; never fired on real bars (synthetic: -100, 100) | a | Same pattern as kicking, but the sign is the colour of the **longer** marubozu. | As kicking. | yes (gap between shadows) | + bullish, - bearish |
| 37 | CDLLADDERBOTTOM, ladder bottom | 5 / 14 | +100 only; 100 | b | Code always +100; XML `Positive Zero`. Three black bars with lower opens and closes, a black bar with an upper shadow, then a white bar that opens above the 4th body and closes above the 4th high. | Source silent. Nison: bullish bottom reversal. | weak (5th opens above the prior open) | + bullish |
| 38 | CDLLONGLEGGEDDOJI, long legged doji | 1 / 10 | +100 only; 100 | c | Code always +100; XML `Pattern Bool Positive Zero`. Doji body, one or two long shadows. | Source silent. Nison: indecision, neutral. | no | neutral. **EXCEPTION** (raw + vs neutral) |
| 39 | CDLLONGLINE, long line candle | 1 / 10 | +/-100; -100, 100 | a | Code: sign = bar colour; long body, short shadows. XML `Bull Bear`. Colour-only sign (judgement call below). | Source silent. Nison: a long white day shows buying strength, a long black day selling strength. | no | + bullish, - bearish |
| 40 | CDLMARUBOZU, marubozu | 1 / 10 | +/-100; -100, 100 | a | Code: sign = bar colour; long body, no/very short shadows both sides. XML `Bull Bear`. Colour-only sign (judgement call below). | Source silent. Nison: white marubozu bullish, black marubozu bearish. | no | + bullish, - bearish |
| 41 | CDLMATCHINGLOW, matching low | 2 / 6 | +100 only; 100 | b | Code always +100; XML `Positive Zero`. Two black bars with equal closes. | Source silent. Nison: bullish support sign. | no | + bullish |
| 42 | CDLMATHOLD, mat hold | 5 / 14 | +100 only; never fired on real bars (synthetic: +100) | b | Code always +100; XML `Positive Zero`. Long white, upside gap, three small bars holding, white bar closing above the reaction highs. | Source silent. Nison: bullish continuation. | yes (upside body gap 1st to 2nd bar); 5th bar opens above the prior close (weak) | + bullish |
| 43 | CDLMORNINGDOJISTAR, morning doji star | 3 / 12 | +100 only; 100 | b | Code always +100; XML `Positive Zero`. | Source silent. Nison: bullish bottom reversal. | yes (doji body gaps below 1st body) | + bullish |
| 44 | CDLMORNINGSTAR, morning star | 3 / 12 | +100 only; 100 | b | Code always +100; XML `Positive Zero`. | Source silent. Nison: bullish bottom reversal. | yes (star body gaps below 1st body) | + bullish |
| 45 | CDLONNECK, on-neck pattern | 2 / 11 | -100 only; -100 | b | Code always -100; XML `Negative Zero`. White bar opens below the prior low and closes equal to it. | Source silent. Nison: bearish continuation. | yes (opens below the prior low) | - bearish |
| 46 | CDLPIERCING, piercing pattern | 2 / 11 | +100 only; 100 | b | Code always +100; XML `Positive Zero`. Opens below the prior low, closes above the midpoint of the prior body (fixed 0.5). | Source silent. Nison: bullish reversal after a decline. | yes (opens below the prior low) | + bullish |
| 47 | CDLRICKSHAWMAN, rickshaw man | 1 / 10 | +100 only; 100 | c | Code always +100; XML `Pattern Bool Positive Zero`. Doji body, two long shadows, body near the midpoint. | Source silent. Nison: indecision, neutral. | no | neutral. **EXCEPTION** (raw + vs neutral) |
| 48 | CDLRISEFALL3METHODS, rising/falling three methods | 5 / 14 | +/-100; -100, 100 | a | Code: `100 * colour(1st bar)`: white first bar = +100 (rising three), black = -100 (falling three). XML `Bull Bear`. | Source silent. Nison: continuation of the prior trend (rising = bullish, falling = bearish). | weak (5th bar opens beyond the prior close, no size) | + bullish, - bearish |
| 49 | CDLSEPARATINGLINES, separating lines | 2 / 11 | +/-100; -100, 100 | a | Code: sign = colour of the 2nd bar; comment: "second candle: bullish (bearish) belt hold with the same open as the prior candle". | Source comment names the 2nd bar bullish (white) / bearish (black). Nison: continuation of the prior trend. | no (open equals the prior open) | + bullish, - bearish |
| 50 | CDLSHOOTINGSTAR, shooting star | 2 / 11 | -100 only; -100 | b | Code always -100; XML `Negative Zero`. Same shape test as inverted hammer, with a gap **up** from the prior body. | Source silent. Nison: bearish after an advance. | yes (body gaps above the prior body) | - bearish |
| 51 | CDLSHORTLINE, short line candle | 1 / 10 | +/-100; -100, 100 | d | Code: sign = bar colour; short body, short shadows. XML flags only `Positive Negative Zero`, no `Pattern Bull Bear`. | Source silent. Nison: a small bar with no direction value. | no | neutral both signs. **EXCEPTION** (both signs) |
| 52 | CDLSPINNINGTOP, spinning top | 1 / 10 | +/-100; -100, 100 | d | Code: sign = bar colour; comment "small real body, shadows longer than the real body". XML flags only `Positive Negative Zero`, no `Pattern Bull Bear`. | Source silent. Nison: indecision, neutral. | no | neutral both signs. **EXCEPTION** (both signs) |
| 53 | CDLSTALLEDPATTERN, stalled pattern | 3 / 12 | -100 only; -100 | b | Code always -100; XML `Negative Zero`. Three white bars; the third is small and rides near the 2nd body's top. | Source silent. Nison: bearish warning of a stalling advance. | no (gaps allowed but not required) | - bearish |
| 54 | CDLSTICKSANDWICH, stick sandwich | 3 / 7 | +100 only; 100 | b | Code always +100; XML `Positive Zero`. Black, white (low above the 1st close), black with close equal to the 1st close. | Source silent. Nison: bullish (support at the equal closes). | yes (2nd bar's low is above the 1st close, so it opens above it) | + bullish |
| 55 | CDLTAKURI, takuri | 1 / 10 | +100 only; 100 | b | Code always +100; XML `Pattern Bool Positive Zero`. Dragonfly doji with a **very long** lower shadow. | Source silent. Nison/Japanese term: bullish when at a low (a "dragonfly" family member). | no | + bullish (the sign is + but is a bool, no sign hint) |
| 56 | CDLTASUKIGAP, tasuki gap | 3 / 7 | +/-100; -100, 100 | a | Code: sign = colour of the 2nd bar of the pair (white after an upside gap = +100; black after a downside gap = -100). XML `Bull Bear`. | Source silent. Nison: continuation; upside tasuki bullish, downside tasuki bearish. | yes (gap between bodies) | + bullish, - bearish |
| 57 | CDLTHRUSTING, thrusting pattern | 2 / 11 | -100 only; -100 | b | Code always -100; XML `Negative Zero`. White bar opens below the prior low, closes under the prior body's midpoint (fixed 0.5), not equal to the prior close. | Source silent. Nison: bearish continuation. | yes (opens below the prior low) | - bearish |
| 58 | CDLTRISTAR, tristar pattern | 3 / 12 | +/-100; -100, 100 | a | Code: -100 when the 2nd doji gaps up and the 3rd is not higher; +100 when it gaps down and the 3rd is not lower. XML `Bull Bear`. | Source silent. Nison: rare reversal; a star at a top = bearish, at a bottom = bullish. | yes (2nd doji gaps from the 1st) | + bullish, - bearish |
| 59 | CDLUNIQUE3RIVER, unique 3 river | 3 / 12 | +100 only; 100 | b | Code always +100; XML `Positive Zero`. | Source silent. Nison: bullish bottom reversal (rare). | no | + bullish |
| 60 | CDLUPSIDEGAP2CROWS, upside gap two crows | 3 / 12 | -100 only; -100 | b | Code always -100; XML `Negative Zero`. | Source silent. Nison: bearish reversal after an advance. | yes (2nd body gaps above 1st body) | - bearish |
| 61 | CDLXSIDEGAP3METHODS, upside/downside gap three methods | 3 / 2 | +/-100; -100, 100 | a | Code: sign = colour of the 1st bar (white with an upside gap = +100; black with a downside gap = -100). XML `Bull Bear`. | Source silent. Nison: continuation of the gap's direction. | yes (gap between 1st and 2nd bodies) | + bullish, - bearish |

Judgement call: LONGLINE, MARUBOZU and CLOSINGMARUBOZU (and BELTHOLD) have a sign that is only the bar's colour. I kept them in class (a) because TA-Lib's XML flags them `Pattern Bull Bear` and textbooks give a white strong bar a bullish reading and a black one a bearish reading. If you would rather treat colour-only signs as neutral, they join the exception list (up to 4 more exceptions, 8 rows).

## 2. Class counts

| Class | Count | Detectors |
|---|---|---|
| (a) sign is a real hint | 24 | 3INSIDE, 3LINESTRIKE, 3OUTSIDE, ABANDONEDBABY, BELTHOLD, BREAKAWAY, CLOSINGMARUBOZU, COUNTERATTACK, DOJISTAR, ENGULFING, GAPSIDESIDEWHITE, HARAMI, HARAMICROSS, HIKKAKE, HIKKAKEMOD, KICKING, KICKINGBYLENGTH, LONGLINE, MARUBOZU, RISEFALL3METHODS, SEPARATINGLINES, TASUKIGAP, TRISTAR, XSIDEGAP3METHODS |
| (b) one sign, matches tradition | 30 | 2CROWS, 3BLACKCROWS, 3STARSINSOUTH, 3WHITESOLDIERS, ADVANCEBLOCK, CONCEALBABYSWALL, DARKCLOUDCOVER, DRAGONFLYDOJI, EVENINGDOJISTAR, EVENINGSTAR, HAMMER, HANGINGMAN, HOMINGPIGEON, IDENTICAL3CROWS, INNECK, INVERTEDHAMMER, LADDERBOTTOM, MATCHINGLOW, MATHOLD, MORNINGDOJISTAR, MORNINGSTAR, ONNECK, PIERCING, SHOOTINGSTAR, STALLEDPATTERN, STICKSANDWICH, TAKURI, THRUSTING, UNIQUE3RIVER, UPSIDEGAP2CROWS |
| (c) one sign, tradition opposite or neutral | 4 | DOJI, GRAVESTONEDOJI, LONGLEGGEDDOJI, RICKSHAWMAN |
| (d) sign is only colour, pattern neutral | 3 | HIGHWAVE, SHORTLINE, SPINNINGTOP |
| Total | 61 | |

Note on (b): DRAGONFLYDOJI and TAKURI are flagged `Pattern Bool` in the XML, so TA-Lib itself calls the + a plain "found" flag. They are in (b) only because the traditional meaning (bullish) happens to match +.

## 3. Exception list (proposed lean differs from raw sign)

| Function | Raw sign | Proposed lean | Reason |
|---|---|---|---|
| CDLDOJI | +100 | neutral | `Pattern Bool` flag; a doji is indecision |
| CDLLONGLEGGEDDOJI | +100 | neutral | `Pattern Bool` flag; indecision |
| CDLRICKSHAWMAN | +100 | neutral | `Pattern Bool` flag; indecision |
| CDLGRAVESTONEDOJI | +100 | bearish | `Pattern Bool` flag; the shape is the bearish doji (long upper shadow, close at the low) |
| CDLHIGHWAVE | +100 / -100 | neutral / neutral | sign is bar colour only; no `Bull Bear` flag |
| CDLSHORTLINE | +100 / -100 | neutral / neutral | sign is bar colour only; no `Bull Bear` flag |
| CDLSPINNINGTOP | +100 / -100 | neutral / neutral | sign is bar colour only; no `Bull Bear` flag |

That is 7 detectors. No class (a) or (b) detector is an exception. (DRAGONFLYDOJI and TAKURI keep their + as bullish.)

## 4. Python wrapper vs C source

- No behavioural difference found. Every detector's observed values on real and synthetic bars (section appendix) are within the set the C code can write (+/-100, +/-80 for ENGULFING/HARAMI/HARAMICROSS, +/-200 for HIKKAKE/HIKKAKEMOD), and every sign matches the C assignment. `talib.abstract` lookbacks equal the `TA_CDLxxx_Lookback` values I read (spot-checked 3OUTSIDE = 3, XSIDEGAP3METHODS = 2, ENGULFING = 2, HIKKAKE = 5, TRISTAR = 12). Output is an int32 array with 0 for the first `lookback` bars.
- C-comment-versus-code gaps (not wrapper issues): the "Must have" comment of CDLHAMMER/HANGINGMAN says the body must be "below/above or near the lows/highs of the previous candle", which the code applies to the previous bar's low/high only, so it is not a trend check. CDLTRISTAR's "Must have" text says only "3 consecutive doji days, the second doji is a star"; the code decides the sign from which way the 2nd doji gaps.
- Not checked: the wrapper's own source (I only ran it); behaviour with NaN or flat bars (the earlier note recorded that a zero-range bar fires DOJI).

## 5. Price-jump list and span list

Jump = yes (25): 2CROWS, ABANDONEDBABY, BREAKAWAY, CONCEALBABYSWALL, DARKCLOUDCOVER, DOJISTAR, EVENINGDOJISTAR, EVENINGSTAR, GAPSIDESIDEWHITE, INNECK, INVERTEDHAMMER, KICKING, KICKINGBYLENGTH, MATHOLD, MORNINGDOJISTAR, MORNINGSTAR, ONNECK, PIERCING, SHOOTINGSTAR, STICKSANDWICH, TASUKIGAP, THRUSTING, TRISTAR, UPSIDEGAP2CROWS, XSIDEGAP3METHODS.
Weak (strict inequality only, no size): 3LINESTRIKE, LADDERBOTTOM, RISEFALL3METHODS, and MATHOLD's 5th bar.

Spans:
- 1 bar (13): BELTHOLD, CLOSINGMARUBOZU, DOJI, DRAGONFLYDOJI, GRAVESTONEDOJI, HIGHWAVE, LONGLEGGEDDOJI, LONGLINE, MARUBOZU, RICKSHAWMAN, SHORTLINE, SPINNINGTOP, TAKURI.
- 2 bars (19): COUNTERATTACK, DARKCLOUDCOVER, DOJISTAR, ENGULFING, HAMMER, HANGINGMAN, HARAMI, HARAMICROSS, HOMINGPIGEON, INNECK, INVERTEDHAMMER, KICKING, KICKINGBYLENGTH, MATCHINGLOW, ONNECK, PIERCING, SEPARATINGLINES, SHOOTINGSTAR, THRUSTING.
- 3 bars (21): 2CROWS, 3INSIDE, 3OUTSIDE, 3STARSINSOUTH, 3WHITESOLDIERS, ABANDONEDBABY, ADVANCEBLOCK, EVENINGDOJISTAR, EVENINGSTAR, GAPSIDESIDEWHITE, HIKKAKE, IDENTICAL3CROWS, MORNINGDOJISTAR, MORNINGSTAR, STALLEDPATTERN, STICKSANDWICH, TASUKIGAP, TRISTAR, UNIQUE3RIVER, UPSIDEGAP2CROWS, XSIDEGAP3METHODS.
- 4 bars (4): 3BLACKCROWS, 3LINESTRIKE, CONCEALBABYSWALL, HIKKAKEMOD.
- 5 bars (4): BREAKAWAY, LADDERBOTTOM, MATHOLD, RISEFALL3METHODS.

## 6. Could not confirm from the source

- The traditional meanings: the C source says almost nothing about them (see above). The Nison column is from recollection, unverified in this session. The XML flags and the code are the only source-backed sign evidence.
- The `Pattern Bull Bear` / `Pattern Bool` flags are TA-Lib's declaration for GUI/tool use; the C files do not repeat them in comments, so the doji-family "bool" reading rests on the XML.
- Chesler's hikkake description is recalled, not read.
- Real-bar firing of six detectors (3STARSINSOUTH, ABANDONEDBABY, CONCEALBABYSWALL, KICKING, KICKINGBYLENGTH, MATHOLD) was zero on about 261,000 real 15-minute bars; their signs were confirmed only on synthetic gappy bars.
- The jump definition is mine (the brief did not define it); the weak category exists to show the cases where it is arguable.

## Appendix: observed values on real 15-minute bars

Output of `docs/research/ta-lib-all-detectors-observed.py` (talib 0.8.3). Format `value:count` pooled over the five assets; the last column gives fires per asset and the distinct values seen.

| function | display name | lookback | observed values, all assets (value:count) | per asset: fires (distinct values) |
|---|---|---|---|---|
| CDL2CROWS | Two Crows | 12 | -100:23 | SPY: 7 (-100); AAPL: 5 (-100); JPM: 2 (-100); XOM: 8 (-100); BTCUSDT: 1 (-100) |
| CDL3BLACKCROWS | Three Black Crows | 13 | -100:46 | SPY: 2 (-100); AAPL: 8 (-100); JPM: 7 (-100); XOM: 5 (-100); BTCUSDT: 24 (-100) |
| CDL3INSIDE | Three Inside Up/Down | 12 | -100:869, 100:882 | SPY: 243 (-100,100); AAPL: 212 (-100,100); JPM: 201 (-100,100); XOM: 193 (-100,100); BTCUSDT: 902 (-100,100) |
| CDL3LINESTRIKE | Three-Line Strike | 8 | -100:393, 100:359 | SPY: 88 (-100,100); AAPL: 90 (-100,100); JPM: 82 (-100,100); XOM: 71 (-100,100); BTCUSDT: 421 (-100,100) |
| CDL3OUTSIDE | Three Outside Up/Down | 3 | -100:4794, 100:4806 | SPY: 1323 (-100,100); AAPL: 1295 (-100,100); JPM: 1185 (-100,100); XOM: 1106 (-100,100); BTCUSDT: 4691 (-100,100) |
| CDL3STARSINSOUTH | Three Stars In The South | 12 | never fired | SPY: 0 (); AAPL: 0 (); JPM: 0 (); XOM: 0 (); BTCUSDT: 0 () |
| CDL3WHITESOLDIERS | Three Advancing White Soldiers | 12 | 100:322 | SPY: 33 (100); AAPL: 37 (100); JPM: 38 (100); XOM: 34 (100); BTCUSDT: 180 (100) |
| CDLABANDONEDBABY | Abandoned Baby | 12 | never fired | SPY: 0 (); AAPL: 0 (); JPM: 0 (); XOM: 0 (); BTCUSDT: 0 () |
| CDLADVANCEBLOCK | Advance Block | 12 | -100:3498 | SPY: 454 (-100); AAPL: 379 (-100); JPM: 392 (-100); XOM: 375 (-100); BTCUSDT: 1898 (-100) |
| CDLBELTHOLD | Belt-hold | 10 | -100:22068, 100:22441 | SPY: 4204 (-100,100); AAPL: 4189 (-100,100); JPM: 4310 (-100,100); XOM: 4435 (-100,100); BTCUSDT: 27371 (-100,100) |
| CDLBREAKAWAY | Breakaway | 14 | -100:2, 100:1 | SPY: 0 (); AAPL: 0 (); JPM: 2 (-100,100); XOM: 1 (-100); BTCUSDT: 0 () |
| CDLCLOSINGMARUBOZU | Closing Marubozu | 10 | -100:17245, 100:19781 | SPY: 3907 (-100,100); AAPL: 3829 (-100,100); JPM: 3925 (-100,100); XOM: 3955 (-100,100); BTCUSDT: 21410 (-100,100) |
| CDLCONCEALBABYSWALL | Concealing Baby Swallow | 13 | never fired | SPY: 0 (); AAPL: 0 (); JPM: 0 (); XOM: 0 (); BTCUSDT: 0 () |
| CDLCOUNTERATTACK | Counterattack | 11 | -100:3, 100:2 | SPY: 0 (); AAPL: 1 (100); JPM: 2 (-100,100); XOM: 2 (-100); BTCUSDT: 0 () |
| CDLDARKCLOUDCOVER | Dark Cloud Cover | 11 | -100:96 | SPY: 15 (-100); AAPL: 17 (-100); JPM: 34 (-100); XOM: 21 (-100); BTCUSDT: 9 (-100) |
| CDLDOJI | Doji | 10 | 100:35119 | SPY: 3786 (100); AAPL: 4063 (100); JPM: 3885 (100); XOM: 3722 (100); BTCUSDT: 19663 (100) |
| CDLDOJISTAR | Doji Star | 11 | -100:1336, 100:1100 | SPY: 387 (-100,100); AAPL: 386 (-100,100); JPM: 380 (-100,100); XOM: 335 (-100,100); BTCUSDT: 948 (-100,100) |
| CDLDRAGONFLYDOJI | Dragonfly Doji | 10 | 100:4983 | SPY: 403 (100); AAPL: 493 (100); JPM: 534 (100); XOM: 524 (100); BTCUSDT: 3029 (100) |
| CDLENGULFING | Engulfing Pattern | 2 | -100:9858, -80:12365, 80:12270, 100:9583 | SPY: 3925 (-100,-80,80,100); AAPL: 3897 (-100,-80,80,100); JPM: 3716 (-100,-80,80,100); XOM: 3855 (-100,-80,80,100); BTCUSDT: 28683 (-100,-80,80,100) |
| CDLEVENINGDOJISTAR | Evening Doji Star | 12 | -100:290 | SPY: 43 (-100); AAPL: 52 (-100); JPM: 38 (-100); XOM: 29 (-100); BTCUSDT: 128 (-100) |
| CDLEVENINGSTAR | Evening Star | 12 | -100:869 | SPY: 120 (-100); AAPL: 128 (-100); JPM: 124 (-100); XOM: 104 (-100); BTCUSDT: 393 (-100) |
| CDLGAPSIDESIDEWHITE | Up/Down-gap side-by-side white lines | 7 | -100:8, 100:253 | SPY: 43 (-100,100); AAPL: 31 (-100,100); JPM: 47 (-100,100); XOM: 45 (-100,100); BTCUSDT: 95 (100) |
| CDLGRAVESTONEDOJI | Gravestone Doji | 10 | 100:4611 | SPY: 353 (100); AAPL: 475 (100); JPM: 536 (100); XOM: 499 (100); BTCUSDT: 2748 (100) |
| CDLHAMMER | Hammer | 11 | 100:7468 | SPY: 602 (100); AAPL: 751 (100); JPM: 821 (100); XOM: 826 (100); BTCUSDT: 4468 (100) |
| CDLHANGINGMAN | Hanging Man | 11 | -100:4339 | SPY: 456 (-100); AAPL: 443 (-100); JPM: 417 (-100); XOM: 447 (-100); BTCUSDT: 2576 (-100) |
| CDLHARAMI | Harami Pattern | 11 | -100:4876, -80:6070, 80:5961, 100:4728 | SPY: 1873 (-100,-80,80,100); AAPL: 1806 (-100,-80,80,100); JPM: 1749 (-100,-80,80,100); XOM: 1847 (-100,-80,80,100); BTCUSDT: 14360 (-100,-80,80,100) |
| CDLHARAMICROSS | Harami Cross Pattern | 11 | -100:1147, -80:1345, 80:1244, 100:1099 | SPY: 473 (-100,-80,80,100); AAPL: 484 (-100,-80,80,100); JPM: 487 (-100,-80,80,100); XOM: 475 (-100,-80,80,100); BTCUSDT: 2916 (-100,-80,80,100) |
| CDLHIGHWAVE | High-Wave Candle | 10 | -100:14536, 100:15242 | SPY: 3533 (-100,100); AAPL: 3545 (-100,100); JPM: 3290 (-100,100); XOM: 3107 (-100,100); BTCUSDT: 16303 (-100,100) |
| CDLHIKKAKE | Hikkake Pattern | 5 | -200:3345, -100:14104, 100:13629, 200:3364 | SPY: 2931 (-200,-100,100,200); AAPL: 3121 (-200,-100,100,200); JPM: 2985 (-200,-100,100,200); XOM: 3005 (-200,-100,100,200); BTCUSDT: 22400 (-200,-100,100,200) |
| CDLHIKKAKEMOD | Modified Hikkake Pattern | 10 | -200:34, -100:153, 100:157, 200:44 | SPY: 13 (-200,-100,100); AAPL: 30 (-200,-100,100,200); JPM: 24 (-200,-100,100,200); XOM: 24 (-200,-100,100,200); BTCUSDT: 297 (-200,-100,100,200) |
| CDLHOMINGPIGEON | Homing Pigeon | 11 | 100:127 | SPY: 26 (100); AAPL: 26 (100); JPM: 40 (100); XOM: 21 (100); BTCUSDT: 14 (100) |
| CDLIDENTICAL3CROWS | Identical Three Crows | 12 | -100:626 | SPY: 39 (-100); AAPL: 57 (-100); JPM: 57 (-100); XOM: 70 (-100); BTCUSDT: 403 (-100) |
| CDLINNECK | In-Neck Pattern | 11 | -100:37 | SPY: 4 (-100); AAPL: 8 (-100); JPM: 13 (-100); XOM: 10 (-100); BTCUSDT: 2 (-100) |
| CDLINVERTEDHAMMER | Inverted Hammer | 11 | 100:1414 | SPY: 196 (100); AAPL: 183 (100); JPM: 197 (100); XOM: 183 (100); BTCUSDT: 655 (100) |
| CDLKICKING | Kicking | 11 | never fired | SPY: 0 (); AAPL: 0 (); JPM: 0 (); XOM: 0 (); BTCUSDT: 0 () |
| CDLKICKINGBYLENGTH | Kicking - bull/bear determined by the longer marubozu | 11 | never fired | SPY: 0 (); AAPL: 0 (); JPM: 0 (); XOM: 0 (); BTCUSDT: 0 () |
| CDLLADDERBOTTOM | Ladder Bottom | 14 | 100:44 | SPY: 6 (100); AAPL: 12 (100); JPM: 10 (100); XOM: 15 (100); BTCUSDT: 1 (100) |
| CDLLONGLEGGEDDOJI | Long Legged Doji | 10 | 100:35032 | SPY: 3779 (100); AAPL: 4061 (100); JPM: 3883 (100); XOM: 3716 (100); BTCUSDT: 19593 (100) |
| CDLLONGLINE | Long Line Candle | 10 | -100:23708, 100:25591 | SPY: 5498 (-100,100); AAPL: 5377 (-100,100); JPM: 5283 (-100,100); XOM: 5166 (-100,100); BTCUSDT: 27975 (-100,100) |
| CDLMARUBOZU | Marubozu | 10 | -100:7040, 100:7765 | SPY: 1258 (-100,100); AAPL: 1393 (-100,100); JPM: 1532 (-100,100); XOM: 1529 (-100,100); BTCUSDT: 9093 (-100,100) |
| CDLMATCHINGLOW | Matching Low | 6 | 100:3882 | SPY: 382 (100); AAPL: 429 (100); JPM: 392 (100); XOM: 412 (100); BTCUSDT: 2267 (100) |
| CDLMATHOLD | Mat Hold | 14 | never fired | SPY: 0 (); AAPL: 0 (); JPM: 0 (); XOM: 0 (); BTCUSDT: 0 () |
| CDLMORNINGDOJISTAR | Morning Doji Star | 12 | 100:232 | SPY: 34 (100); AAPL: 33 (100); JPM: 35 (100); XOM: 37 (100); BTCUSDT: 93 (100) |
| CDLMORNINGSTAR | Morning Star | 12 | 100:838 | SPY: 109 (100); AAPL: 125 (100); JPM: 114 (100); XOM: 105 (100); BTCUSDT: 385 (100) |
| CDLONNECK | On-Neck Pattern | 11 | -100:50 | SPY: 6 (-100); AAPL: 12 (-100); JPM: 19 (-100); XOM: 11 (-100); BTCUSDT: 2 (-100) |
| CDLPIERCING | Piercing Pattern | 11 | 100:76 | SPY: 11 (100); AAPL: 16 (100); JPM: 22 (100); XOM: 23 (100); BTCUSDT: 4 (100) |
| CDLRICKSHAWMAN | Rickshaw Man | 10 | 100:24847 | SPY: 2837 (100); AAPL: 3003 (100); JPM: 2814 (100); XOM: 2640 (100); BTCUSDT: 13553 (100) |
| CDLRISEFALL3METHODS | Rising/Falling Three Methods | 14 | -100:41, 100:57 | SPY: 10 (-100,100); AAPL: 15 (-100,100); JPM: 10 (-100,100); XOM: 12 (-100,100); BTCUSDT: 51 (-100,100) |
| CDLSEPARATINGLINES | Separating Lines | 11 | -100:788, 100:704 | SPY: 145 (-100,100); AAPL: 142 (-100,100); JPM: 151 (-100,100); XOM: 150 (-100,100); BTCUSDT: 904 (-100,100) |
| CDLSHOOTINGSTAR | Shooting Star | 11 | -100:1751 | SPY: 238 (-100); AAPL: 245 (-100); JPM: 301 (-100); XOM: 212 (-100); BTCUSDT: 755 (-100) |
| CDLSHORTLINE | Short Line Candle | 10 | -100:21167, 100:22334 | SPY: 4127 (-100,100); AAPL: 4595 (-100,100); JPM: 4655 (-100,100); XOM: 4657 (-100,100); BTCUSDT: 25467 (-100,100) |
| CDLSPINNINGTOP | Spinning Top | 10 | -100:25248, 100:26019 | SPY: 6063 (-100,100); AAPL: 5912 (-100,100); JPM: 5587 (-100,100); XOM: 5277 (-100,100); BTCUSDT: 28428 (-100,100) |
| CDLSTALLEDPATTERN | Stalled Pattern | 12 | -100:841 | SPY: 127 (-100); AAPL: 112 (-100); JPM: 108 (-100); XOM: 112 (-100); BTCUSDT: 382 (-100) |
| CDLSTICKSANDWICH | Stick Sandwich | 7 | 100:45 | SPY: 6 (100); AAPL: 11 (100); JPM: 13 (100); XOM: 9 (100); BTCUSDT: 6 (100) |
| CDLTAKURI | Takuri (Dragonfly Doji with very long lower shadow) | 10 | 100:4861 | SPY: 399 (100); AAPL: 483 (100); JPM: 511 (100); XOM: 514 (100); BTCUSDT: 2954 (100) |
| CDLTASUKIGAP | Tasuki Gap | 7 | -100:45, 100:40 | SPY: 17 (-100,100); AAPL: 11 (-100,100); JPM: 33 (-100,100); XOM: 18 (-100,100); BTCUSDT: 6 (-100,100) |
| CDLTHRUSTING | Thrusting Pattern | 11 | -100:184 | SPY: 25 (-100); AAPL: 39 (-100); JPM: 59 (-100); XOM: 51 (-100); BTCUSDT: 10 (-100) |
| CDLTRISTAR | Tristar Pattern | 12 | -100:29, 100:15 | SPY: 8 (-100,100); AAPL: 6 (-100,100); JPM: 15 (-100,100); XOM: 6 (-100,100); BTCUSDT: 9 (-100,100) |
| CDLUNIQUE3RIVER | Unique 3 River | 12 | 100:20 | SPY: 4 (100); AAPL: 4 (100); JPM: 5 (100); XOM: 3 (100); BTCUSDT: 4 (100) |
| CDLUPSIDEGAP2CROWS | Upside Gap Two Crows | 12 | -100:3 | SPY: 1 (-100); AAPL: 1 (-100); JPM: 1 (-100); XOM: 0 (); BTCUSDT: 0 () |
| CDLXSIDEGAP3METHODS | Upside/Downside Gap Three Methods | 2 | -100:861, 100:817 | SPY: 237 (-100,100); AAPL: 273 (-100,100); JPM: 273 (-100,100); XOM: 226 (-100,100); BTCUSDT: 669 (-100,100) |

