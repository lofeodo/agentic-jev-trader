# Measurements are scaled from a warm-up period in which no run trades

Episode search compares snapshots partly by their feature vectors, and for that every measurement has to sit on one scale: each becomes a standard score, its value minus the average, divided by the typical spread. If a bar usually moves $0.50 with a typical spread of $0.20, a $0.90 move scores 2.0; if volume compared with normal averages 1.0 with a spread of 0.6, a reading of 1.8 scores 1.3. Those averages and spreads have to come from some stretch of bars, and if that stretch includes bars a run has not reached yet, the run is using its own future. So the first three months of every dataset, the opening of its development period, are a warm-up period: no run trades there, and the averages and spreads are worked out from it once when the dataset is built, shared by all its assets, and frozen with the dataset. We chose this so that the rule "nothing from after the current step ever reaches the agent" has no exception, and so that a snapshot gets the same feature vector whenever it is looked at.

## Considered Options

- **Averages from the whole development period.** More bars, but a run early in the period would be scaled with bars from its own future. A small leak, yet an exception to the rule that nothing from after the current step reaches the agent.
- **Averages from the bars before the current step, recalculated as the run advances.** No leak, but the same snapshot would get different numbers at different times, so old and new episodes would stop being comparable, and feature vectors could not be built once with the dataset.
- **Percentiles (a reading's rank among past readings: 0.9 means higher than 90% of them), or capped standard scores (any score above a limit such as 4 counts as 4).** Both tame freak values. Left as a later comparison; either would use the same warm-up period.
- **Fixed formulas with nothing taken from the data.** No leak, but the measurements keep unequal spreads, so some drown out the others.

## Consequences

- A dataset's first tradable step is three months after its start: early April 2022 for the first dataset, which begins 2022-01-03.
- The warm-up period also supplies the history other measurements need, such as the previous 20 days with bars behind "volume compared with normal".
- Standard scores are not capped, so a freak bar dominates its own comparison: volume at 25 times normal scores 40. Accepted for version 1.
- If the warm-up period is unlike what follows, scores are shifted the same way for every snapshot. That costs episode search some quality; it never leaks the future.
- Changing the length means building a new dataset, since a published dataset never changes.
