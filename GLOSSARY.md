# Trading Agent with Memory

An agent that trades in a historical market simulation, records every decision, and uses those records to trade better over time. This glossary is the project's shared vocabulary.

## Language

### Time and data

**Bar**:
One 15-minute candle: open, high, low, close, volume.
_Avoid_: Candle (for the data row), tick

**Hourly bar**:
A summary of an asset's bars within one clock hour, built by code: the first bar's open, the highest high, the lowest low, the last bar's close, and the volume added up. A stock's session opens on the half hour, so its first hourly bar holds two bars.
_Avoid_: 1h candle, higher timeframe

**Daily bar**:
The same summary over a whole day of an asset's bars: one session for a stock, one day for crypto.
_Avoid_: Daily candle, higher timeframe

**Step**:
The moment a bar ends, when the agent may act. Steps come every 15 minutes, day and night, on one UTC clock shared by all assets.
_Avoid_: Tick, turn, iteration

**Day**:
One UTC calendar day: 96 steps. It is the same day for every asset and for the account.
_Avoid_: Trading day

**Session**:
A stock's trading hours within one day. Crypto has no session.
_Avoid_: Trading day, market hours

**Dataset**:
A fixed, versioned set of assets, instruments, bars, and candle features that trading sims are executed on. Once published it never changes.
_Avoid_: Data set, universe

**Data provider**:
The outside service a dataset's bars are downloaded from.
_Avoid_: Vendor, feed, source

**Adjusted price**:
A stock's past price corrected for splits and dividends, so that a change in price is always a real gain or loss to a holder. A split swaps each share for several cheaper ones (one $100 share becomes two $50 shares); a dividend is cash paid to holders, after which the price drops by about that amount. Every stock price in a dataset is an adjusted price.
_Avoid_: Raw price, as-traded price

**Missing bar**:
A bar an asset should have at a step but that the data provider did not supply, supplied with no volume, or supplied for a stock on a partial-volume day. It stays missing: no bar is ever made up to fill it.
_Avoid_: Gap (for a single bar), hole

**Partial-volume day**:
A day on which the data provider's bars for a stock carry only part of the market's trading, even when their prices are sound. Every bar the stock has that day is a missing bar.
_Avoid_: Thin day, low-volume day (both also describe a genuinely quiet market), bad day

**Lead-in sessions**:
The sessions just before a dataset's first day, 20 in version 1, whose bars serve only to show how much a stock normally trades, so that partial-volume days can be spotted from the dataset's first day on. They are never part of the dataset.
_Avoid_: Lookback, pre-roll, warm-up (that is the first months inside the dataset)

**Quality report**:
The list, made when a dataset is built, of every missing bar and every other problem found in the data provider's bars.

**Development period**:
The part of a dataset's date range used for building, tuning, and building up memory.
_Avoid_: Training period, in-sample

**Warm-up period**:
The first three months of a dataset's development period, in which no sim trades. Its bars supply the history that later measurements need and the averages and spreads those measurements are scaled by.
_Avoid_: Burn-in, lookback period

**Test period**:
The part of a dataset's date range used only for final measurement, never for tuning.
_Avoid_: Holdout, out-of-sample, validation period

**Asset**:
A thing whose price is tracked, such as one stock, fund, or cryptocurrency.
_Avoid_: Symbol, ticker, security

**Asset class**:
Whether an asset is a stock or crypto. A fund counts as a stock.
_Avoid_: Asset type, market

**Instrument**:
One tradable form of an asset. In version 1 every instrument is spot.
_Avoid_: Contract, product

**Spot**:
Buying or selling the asset itself, as opposed to a contract on it.

### Masking

**Masked ID**:
The neutral name the agent sees for an asset, such as `ASSET_03`.
_Avoid_: Alias, anonymized ID

**Asset key**:
The mapping from each masked ID back to the real asset and its price and volume scales. Never visible to the agent.
_Avoid_: Lookup table, mapping table

### Trading sims

**Trading sim**:
One replay of an agent or baseline over a step range of one dataset, with its own account and its own memory: a simulation of trading through past market days. "Sim" for short. At its last step code closes every open position, so a sim that reaches it ends in cash; a sim stopped earlier keeps its positions open and can be restarted. The text sent to Jev and the LLM still calls it a run.
_Avoid_: Run (outside the text the models are sent), backtest, session, simulation (unqualified)

**Live sim**:
A sim that is in progress and being watched in the web app. It is still a historical replay.
_Avoid_: Live trading, paper trading

**Practice sim**:
A brief sim that calls the real paid services (Jev, and the LLM when the sim is a `memory_on` one) to confirm that the system works. Its results never count toward a conclusion. It is a developer's tool, started from the command line and never from the web app.
_Avoid_: Practice run, test run, trial run, pilot run, smoke run

**Rehearsal**:
Three practice sims of one day each that run the whole agent, from reading bars to placing orders, and must all finish without a failure before the build-up sim starts. The first is a `memory_off` sim that leaves a small memory behind; the other two are `memory_on` sims, one per LLM being compared, that start on the following day from a copy of that memory.
_Avoid_: Dress rehearsal, dry run, smoke test, pilot

**Measurement sim**:
A sim whose results count toward the project's conclusions.
_Avoid_: Measurement run, actual run, real run, full run

**Tuning sim**:
A short sim in the development period, made to adjust how the agent behaves before its settings are frozen. Its results never count toward a conclusion. It is a developer's tool, started from the command line and never from the web app.
_Avoid_: Tuning run, calibration run, experiment, dry run

**Build-up sim**:
A sim in the development period whose purpose is to fill a memory with episodes and a scorecard. It trades as the `memory_off` variant does, reading no memory, and its results never count toward a conclusion.
_Avoid_: Build-up run, seeding run, training run, warm-up run

**Free sim**:
A sim on days the developer chooses, started from the web app to watch the agent trade or to try something. It cannot use test period days, and its results never count toward a conclusion.
_Avoid_: Custom run, open run, sandbox

**Spending cap**:
The amount of spending on Jev and LLM calls at which code stops a sim, once the current step has ended. It counts money paid for model calls, never trading losses. A sim stopped by its spending cap can be resumed under a new one.
_Avoid_: Call budget, run budget, dollar cap

**Spending ceiling**:
The most real money the whole project may pay for Jev and LLM calls, US$75 in version 1. A sim is refused when its spending cap, added to the money already spent and to the unspent part of the cap of every sim in progress, would pass it.
_Avoid_: Budget, limit (unqualified), total cap

**Not responding**:
How the web app shows a sim that is recorded as in progress but has stored nothing for a set time, 7 minutes in version 1, usually because its program has died. It can be resumed from its last stored step.
_Avoid_: Stalled, hung, crashed, dead

**Variant**:
Which strategy a sim uses: `buy_hold` (equal money put into every asset at the first step and held until the sim's last step), `memory_off`, or `memory_on`. Two `memory_on` sims can differ by the LLM that selects their episodes; the LLM is a setting of the sim, not a variant.
_Avoid_: Mode, arm, configuration

**Random seed**:
The number that fixes the part of a sim's randomness that code controls. Jev's answers vary on their own, so two sims with the same random seed can still differ.
_Avoid_: Seed (unqualified)

**Repeat**:
One `memory_on` sim for each LLM being compared and one `memory_off` sim, all over the same steps with the same settings. Repeats differ only by chance, such as Jev answering the same question slightly differently.
_Avoid_: Trial, replicate, iteration

**Verdict**:
The conclusion about memory for one part of the test period, drawn by comparing the ending account value of its `memory_on` sims with that of its `memory_off` sims: memory helped, memory hurt, or can't tell. Each LLM being compared gets its own verdict.
_Avoid_: Result (for the conclusion), significance

**Performance winner**:
For one part of the test period, the LLM whose `memory_on` sims ended with the higher average account value, when the gap is larger than the repeats' own spread. When it is not, there is no performance winner.
_Avoid_: Best model, winner (unqualified)

**Price winner**:
For one part of the test period, the LLM that cost fewer real dollars per full evaluation or position review in its `memory_on` sims, thinking included.
_Avoid_: Cheapest model, winner (unqualified)

**LLM benchmark**:
A one-off comparison made before the measurement sims: each LLM is handed the same full evaluations and position reviews saved from the build-up sim, several times each, and selects episodes for them. Nothing is traded and Jev is not asked. An LLM that fails too often is left out of the measurement sims.
_Avoid_: Try-out, smoke check, test run, bake-off

**Selection overlap**:
How alike two sets of selected episodes for the same situation are: the episodes in both, as a share of the episodes in either. Selections of A, B, C and B, C, D share 2 of 4 episodes, an overlap of 50%.
_Avoid_: Similarity (that is how alike two snapshots are), agreement

**Base memory**:
The memory a build-up sim leaves behind, which never changes afterwards. Every `memory_on` sim outside the rehearsal starts from a fresh copy of it, its seed memory.
_Avoid_: Initial memory, starting memory

**Seed memory**:
A copy of another sim's memory that a sim starts from.
_Avoid_: Seed (unqualified), warm start

**Memory namespace**:
The label that keeps one sim's episodes and scorecard separate from every other sim's.

### Deciding

**Tier**:
How far a step's evaluation went for one asset: 0 is code only, 1 is a screen or a position screen, 2 is a full evaluation or a position review.
_Avoid_: Level, stage

**Screen**:
The question Jev answers at every step for an asset with no position: is a full evaluation worth running now? The answer is a number from 0 to 1.
_Avoid_: Filter, pre-check

**Position screen**:
The question Jev answers at every step for an open position: is a position review worth running now? The answer is a number from 0 to 1. Below the cut-off nothing more is asked and the position is held.
_Avoid_: Position check (the every-step hold, close, reduce, or add question it replaced), filter, pre-check

**Position review**:
The Tier 2 path for an open position, run when its position screen says yes: the LLM selects past episodes and Jev decides to hold, close, reduce, or add.
_Avoid_: Position check, closer look, manage

**End-of-session review**:
The position review every open stock position gets, with no position screen first, at the last step of a session from which an order is still carried out the same day. It decides whether the position is carried overnight.
_Avoid_: Forced review (a forced close is something else), closing review

**Standing**:
How an open position stood at one step: how long it had been open, its profit or loss so far, and how far its stop price was from the last price. "Open 6 bars, up $18, stop price 0.9% away" is a standing.
_Avoid_: State, status

**Check**:
One look at one asset at one step, answered by Jev: either a screen or a position screen.
_Avoid_: Tier 1 call, quick check

**Full evaluation**:
The Tier 2 path for an asset with no position, run when its screen says yes: the LLM selects past episodes and Jev either picks a candidate trade and sizes it or picks no trade.
_Avoid_: Closer look

**Lookup**:
One use by the LLM, during a full evaluation or a position review, of a tool that reads memory: another episode search, reading episodes in full, or reading the scorecard. Giving its answer is not a lookup.
_Avoid_: Tool call (the answer is one too), query, retrieval

**Failed reply**:
A reply from the LLM from which code can neither run a lookup nor take an answer: a sentence instead of a tool call, a call to a tool that does not exist, or an answer that is not a list of episodes with a note.
_Avoid_: Invalid output, malformed answer

**Prompt version**:
The name of one exact wording of everything the LLM is sent that is not data: its standing instructions, its tool descriptions, and the layout of each message. Every sim and every full evaluation records the one it used.
_Avoid_: Prompt revision, prompt ID

**Transcript**:
Every message of the exchange between code and the LLM in one full evaluation or one position review, in order and word for word.
_Avoid_: Trace (that is a tracing service's own recording), chat log, conversation

**Decision trail**:
Everything that was asked and answered on the way to one decision, in order: the screen, the LLM's exchange with memory, Jev's pick, Jev's size, what code trimmed, and the order. For a position review: the position screen (an end-of-session review has none), the LLM's exchange with memory, Jev's answer and how much, what code trimmed, and the order.
_Avoid_: Chain of thought (Jev does not reason in words), exchange, trace (that is a tracing service's own recording)

**Candidate trade**:
One of the trades code lists for an asset at a step: an instrument, a direction, and a stop price.
_Avoid_: Proposal, idea, signal

**Decision**:
What the agent did for one asset at one step, including "no action".
_Avoid_: Action, move

**Jev**:
The hosted decision model from TypeSafe AI. A background and questions go in; choice, score, and yes/no answers with probabilities come out.

**Jev request**:
One call to Jev: a background and one or more questions, which Jev answers all at once. A question that depends on another's answer goes in a second Jev request.
_Avoid_: Jev call (for the text sent), prompt (that is the LLM's)

**Background**:
The text code writes for one Jev request to describe the moment: the task, the account, the asset or the position, and any memory shown. Jev's own documentation calls it the state.
_Avoid_: State, context (that is a snapshot's measurements), prompt (that is the LLM's)

**Reading version**:
The name of one exact wording of everything Jev is sent that is not data: the opening of the background, the layout of its sections, and the wording of every question and option. Every sim and every Jev request records the one it used.
_Avoid_: Prompt version (that is the LLM's)

**Size bucket**:
One of the dollar amounts, each a percentage of account value, that Jev weighs when deciding how much money to put into a trade. The size is their average, weighted by the probability Jev gives each. Code then makes the trade smaller if it would break the trade risk limit, the position limit, or the exposure limit.

**Stop price**:
The price, fixed at entry and never moved, at which code closes the position to cap its loss.
_Avoid_: Stop loss, stop

### Account and risk

**Account value**:
What the account would be worth in cash if every open position were closed now.
_Avoid_: Equity, balance, portfolio value

**Order**:
An instruction to buy or sell an amount of one instrument. Its commission or trading fee comes on top of its dollar amount: a $2,000 stock purchase with a $1 commission takes $2,001 of cash for a $2,000 position.
_Avoid_: Trade (for the instruction), fill, transaction

**Position**:
A holding in one instrument, from the step it is opened until it is fully closed.
_Avoid_: Trade (for something still open)

**Entry**:
Opening a new position.

**Add**:
Increasing a position that is already open.

**Reduce**:
Closing part of a position, which stays open at a smaller size.
_Avoid_: Trim, scale out

**Long**:
A position that gains when the price rises: units are bought first and sold later.

**Short**:
A position that gains when the price falls: borrowed units are sold first and bought back later.

**Exposure**:
The size of all open positions added together, counting a short the same as a long.
_Avoid_: Gross exposure

**Risk limit**:
A cap on the account that code enforces whatever the models decide.
_Avoid_: Guardrail, constraint

**Position limit**:
The risk limit on how large one position may be, as a multiple of account value.

**Exposure limit**:
The risk limit on exposure, as a multiple of account value.

**Trade risk**:
What a position would lose, before trading costs, if it closed at its stop price. A $10,000 position whose stop price is 1% away from its entry price has a trade risk of $100. A position can lose more than its trade risk when the price jumps past the stop price, as a stock's can between one session and the next.
_Avoid_: Risk (unqualified), R, exposure (that is the size of all open positions)

**Trade risk limit**:
The risk limit on a position's trade risk, as a share of account value. Code makes an entry or an add smaller until the position fits it. With a limit of 1%, a $10,000 account holds no position whose trade risk was above $100 when it was opened or added to.
_Avoid_: Loss cap, risk per trade, 1% rule

**Daily loss limit**:
The risk limit that blocks entries and adds for the rest of the day once account value has fallen by a fixed percentage since the start of the day. It never closes a position.
_Avoid_: Daily stop, circuit breaker

**Forced close**:
Code closing every position because account value has fallen below a fixed share of exposure, as a broker does to protect what it has lent. With a share of one quarter, an account that buys $20,000 of a stock with $10,000 of its own money is closed out if the stock falls by about a third: the position is then worth about $13,300 and account value about $3,300, a quarter of it.
_Avoid_: Margin call, liquidation, stop-out

**Risk profile**:
A named set of risk limits and of the other settings that decide how boldly the agent trades, such as the size buckets. Every sim trades under one. Version 1 has a single risk profile, medium.
_Avoid_: Risk level, risk mode, preset

**Slippage**:
The small price penalty applied whenever an order is carried out, standing in for the worse price a real order gets.

**Commission**:
The flat dollar amount charged each time a stock order is carried out, whatever the order's size.
_Avoid_: Fee (for stocks), brokerage

**Trading fee**:
The share of an order's value charged each time a crypto order is carried out.
_Avoid_: Commission (for crypto), exchange fee

**Borrow fee**:
The charge a short pays, for the units it has borrowed, at the end of each day it is still open: one day's share of a yearly rate, applied to the short's value. At a yearly rate of 10%, for example, a $2,000 short pays about 55 cents a day.
_Avoid_: Short fee, short's daily fee, interest (that is the loan's charge), funding

**Loan**:
The money the account owes when the positions it has bought cost more than the cash it had. An account with $10,000 that buys $16,000 of positions has a loan of $6,000. The units a short borrows are not part of it.
_Avoid_: Margin, leverage, debt

**Loan interest**:
The charge on the loan at the end of each day: one day's share of a yearly rate. At a yearly rate of 5%, a $10,000 loan costs about $1.37 a day. A loan paid back before the day ends costs nothing.
_Avoid_: Margin interest, borrow fee (that is a short's charge), funding

**Trading costs**:
What trading costs a sim in simulated money: slippage, commission, trading fee, borrow fee, and loan interest. Separate from what Jev and LLM calls cost in real money.
_Avoid_: Fees (for all of them together), friction, transaction costs

### Memory

**Candle pattern**:
A named shape of one to five bars in a row, or of as many hourly bars or daily bars, that traders read as a hint about where the price goes next. A shape with a rising and a falling version, such as engulfing, is two candle patterns.
_Avoid_: Signal, formation, setup

**Pattern window**:
The most recent steps, four in version 1, whose candle patterns on bars a snapshot lists, each with how many steps ago it was recognised.
_Avoid_: Lookback (for this window)

**Lean**:
The hint a candle pattern gives: bullish (the price will rise), bearish (the price will fall), or neutral (indecision). Each candle pattern has one fixed lean.
_Avoid_: Direction (that is a trade's long or short), bias, signal

**Playbook**:
Reference entries, one per candle pattern, giving its name, its lean, and a description of its shape. Shared by all sims and read only.
_Avoid_: Rulebook, theory

**Scorecard**:
Statistics, computed by code, of how the agent's own closed trades performed for each candle pattern, direction, and asset class, split further by whether the trade was with the trend, by volume level, and by part of the day. It counts candle patterns on bars only, never those on hourly bars or daily bars. The text sent to Jev and the LLM still calls it the track record.
_Avoid_: Track record (outside the text the models are sent), stats, performance history

**Closed trade**:
The finished record of a position, from its entry to its full close, with a known profit or loss.

**Closing reason**:
Why a position closed: Jev chose to close it, its stop price was reached, a forced close, or the sim ended.
_Avoid_: Exit reason, exit type

**Scorecard group**:
One line of the scorecard: the closed trades that share a pattern, a direction, an asset class, and any of three further splits the group specifies: with or against the trend, volume level, and part of the day.
_Avoid_: Bucket, cell, segment

**Lesson**:
A rule or reflection a model writes about its own past decisions. This project's memory holds none.
_Avoid_: Reflection, insight

**Minimum sample**:
The number of closed trades a scorecard group needs before the agent is shown it.
_Avoid_: Threshold, cutoff

**Episode**:
The stored record of one decision: its situation, action, and outcome.
_Avoid_: Memory (for a single record), experience

**Outcome**:
A fact about how a decision turned out, computed by code and visible only from the step at which it became known.
_Avoid_: Result, label

**Position journal**:
The running record for an open position: the situation it was opened in, its stop price, and what has been done to it since.
_Avoid_: Trade log, position notes

**Entry memory**:
The scorecard lines and selected episodes Jev read in the full evaluation that opened a position. They are kept with the position unchanged and shown with it. Jev does not read them again: a position review reads episodes selected for its own moment.
_Avoid_: Frozen memory, carried memory

**Situation text**:
The one-paragraph plain-language description of a snapshot, written by code and embedded for episode search.

**Snapshot**:
The candle patterns, candle geometry, and context for one asset at one step.

**Context**:
The measurements of an asset's surroundings at a step, ten in version 1: its short-term and long-term trend, its volume against normal, where the price sits against the day's average price and against the highs and lows of the day and the previous day, how far through its session or day it is, and its typical move as a share of price.
_Avoid_: Indicators, market context

**Typical move**:
The average, over an asset's last bars (14 in version 1), of how far its price travelled per bar, counting any jump from the previous bar's close. With a typical move of $0.60, a price $0.90 above some level is 1.5 typical moves above it. Traders call it ATR (average true range).
_Avoid_: ATR (unexplained), volatility, range

**Day's average price**:
The average price paid for an asset so far in the day, weighted by how much was traded at each price: 100 units traded at $10 and 300 at $12 give $11.50, not $11. Traders call it VWAP.
_Avoid_: VWAP (unexplained), mean price

**Short-term trend**:
Where an asset's price sits against the average closing price of its last bars (20 in version 1). A price of $52 against an average of $50 is above it: the price has been rising for the last few hours.
_Avoid_: Momentum, intraday trend

**Long-term trend**:
Where an asset's price sits against the average closing price of its last daily bars (20 in version 1). A price of $52 against an average of $50 is above it: the price has been rising for weeks.
_Avoid_: Daily trend, the trend (when the short-term one could be meant)

**With the trend**:
Said of a trade whose direction matches the long-term trend: a long while the price is at or above that trend's average, or a short while it is below. Any other trade is against the trend; there is nothing in between.
_Avoid_: Trend-following, countertrend

**Volume against normal**:
A bar's volume divided by the average volume of the asset's bars at the same time of day over its previous days with bars (20 in version 1). A reading of 1.8 means 1.8 times the usual trading.
_Avoid_: Relative volume, RVOL

**Volume level**:
Which of three piles a bar's volume against normal falls in: low, average, or high. With version 1's starting settings, low is below 0.9, average is 0.9 to 1.1, and high is above 1.1.
_Avoid_: Volume bucket, high or low volume (there are three)

**Part of the day**:
Which of three stretches of an asset's day a step falls in. For a stock: the first hour, the middle, or the last hour of its session. For crypto: Asian hours (midnight to 8:00 UTC), European hours (8:00 to 16:00), or American hours (16:00 to midnight).
_Avoid_: Time-of-day bucket, session (for crypto's parts)

**Feature vector**:
A snapshot's candle geometry and context written as a list of numbers in a fixed order, so that two snapshots can be compared. Candle patterns are not part of it.
_Avoid_: Embedding (for this list), numeric vector

**Episode search**:
Finding the past episodes with complete outcomes whose snapshots are most like the current snapshot, judged by feature vector and by situation text. For an asset with no position it finds past full evaluations; for an open position it finds past position reviews of positions in the same direction. It is the project's retrieval-augmented generation (RAG) step: looking things up before a model answers.
_Avoid_: Memory search, retrieval

**Selected episodes**:
The episodes, possibly none, that the LLM chose from what episode search returned, for Jev to read in one full evaluation or one position review.
_Avoid_: Retrieved memories, examples

**Episode summary**:
The one line that stands for an episode in a list of episode search results: how long ago it was, the asset, the part of the day, the long-term trend, the volume level, the candle patterns on bars, what was decided, and how it ended. For a past position review it also gives the position's standing then and where the price went next.
_Avoid_: Preview, snippet

**Episode block**:
The few lines that stand for one selected episode in a background: how long ago it was, whether it was the same asset, the situation text, what was decided, and how it ended. For a past position review it also gives the position's standing then, where the price went next, and how its trade was handled bar by bar.
_Avoid_: Episode card, example

### Testing

**Recorded-answer test**:
An automated test that runs the agent through one scenario using answers saved from earlier real calls to Jev and, where the scenario reaches it, the LLM, instead of calling either service. Unlike a practice sim, it costs nothing and gives the same result every time.
_Avoid_: Replay test (a sim is the replay), regression test, playback test

**Scenario**:
One made-up situation a recorded-answer test puts the agent in: one asset at one step, with made-up bars, a made-up memory, and a made-up account that may hold a position.
_Avoid_: Case, fixture, replay
