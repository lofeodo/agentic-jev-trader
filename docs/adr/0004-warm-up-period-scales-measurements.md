# Measurements are scaled from a warm-up period in which no run trades

Episode search compares snapshots by their feature vectors, and for that every measurement has to sit on one scale: each becomes a standard score, its value minus the average, divided by the typical spread. If volume compared with normal averages 1.0 with a spread of 0.6, a reading of 1.8 becomes 1.3. Those averages and spreads have to come from some stretch of bars, and if that stretch includes bars a run has not reached yet, the run is using its own future. So the first three months of every dataset are a warm-up period: no run trades there, and the averages and spreads are worked out from it once when the dataset is built, shared by all its assets, and frozen with the dataset. We chose this so that the rule "nothing from after the current step ever reaches the agent" has no exception, and so that a snapshot gets the same feature vector whenever it is looked at.

## Considered Options

- **Averages from the whole development period.** More bars, but a run early in the period would be scaled with bars from its own future. A small leak, yet an exception to the no-lookahead rule.
- **Averages from the bars before the current step, recalculated as the run advances.** No leak, but the same snapshot would get different numbers at different times, so old and new episodes would stop being comparable, and feature vectors could not be built once with the dataset.
- **Percentiles, or capped standard scores.** Both tame freak values. Left as a later comparison; either would use the same warm-up period.
- **Fixed formulas with nothing taken from the data.** No leak, but the measurements keep unequal spreads, so some drown out the others.

## Consequences

- A dataset's first tradable step is three months after its start: early April 2022 for the first dataset, which begins 2022-01-03.
- The warm-up period also supplies the history other measurements need, such as the previous 20 days with bars behind "volume compared with normal".
- Standard scores are not capped, so a freak bar dominates its own comparison: volume at 25 times normal scores 40. Accepted for version 1.
- If the warm-up period is unlike what follows, scores are off-centre for every snapshot alike. That costs episode search some quality; it never leaks the future.
- Changing the length means building a new dataset, since a published dataset never changes.
