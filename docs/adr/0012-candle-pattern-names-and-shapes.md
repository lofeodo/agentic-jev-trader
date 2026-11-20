# Candle pattern names are TA-Lib's own in lower case; shapes are TA-Lib's comments in plain words

A candle pattern is a named shape of one to five bars, and each has a lean: bullish (a hint the price will rise), bearish (a hint it will fall) or neutral (no hint either way). "Bullish engulfing", for example, is a falling bar from $101.00 to $100.00, then a rising bar from $99.50 to $101.50 that covers it. The playbook is the list of every candle pattern with its name, lean and shape. The spec says names are written as TA-Lib gives them and that each shape is TA-Lib's own description, but it leaves the exact rule open.

We decided that a name is TA-Lib's display name in lower case, without a trailing "pattern", with "bullish" or "bearish" in front when one detector gives both a rising and a falling version. `CDLENGULFING`, which TA-Lib calls "Engulfing Pattern", gives "bullish engulfing" and "bearish engulfing". `CDLHAMMER` only ever reports a rise, so it gives just "hammer". "Stalled Pattern" keeps its last word, since "stalled" alone is not a name. Which leans a detector can give is read from TA-Lib's own function listing, which states whether its result can be positive or negative. That makes 85 candle patterns from the 61 detectors.

Each shape restates the "must have" comment at the top of the detector's TA-Lib source file (version 0.8.3) in plain sentences, with the words the walkthrough pages use. An up bar closes above where it opened, a down bar below. The body is the part between the open and the close: $100.00 to $101.00 for a bar that opens at $100.00 and closes at $101.00. A wick is the part of the bar's range above or below the body: if the same bar touched $101.40, its upper wick is $0.40 long. A jump is a gap between one bar and the next, such as a close at $100.00 and the next open at $100.50. A doji is a bar that closes almost where it opened. We chose this because it matches how the walkthrough pages already write names, and TA-Lib's comments use candle jargon ("white real body", "window", "marubozu") that Jev, the LLM and the developer should not have to decode.

## Considered Options

- **TA-Lib's display names as they stand** ("Engulfing Pattern"). Rejected: they carry no lean, so "bullish engulfing" and its bearish twin would share a name.
- **Copying TA-Lib's comments word for word.** Rejected: jargon, and one comment describes both versions at once ("white (black) real body").

## Consequences

- Some names read awkwardly because TA-Lib's do, such as "bullish three inside up/down" and "bullish kicking - bull/bear determined by the longer marubozu". They are kept: the names are not ours to fix.
- The walkthrough pages' made-up notes differ from the real playbook in places. They write "belt-hold" with no lean, and their shape sentences add detail such as "a lower wick at least twice as long". The pages are brought into line by the change that first sends playbook notes to a model.
