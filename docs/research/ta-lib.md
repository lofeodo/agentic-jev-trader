# TA-Lib: installation, detector names, and behavior on 15-minute bars

Research for issue #12 (map #7). Read on 2026-11-11. Brief: `docs/project-breakdown.md` section 12.4.

## Sources and method

- TA-Lib C source, tag v0.8.3 (the C core in the 0.8.3 wheel), `src/ta_func/ta_CDL*.c`: https://github.com/TA-Lib/ta-lib/tree/v0.8.3/src/ta_func . Main (commit fd57d4c, 2026-11-10) has since been refactored into macro-expanded form; for the detectors I compared (hammer, hanging man, engulfing, harami) the logic is equivalent. Candle-setting defaults: `src/ta_common/ta_global.c` (identical on tag and main), macro `TA_CANDLE_DEFAULT_SETTINGS`: https://github.com/TA-Lib/ta-lib/blob/main/src/ta_common/ta_global.c
- Python wrapper README: https://github.com/TA-Lib/ta-lib-python , release v0.8.3 dated 2026-10-28. PyPI: https://pypi.org/project/TA-Lib/ (JSON API read 2026-11-11). conda-forge: https://anaconda.org/conda-forge/ta-lib (API read 2026-11-11).
- Empirical checks: throwaway env (`conda create -p <scratch dir> python=3.14`, then `pip install TA-Lib`) with TA-Lib 0.8.3, C core reported as `0.8.3 (Oct 28 2026 21:54:29)`, Python 3.14.10 on Windows 11. Hand-built bars (details in section 5). None of the developer's environments was touched.

## 1. Installation

| Target | Method | Evidence |
|---|---|---|
| Windows, pip | `python -m pip install TA-Lib`. Prebuilt wheel `ta_lib-0.8.3-cp314-cp314-win_amd64.whl` (also cp39 to cp314, win32, win_arm64). No compiler or separate C library needed. I ran this in a fresh py3.14 conda env: it installed from the wheel, `import talib` worked, 61 pattern functions. | PyPI file list 2026-11-11; README: "Binary wheels include the TA-Lib C library"; "Starting with version 0.8.3, this library is statically linked into the extension." |
| Windows, conda | `conda install -c conda-forge ta-lib`. conda-forge has `ta-lib 0.8.3` for win-64 py311 to py315 (uploaded 2026-10-29), depending on `libta-lib >=0.8.3`. | anaconda.org API 2026-11-11 |
| Linux container | `pip install TA-Lib` in a plain Python image: wheels exist for `manylinux_2_28` x86_64 and aarch64 and for `musllinux_1_2` (Alpine), cp39 to cp314. No apt packages needed. Source builds need Python headers and a C toolchain (README mentions `python3-dev`). I did not run Docker, so the Linux install is verified from the file list only. | PyPI file list; README |
| Python version | Wrapper supports 3.9 to 3.14 (classifiers; `requires_python >=3.9`); 3.14 wheels exist, so machine Python 3.14 works. | PyPI, README |

Suggested pin: `TA-Lib==0.8.3` in `requirements.txt`. Pip inside the project conda env is the simplest identical path for Windows and Linux. Pin because main has been refactored since the 0.8.3 tag; re-run the detector tests before upgrading.

## 2. How TA-Lib defines the shapes

Default candle settings (`ta_global.c`, `TA_CANDLE_DEFAULT_SETTINGS`):

- BodyLong: body > average body of the previous 10 candles. BodyVeryLong: 3x that. BodyShort: body < average body of the previous 10.
- BodyDoji: body <= 0.1 x average high-low range of the previous 10.
- ShadowLong: shadow > the real body. ShadowVeryLong: > 2x body.
- ShadowVeryShort: shadow < 0.1 x average high-low range of the previous 10.
- Near: <= 0.2 x average high-low range of the previous 5. Far: >= 0.6x. Equal: <= 0.05x.
- "Average of previous N" excludes the current candle. So a detector returns 0 for the first `lookback` bars of the array. Lookbacks (from `abstract.Function(...).lookback`): 10 for DOJI, DRAGONFLYDOJI, GRAVESTONEDOJI, SPINNINGTOP, MARUBOZU; 11 for HAMMER, HANGINGMAN, INVERTEDHAMMER, SHOOTINGSTAR, HARAMI, PIERCING, DARKCLOUDCOVER; 12 for MORNINGSTAR, EVENINGSTAR, 3INSIDE, 3WHITESOLDIERS; 13 for 3BLACKCROWS; 14 for RISEFALL3METHODS; 2 for ENGULFING. Feed one continuous multi-day series, not one array per day, or the first 10 to 14 bars of each day are blank.
- Output is an `int` array, 0 meaning none. Sign conventions below were confirmed on the 0.8.3 wheel.
- No detector looks at more than the 1 to 4 bars of its own pattern plus the averaging window. None tests a multi-bar trend.

## 3. Table: playbook detectors (section 12.4)

"Trend check" is whether the detector itself requires a prior move. "Gap" is what TA-Lib requires between bars. Source: `ta_CDLxxx.c` on tag v0.8.3, the "Must have" comment and the condition under it.

| Detector | Exists | Output and sign | Trend check in detector | Gap required | On 15-min bars inside a day |
|---|---|---|---|---|---|
| CDLDOJI | yes | +100 or 0, never negative, no direction. Body <= 0.1 x avg range of previous 10. | none | no | Common. Also fires on a zero-range bar (open=high=low=close returned 100; tested), so filter flat bars. |
| CDLDRAGONFLYDOJI | yes | +100 or 0. Doji body, upper shadow < 0.1 x avg range, lower shadow > that threshold. | none | no | Fires; about 1 doji in 7 is a dragonfly (synthetic data). |
| CDLGRAVESTONEDOJI | yes | +100 or 0. Mirror of the above. Positive although the playbook calls it bearish. | none | no | Same as dragonfly. |
| CDLSPINNINGTOP | yes | +100 if bar is up (close >= open), -100 if down. Colour only, not a bullish/bearish call. Body short and both shadows longer than the body. | none | no | Very common. |
| CDLMARUBOZU | yes | +100 up bar, -100 down bar. Body long, both shadows < 0.1 x avg range. | none | no | Fires. |
| CDLHAMMER | yes | +100 or 0. Small body, lower shadow > body, upper shadow very short, and body's low <= previous bar's low + Near. | previous bar only (proxy, see below) | no | Fires, no gap needed. |
| CDLHANGINGMAN | yes | -100 or 0. Same shape; body's low >= previous bar's high - Near. | previous bar only | no | Fires, rarer than hammer (needs body near previous bar's high). |
| CDLINVERTEDHAMMER | yes | +100 or 0. Small body, long upper shadow, very short lower shadow, body gaps down (open and close both below previous open and close). | previous bar only, as a gap | yes (body gap down) | Only at the open or after a jump. Synthetic 10,400 bars: 7 fires, all on the first bar of a day. |
| CDLSHOOTINGSTAR | yes | -100 or 0. Same shape; body gaps up (open and close both above previous open and close). | previous bar only, as a gap | yes (body gap up) | Same: 7 fires, all on the first bar of a day. |
| CDLENGULFING | yes | +100 bullish (up bar engulfs previous down body), -100 bearish. +80 / -80 when one end of the body equals the previous bar's close or open (touching). Tag file lines 130-160. | none. No size test either: a tiny previous bar can be "engulfed" by anything. | no | Very common (about 24% of bars in the synthetic run), so weak alone. |
| CDLHARAMI | yes | Sign is opposite the first bar's colour: +100 when first bar is down (bullish), -100 when first is up (bearish). 100 when the second body is strictly inside the first, 80 / -80 when touching. First body long, second body short (<= average). Compares bodies only; shadows may stick out. A doji works as the second bar. | none | no | Common. |
| CDLPIERCING | yes | +100 or 0. First bar down and long, second up and long, second open < first bar's LOW (shadow gap), close above the midpoint of the first body and below its open. Midpoint fixed at 0.5. | none | yes (open below previous low) | Rare. Tested: open equal to previous close returns 0. 1 fire in 10,400 synthetic bars (day open). |
| CDLDARKCLOUDCOVER | yes | -100 or 0. First bar up and long, second down with open > first bar's HIGH, close inside first body below penetration (parameter `penetration`, default 0.5). | none | yes (open above previous high) | Rare. Tested: open equal to previous close returns 0. 0 fires synthetic. |
| CDLMORNINGSTAR | yes | +100 or 0. Long down bar, short star whose whole body is below both the first bar's open and close, then an up bar closing above first close + 0.3 x first body (parameter `penetration`, default 0.3) and longer than "short". | none | yes (body gap down on the star) | Rare. Tested: a version with no body gap returns 0. 0 fires synthetic. |
| CDLEVENINGSTAR | yes | -100 or 0. Mirror; body gap up on the star; penetration default 0.3. | none | yes (body gap up) | Rare. 1 fire synthetic. |
| CDL3INSIDE | yes | +100 (first bar down, third bar up closing above first bar's OPEN) or -100 (mirror). Sign is the third bar's direction. First long, second short and inside the first body (touching allowed), third of opposite colour closing beyond first open. | none | no | No gap needed but needs a long, a short and a full-size bar. 2 fires in 10,400 synthetic bars. |
| CDL3WHITESOLDIERS | yes | +100 or 0. Three up bars, rising closes, each opens above the previous open and no higher than previous close + Near, very short upper shadows, each body not far shorter than the previous. | none (it is itself a run) | no | Works on continuous bars (open equal to previous close passes; tested). 12 fires synthetic. |
| CDL3BLACKCROWS | yes | -100 or 0. Needs a white bar immediately before the three black bars; first crow closes under that white bar's high; each crow opens strictly inside the previous crow's body (open < previous open and open > previous close); declining closes; very short lower shadows. | one prior up bar | no gap, but opens must be STRICTLY inside the previous body: tested, crows opening exactly at the previous close returned 0 | Rare. 0 fires synthetic. Depends on whether the feed has opens exactly equal to the previous close. |
| CDLRISEFALL3METHODS | yes | +100 rising three, -100 falling three; sign is the first bar's colour. Exactly three small bars; long first and last bars of the same colour, middle three of the opposite colour. | none | no gap; final bar must open above (below) the previous close | Needs 5 specific bars. 0 fires synthetic. |

Hammer vs hanging man, inverted hammer vs shooting star. TA-Lib does not distinguish by trend. Hammer and hanging man use identical shape tests; they differ only in the comparison with the previous bar: hammer needs the body's low <= previous low + Near, hanging man needs the body's low >= previous high - Near (source comments "rb near the prior candle's lows / highs": tag v0.8.3 `ta_CDLHAMMER.c` line 189 and `ta_CDLHANGINGMAN.c` line 189; Near = 0.2 x average range of previous 5 bars). A hammer-shaped bar after six down bars returned +100 (hammer), after six up bars -100 (hanging man), and after a flat sequence neither. Inverted hammer and shooting star use identical shape tests and differ only in gap direction: body gapping down gives CDLINVERTEDHAMMER (+100), body gapping up gives CDLSHOOTINGSTAR (-100). An inverted-hammer shape after an advance with a gap down returned CDLINVERTEDHAMMER, so the name tracks the gap, not the trend. The playbook's "must follow a decline/advance" is NOT enforced by any detector; the snapshot code must compute trend itself and combine it with the signed output.

## 4. Findings that matter for the design

1. All 19 detectors named in 12.4 exist in 0.8.3 (61 pattern functions in total). Tweezers have no entry in the brief's detector list (custom code).
2. None checks a prior trend. Hammer/hanging man use the previous bar as a weak proxy; 3 black crows needs one prior up bar; stars, shooting star and inverted hammer need a gap. The section 12.1 trend context features are the only real trend gate.
3. Two-direction detectors are separated by sign: ENGULFING, HARAMI (+bullish, -bearish), 3INSIDE and RISEFALL3METHODS (+up, -down). 80 vs 100 is touching vs strict, so use `>0` and `<0` for direction. The brief's two-entry storage maps to the sign.
4. Gap-dependent: INVERTEDHAMMER, SHOOTINGSTAR (body gap), PIERCING (open below previous low), DARKCLOUDCOVER (open above previous high), MORNINGSTAR, EVENINGSTAR (star body gap). With open near the previous close these fire essentially only on the first bar of a day or after news gaps. CDL3BLACKCROWS is strict about opens inside previous bodies and also fires rarely.
5. Fine intraday: the DOJI family, SPINNINGTOP, MARUBOZU, HAMMER, HANGINGMAN, ENGULFING, HARAMI, 3INSIDE, 3WHITESOLDIERS, RISEFALL3METHODS (rare by construction).
6. Warm-up is 10 to 14 bars, and on a continuous series the averaging window spans the overnight gap, which inflates "average range" on the first bars of a day.

## 5. Empirical check details

Each pattern was a hand-built bar sequence appended after 15 neutral alternating bars, called as `talib.CDLxxx(open, high, low, close)`; outputs are quoted above. A synthetic intraday series (400 days of 26 bars, 0.6% overnight gaps, random intraday moves, no intraday jumps) gave the firing counts. They are illustrative only: real data has intraday jumps, different wick sizes and different open-equals-previous-close behavior. A later ticket should measure fire rates on real 15-minute bars.

Synthetic counts over 10,400 bars: DOJI 1479, SPINNINGTOP 2368, ENGULFING 2503, HARAMI 1170, HAMMER 286, HANGINGMAN 122, MARUBOZU 293, DRAGONFLY 222, GRAVESTONE 219, 3WHITESOLDIERS 12, INVERTEDHAMMER 7, SHOOTINGSTAR 7, 3INSIDE 2, PIERCING 1, EVENINGSTAR 1, DARKCLOUDCOVER 0, MORNINGSTAR 0, 3BLACKCROWS 0, RISEFALL3METHODS 0.

## 6. Could not verify

- Linux wheel install in an actual container (Docker not run; wheel availability read from PyPI).
- Behavior on real 15-minute data (synthetic only).
- That main's refactored source behaves identically to v0.8.3 for every detector (compared hammer, hanging man, engulfing, harami; behavior tests ran on the 0.8.3 wheel).
