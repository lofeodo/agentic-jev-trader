# Candle patterns come from TA-Lib unmodified, all 61, on three bar sizes

A candle pattern is a named shape of one to five bars that traders read as a hint about where the price goes next; a "hammer", for example, is a bar that fell from $100.20 to $99.20 and recovered to close at $100.30. The agent needs code that recognises these shapes, and TA-Lib is the standard library for it, with 61 pattern detectors. We decided to take every one of the 61 exactly as TA-Lib (pinned to version 0.8.3) defines it, with no adjustments and no detectors of our own, and to run the same detectors on three bar sizes: the 15-minute bars the agent decides on, and the hourly bars and daily bars built from them, the way a day trader checks the bigger picture before reading the chart they trade on. We chose this because reliability comes first: a standard tool used as it comes leaves no settings of ours to defend, and the agent's own track record, not our judgment, is what tests whether a pattern is worth anything.

## Considered Options

- **A hand-picked list of 23 well-known patterns** (the original brief's). Rejected: the list was arbitrary, and nothing made those 23 better than the other 38.
- **Our own check that the price had been falling or rising before the shape.** The textbook says a hammer only counts after a fall, and TA-Lib does not check. Rejected: it needs our own detectors and several numbers we would have to pick, and on the first dataset's bars the stricter names showed no sign of predicting the next price better than the plain ones. Jev is told separately whether the price has been rising or falling.
- **Loosening the 25 patterns that need the price to jump between two bars.** TA-Lib was written for daily bars, where each day opens away from the last close. Inside a day a 15-minute bar opens where the last one closed, so these patterns rarely appear there, and six never appeared once in over four years. Rejected in favour of the daily bars, where they work as designed.
- **Dropping patterns for being very common or very rare.** Rejected: a rare pattern costs nothing, and how much a common one is worth is for the track record to show.
- **Choosing patterns by how they would have traded in the past.** Never: it fits the list to history and flatters every later result.

## Consequences

- Something is recognised on about four 15-minute bars in five, often several names at once, and some names are near-copies that land on the same bars (three kinds of doji). All are listed; there are no tie-break rules.
- Jev reads three lists: 15-minute patterns from the last four steps, each with its age; patterns on the latest finished hourly bar; patterns on the latest finished daily bar. Only finished bars count, so a day's pattern is never seen before the day ends.
- A 15-minute or hourly pattern never stretches across a missing bar or a stock's overnight close. A daily pattern runs across consecutive days with bars, since the overnight jump is what those patterns were designed around.
- Each pattern's lean (bullish, bearish, or neutral) is TA-Lib's own plus or minus sign, except for seven detectors whose sign is not a hint. Six are neutral: doji, long-legged doji, rickshaw man, high wave, short line, and spinning top. Gravestone doji is bearish although TA-Lib reports it as plus.
- The track record and the LLM's search filter use the 15-minute list only. The hourly and daily names are background that Jev reads.
- Memories are filed under these names, so changing the list or the TA-Lib version later means a new dataset and starting memory again.
