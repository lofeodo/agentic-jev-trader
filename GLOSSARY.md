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
A fixed, versioned set of assets, instruments, bars, and candle features that runs are executed on. Once published it never changes.
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

**Quality report**:
The list, made when a dataset is built, of every missing bar and every other problem found in the data provider's bars.

**Development period**:
The part of a dataset's date range used for building, tuning, and building up memory.
_Avoid_: Training period, in-sample

**Warm-up period**:
The first three months of a dataset's development period, in which no run trades. Its bars supply the history that later measurements need and the averages and spreads those measurements are scaled by.
_Avoid_: Burn-in, lookback period

**Test period**:
The part of a dataset's date range used only for final measurement, never for tuning.
_Avoid_: Holdout, out-of-sample, validation period

**Asset**:
A thing whose price is tracked, such as one stock, fund, or cryptocurrency.
_Avoid_: Symbol, ticker, security

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

### Runs

**Run**:
One replay of an agent or baseline over a step range of one dataset, with its own account and its own memory.
_Avoid_: Backtest (as a noun for the record), session, simulation

**Live run**:
A run that is in progress and being watched in the web app. It is still a historical replay.
_Avoid_: Live trading, paper trading

**Practice run**:
A brief run that calls the real paid services, Jev and the LLM, to confirm that the system works. Its results never count toward a conclusion.
_Avoid_: Test run, trial run, pilot run, smoke run

**Measurement run**:
A run whose results count toward the project's conclusions.
_Avoid_: Actual run, real run, full run

**Tuning run**:
A short run in the development period, made to adjust how the agent behaves before its settings are frozen. Its results never count toward a conclusion.
_Avoid_: Calibration run, experiment, dry run

**Build-up run**:
A run in the development period whose purpose is to fill a memory with episodes and a track record. It trades as the `memory_off` variant does, reading no memory, and its results never count toward a conclusion.
_Avoid_: Seeding run, training run, warm-up run

**Spending cap**:
The amount of spending on Jev and LLM calls at which code stops a run, once the current step has ended. It counts money paid for model calls, never trading losses.
_Avoid_: Call budget, run budget, dollar cap

**Variant**:
Which strategy a run uses: `buy_hold` (equal money put into every asset at the first step and never traded), `memory_off`, or `memory_on`.
_Avoid_: Mode, arm, configuration

**Random seed**:
The number that fixes the part of a run's randomness that code controls. Jev's answers vary on their own, so two runs with the same random seed can still differ.
_Avoid_: Seed (unqualified)

**Repeat**:
One `memory_on` run and one `memory_off` run over the same steps with the same settings. Repeats differ only by chance, such as Jev answering the same question slightly differently.
_Avoid_: Trial, replicate, iteration

**Verdict**:
The conclusion about memory for one part of the test period, drawn by comparing the ending account value of its `memory_on` runs with that of its `memory_off` runs: memory helped, memory hurt, or can't tell.
_Avoid_: Result (for the conclusion), significance

**Base memory**:
The memory a build-up run leaves behind, which never changes afterwards. Every `memory_on` run starts from a fresh copy of it, its seed memory.
_Avoid_: Initial memory, starting memory

**Seed memory**:
A copy of another run's memory that a run starts from. In version 1 the only memory copied is the base memory.
_Avoid_: Seed (unqualified), warm start

**Memory namespace**:
The label that keeps one run's episodes and track record separate from every other run's.

### Deciding

**Tier**:
How far a step's evaluation went for one asset: 0 is code only, 1 is a screen or a position check, 2 is a full evaluation.
_Avoid_: Level, stage

**Screen**:
The question Jev answers at every step for an asset with no position: is a full evaluation worth running now? The answer is a number from 0 to 1.
_Avoid_: Filter, pre-check

**Position check**:
The question Jev answers at every step for an open position: hold, close, reduce, or add.
_Avoid_: Manage

**Check**:
One look at one asset at one step, answered by Jev: either a screen or a position check.
_Avoid_: Tier 1 call, quick check

**Full evaluation**:
The Tier 2 path, where the LLM selects past episodes and Jev either picks a candidate trade and sizes it or picks no trade.
_Avoid_: Closer look

**Candidate trade**:
One of the trades code lists for an asset at a step: an instrument, a direction, a stop price, and a target price.
_Avoid_: Proposal, idea, signal

**Decision**:
What the agent did for one asset at one step, including "no action".
_Avoid_: Action, move

**Jev**:
The hosted decision model from TypeSafe AI. State goes in; choice, score, and yes/no answers with probabilities come out.

**Size bucket**:
One of the dollar amounts, each a share of account value, that Jev weighs when sizing a trade. The size is their average, weighted by the probability Jev gives each.

**Stop price**:
The price, fixed at entry and never moved, at which code closes the position to cap its loss.
_Avoid_: Stop loss, stop

**Target price**:
The advisory price at which the trade would have met its goal. Code never acts on it.
_Avoid_: Take profit

### Account and risk

**Account value**:
What the account would be worth in cash if every open position were closed now.
_Avoid_: Equity, balance, portfolio value

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
The risk limit on how large one position may be, as a share of account value.

**Exposure limit**:
The risk limit on exposure, as a multiple of account value.

**Daily loss limit**:
The risk limit that blocks entries and adds for the rest of the day once account value has fallen by a fixed percentage since the start of the day. It never closes a position.
_Avoid_: Daily stop, circuit breaker

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
_Avoid_: Short fee, short's daily fee, interest, funding

**Trading costs**:
What trading costs a run in simulated money: slippage, commission, trading fee, and borrow fee. Separate from what Jev and LLM calls cost in real money.
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
Reference entries, one per candle pattern, giving its name, its lean, and a description of its shape. Shared by all runs and read only.
_Avoid_: Rulebook, theory

**Track record**:
Statistics, computed by code, of how the agent's own closed trades performed for each candle pattern, direction, and context. It counts candle patterns on bars only, never those on hourly bars or daily bars.
_Avoid_: Stats, performance history

**Closed trade**:
The finished record of a position, from its entry to its full close, with a known profit or loss.

**Track record group**:
One line of the track record: the closed trades that share a pattern, a direction, and whichever parts of the context the group specifies.
_Avoid_: Bucket, cell, segment

**Lesson**:
A rule or reflection a model writes about its own past decisions. This project's memory holds none.
_Avoid_: Reflection, insight

**Minimum sample**:
The number of closed trades a track record group needs before the agent is shown it.
_Avoid_: Threshold, cutoff

**Episode**:
The stored record of one decision: its situation, action, and outcome.
_Avoid_: Memory (for a single record), experience

**Outcome**:
A fact about how a decision turned out, computed by code and visible only from the step at which it became known.
_Avoid_: Result, label

**Position journal**:
The running record for an open position: why it was opened, the exit plan, and what has happened since.
_Avoid_: Trade log, position notes

**Situation text**:
The one-paragraph plain-language description of a snapshot, written by code and embedded for episode search.

**Snapshot**:
The candle patterns, candle geometry, and context for one asset at one step.

**Feature vector**:
A snapshot's candle geometry and context written as a list of numbers in a fixed order, so that two snapshots can be compared. Candle patterns are not part of it.
_Avoid_: Embedding (for this list), numeric vector

**Episode search**:
Finding the past full evaluations with complete outcomes whose snapshots are most like the current snapshot, judged by feature vector and by situation text. It is the project's retrieval-augmented generation (RAG) step: looking things up before a model answers.
_Avoid_: Memory search, retrieval

**Selected episodes**:
The episodes, possibly none, that the LLM chose from what episode search returned, for Jev to read in one full evaluation.
_Avoid_: Retrieved memories, examples

### Testing

**Recorded-answer test**:
An automated test that runs the agent through one scenario using answers saved from earlier real calls to Jev and, where the scenario reaches it, the LLM, instead of calling either service. Unlike a practice run, it costs nothing and gives the same result every time.
_Avoid_: Replay test (a run is the replay), regression test, playback test

**Scenario**:
One made-up situation a recorded-answer test puts the agent in: one asset at one step, with made-up bars, a made-up memory, and a made-up account that may hold a position.
_Avoid_: Case, fixture, replay
