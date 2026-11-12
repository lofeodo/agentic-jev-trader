# One UTC clock; an asset has bars only when its market is open

On a normal weekday a stock trades for six and a half hours, which is 26 fifteen-minute bars, while crypto trades day and night, which is 96 bars every day; yet the account has to be valued at one moment across both. Every step sits on a single UTC clock that runs day and night, with steps numbered from 1 at the dataset's first midnight, so every day has exactly 96 steps and a step's day and time of day follow from its number by arithmetic. An asset has a bar only at steps where its market was open, and the agent is not consulted about it at any other step. We chose UTC because it never shifts for daylight saving (the one-hour clock change New York makes twice a year) and a stock's whole session always falls inside one UTC day, which gives the account, every asset, and the daily loss limit (no new positions once the account is down 3% since the day began, $300 on $10,000) the same day.

## Considered Options

- **The same clock in New York time.** The stock session would start at the same time of day all year, but the two days a year when New York changes its clocks would have 92 or 100 steps (23 or 25 hours), and a step's day would no longer follow from its number.
- **A clock that advances only when some asset is open.** Compact for a stocks-only dataset, but a step would mean a different amount of real time in each dataset, and adding a crypto asset would renumber everything.

## Consequences

- Twice a year, when New York changes its clocks, the stock session starts one hour earlier or later on the UTC clock, so it shifts against crypto's bar numbers. A stock's own bar numbers within its session do not change.
- Anything counted in bars (bars held, look-back windows, "after N bars") counts the asset's own bars, never clock steps.
