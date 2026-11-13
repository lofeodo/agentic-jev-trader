# Positions still open at a run's last step are closed and counted as trades

A run (one replay of the agent over a stretch of market history) can reach its last step while still holding positions, and such a position has no final profit or loss. At the last step code closes every open position at the asset's last closing price, charges the usual trading costs, and stores it as a closed trade whose closing reason is "the run ended". Memory then uses it like any other closed trade: episode search (looking up past decisions like the current one) can return it, and the track record (the agent's statistics on its own finished trades) counts it. We chose this because a trade that happens to be open at the end can be one of the run's best, and the build-up run (the one-year run that fills the memory every later run starts from) should not lose it.

## Considered Options

- **Leave the positions open and out of memory.** The ending account value counts them at the last price and nothing is invented, but memory loses up to one trade per asset per run, whatever it was worth.
- **Keep them in memory marked "still open".** Truthful, but it needs a special case in three places: episode search returns only decisions whose outcomes are complete, the text Jev (the hosted decision model) reads about a past trade expects an ending, and the track record counts only closed trades.
- **Let the run carry on past its last day until its positions close by themselves.** For the build-up run those days are the test period (the dates kept aside for the final measurement), which the memory must never hold.

## Consequences

- The profit of a trade closed this way is where it stood when the run stopped, not an ending the agent chose. The closing reason is shown wherever the trade is read, by Jev and in reports, so it is not mistaken for one. The track record counts it with the rest: at most one trade per asset per run.
- Every run ends in cash. `buy_hold` (the comparison that holds every asset in equal parts) is sold at its last step too and pays for five sales, about $11 on $10,000.
- The memory a build-up run leaves behind holds no open position, so copying it for a later run copies only finished trades.
- Undoing this means running the build-up again, about $10.
- A "no trade" decision records where the price went after it. For the last four bars of each asset that lies beyond the run's last step, so those few decisions never get complete outcomes and stay out of episode search.
