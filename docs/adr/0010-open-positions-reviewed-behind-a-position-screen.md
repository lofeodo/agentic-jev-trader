# An open position is reconsidered only when its position screen says yes

A position is a trade that is open: $6,000 of a stock bought and not yet sold. Until now Jev (the hosted decision model) was asked at every step (every 15 minutes) whether to hold it, close it, reduce it (sell part), or add to it (buy more), and re-read the past episodes (stored records of earlier decisions) it had read when it opened the trade. Now a position is handled the way a trade is opened. At every step Jev answers a position screen, a cheap yes-or-no question: is this position worth reconsidering now? On a no, nothing more is asked: the position is held and its stop price (the price at which code closes it to cap the loss) keeps guarding it. On a yes, a position review runs: the LLM selects past episodes for the position as it stands now, and Jev reads them and decides to hold, close, reduce, or add. Each position review is stored as an episode, and episode search for an open position returns past position reviews of positions in the same direction, not past decisions to open a trade. We chose this because knowing when to close, add, or reduce is where memory is worth most, and the episodes read at entry were chosen for a moment that has passed.

One exception to the screen: at the last step of a stock's session from which an order is still carried out the same day, every open stock position gets a position review with no position screen first (an end-of-session review). A stock held past the close can open the next morning far from where it ended: $6,000 of a stock that opens 3% lower loses $180, whatever its stop price. Carrying a position overnight is therefore always decided, never drifted into.

## Considered Options

- **Keep asking hold, close, reduce, or add at every step, with the entry memory.** No new kind of episode, but the memory read is about the moment of entry, and every extra ask is another chance to close a good trade on a wobble in Jev's answer.
- **Call the LLM at every step for every position.** The freshest memory, at about seven times the LLM spending (about $18 for a 30-day sim against about $2.40).
- **On a no, still ask the old every-step question.** A safety net, but a position could then be closed at a moment the screen called unremarkable, and decisions that move money would be made with two different memories.
- **Search past decisions to open a trade** that look like the present moment ("would I open this trade now?"). The search as it was, but it finds trades that began like this, not trades that stood like this part-way through.
- **Rank the search by the position's standing** (how long open, profit so far, distance to the stop price) as well as by the chart. The standing depends on the sim, so it has no warm-up period to be scaled from (ADR 0004) and cannot be embedded when a dataset is built. The standing is instead shown on each result line for the LLM to weigh.

## Consequences

- The agent without memory and the build-up sim run the same position screen and the same end-of-session review, with no LLM and no past episodes, so the agents still differ only by memory, and the base memory holds position reviews to search.
- Jev can close, reduce, or add only in a position review. Between reviews only code acts on a position: the stop price, a forced close, and the sim's last step.
- A past position review records two outcomes whatever was decided: where the price went after 1 bar, after 4 bars, and by the end of the day, and how the trade ended beside where it stood at the review. It can be searched once both are known.
- The entry memory is still stored with the position and shown with it, but Jev does not read it again. This replaces the re-reading decided earlier the same day.
- Undoing this means running the build-up sim again, since the base memory's position reviews and its trades both come from this rule.
- Spending is planned on the same guess as before, a Tier 2 path on about 15% of all checks. End-of-session reviews add at most 4 position reviews per replayed day, about 1 cent a day for each agent with memory.
