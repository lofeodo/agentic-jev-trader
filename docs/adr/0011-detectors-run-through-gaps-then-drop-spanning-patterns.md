# Detectors run through every gap; a pattern that spans one is dropped afterwards

A candle pattern detector compares its shape against averages of the 10 to 14 bars before it, and a 15-minute or hourly pattern must never stand on bars either side of a missing bar or a stock's overnight close (ADR 0005). We decided to run each TA-Lib detector once over an asset's whole series of bars, as if the bars followed one another, and then drop every 15-minute or hourly pattern whose bars cross a break. A break is any place where two 15-minute bars in a row are not 15 minutes apart. For an hourly pattern, the break can fall between or inside its hourly bars. Daily patterns are never dropped. We chose this because a day trader reads the first bars of the morning against what the market did yesterday: cutting the series at each overnight close would leave a stock's first 10 to 14 bars of every session, its whole first three hours, with no patterns at all.

## Considered Options

- **Cut the series at every break and run the detectors on each piece.** Rejected: the averages restart after every break, so nothing is recognised at the open, the busiest time of a stock's day.

## Consequences

- The averages behind a morning bar's pattern include the previous session's bars. TA-Lib's own output is untouched; only whole patterns are dropped.
- How many bars a pattern stands on comes from TA-Lib's source: 1 to 5 bars per detector. A hikkake confirmation (TA-Lib's ±200) stands on its shape and on the up to three bars since the shape ended, so it is dropped when a break falls anywhere in that stretch.
- An hourly bar missing a 15-minute bar at its very start or end, such as a stock's first hour, which holds only two bars, is still a whole hourly bar: only a break inside the stretch a pattern covers drops it.
