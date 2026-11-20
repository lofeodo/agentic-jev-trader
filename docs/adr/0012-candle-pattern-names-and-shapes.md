# Candle pattern names are TA-Lib's own in lower case; shapes are TA-Lib's comments in plain words

A candle pattern is a detector with a lean, such as "bullish engulfing" (a falling bar, then a rising bar whose body covers it). The spec says names are written as TA-Lib gives them and each playbook shape is TA-Lib's own description, but it leaves the exact rule open. We decided that a name is TA-Lib's display name in lower case, without a trailing "pattern", with "bullish" or "bearish" in front when the detector gives both a rising and a falling version: `CDLENGULFING`, which TA-Lib calls "Engulfing Pattern", gives "bullish engulfing" and "bearish engulfing", and `CDLHAMMER` gives "hammer". Which leans a detector can give is read from TA-Lib's own function listing, which states whether its result can be positive or negative. That makes 85 candle patterns from the 61 detectors. Each shape restates the "must have" comment at the top of the detector's TA-Lib source file (v0.8.3) in plain sentences, using the walkthrough pages' words: up bar, down bar, body, wick, and "jump" for a gap. We chose this because it matches how the walkthrough pages already write names, and TA-Lib's comments are written in candle jargon ("white real body", "window") that Jev, the LLM and the developer should not have to decode.

## Considered Options

- **TA-Lib's display names as they stand** ("Engulfing Pattern"). Rejected: they carry no lean, so "bullish engulfing" and its twin would share a name.
- **Copying TA-Lib's comments word for word.** Rejected: jargon, and one comment describes both versions at once ("white (black) real body").

## Consequences

- Some names read awkwardly because TA-Lib's do, such as "bullish three inside up/down" and "bullish kicking - bull/bear determined by the longer marubozu". They are kept: the names are not ours to fix.
- The walkthrough pages' made-up notes differ from the real playbook in places: they write "belt-hold" with no lean, and their shape sentences add detail such as "a lower wick at least twice as long". The pages are brought into line by the change that first sends playbook notes to a model.
