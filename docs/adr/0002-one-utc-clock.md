# One UTC clock; an asset has bars only when its market is open

Stocks trade 26 bars a day on weekdays and crypto trades 96 bars a day, every day, yet the account has to be valued at one moment across both. Every step is a 15-minute instant on a single around-the-clock UTC clock, numbered from the dataset's first midnight, so every day has exactly 96 steps and a step's day and slot follow from its number by arithmetic. An asset has a bar only at steps where its market was open, and nothing happens for it at any other step. We chose UTC because it never shifts for daylight saving and a whole stock session always falls inside one UTC day, which gives the account, the daily loss limit, and every asset the same day.

## Considered Options

- **The same clock in New York time.** The stock session would sit in the same slots all year, but two days a year would have 92 or 100 steps, and the day would no longer follow from the step number.
- **A clock that ticks only when some asset is open.** Compact for a stocks-only dataset, but a step would mean a different amount of real time in each dataset, and adding a crypto asset would renumber everything.

## Consequences

- Twice a year, when New York changes its clocks, the stock session shifts by one hour against the crypto slots. A stock's own bars stay numbered 1 to 26 within its session.
- Anything counted in bars (bars held, look-back windows, "after N bars") counts the asset's own bars, never clock steps.
