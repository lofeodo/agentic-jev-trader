# Positions still open at a run's last step are closed and counted as trades

A run (one replay of the agent, or of a comparison strategy, over a stretch of market history) can reach its last step while still holding positions (a position is a holding in one asset, from the moment it is opened until it is fully closed). Such a position has no final profit or loss. At the last step code closes every open position at the price the asset's last bar ended on, charges the usual trading costs (the simulated costs of buying and selling), and stores it as a closed trade, the finished record of a position, whose closing reason is "the run ended". Example: $3,000 of a stock that is up $40 is sold for $3,040, less about $2.50 of costs, and recorded as a trade that made about $37. Memory then uses it like any other closed trade: episode search (looking up past decisions like the current one) can return it, and the track record (the agent's statistics on its own closed trades) counts it. We chose this because a position that happens to be open at the end can be one of the run's best, and the build-up run (the one-year run that fills the memory every later run starts from) should not lose it.

## Considered Options

- **Leave the positions open and out of memory.** The ending account value counts them at the last price and nothing is invented, but memory loses up to one position per asset per run, whatever it was worth.
- **Keep them in memory marked "still open".** Truthful, but it needs a special case in three places: episode search returns only decisions whose outcomes are complete, the text Jev (the hosted decision model) reads about a past position expects an ending, and the track record counts only closed trades.
- **Let the run carry on past its last day until its positions close by themselves.** For the build-up run those days are the test period (the dates kept aside for the final measurement), which the memory must never hold.

## Consequences

- The profit of a closed trade that ended this way is where the position stood when the run stopped, not an ending the agent chose. The closing reason is shown wherever the closed trade is read, by Jev and in reports, so it is not mistaken for one. The track record counts it with the rest.
- Every run that reaches its last step ends in cash. `buy_hold` (the comparison that holds every asset in equal parts) is sold there too and pays for five sales, about $11 on $10,000.
- A run stopped before its last step, for example by its spending cap, keeps its positions open, because it can be restarted from where it stopped.
- The memory a build-up run leaves behind holds no open position, so copying it for a later run copies only closed trades.
- Undoing this means running the build-up again, about $10.
- When the agent decides to make no trade, memory records where the price went over the next bars. The last four bars of each asset in a run have no such next bars inside the run, so those few decisions never get complete outcomes and stay out of episode search.
