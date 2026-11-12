# Trading Agent with Memory

An agent that trades in a historical market simulation, records every decision, and uses those records to trade better over time. This glossary is the project's shared vocabulary.

## Language

### Time and data

**Bar**:
One 15-minute candle: open, high, low, close, volume.
_Avoid_: Candle (for the data row), tick

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
A stock's past price corrected for splits and dividends, so that a change in price is always a real gain or loss to a holder. Every stock price in a dataset is an adjusted price.
_Avoid_: Raw price, as-traded price

**Missing bar**:
A step at which an asset should have a bar but the data provider supplied none, or one with no volume. It stays missing: no bar is ever made up to fill it.
_Avoid_: Gap (for a single bar), hole

**Quality report**:
The list, made when a dataset is built, of every missing bar and every other problem found in the data provider's bars.

**Development period**:
The part of a dataset's date range used for building, tuning, and building up memory.
_Avoid_: Training period, in-sample

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

**Variant**:
Which strategy a run uses: `buy_hold`, `pattern_rules`, `memory_off`, or `memory_on`.
_Avoid_: Mode, arm, configuration

**Random seed**:
The number that fixes a run's randomness, so variants can be repeated and their spread reported.
_Avoid_: Seed (unqualified)

**Seed memory**:
A copy of another run's memory that a run starts from.
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

### Memory

**Playbook**:
Reference entries describing what each candle pattern traditionally means. Shared by all runs and read only.
_Avoid_: Rulebook, theory

**Track record**:
Statistics, computed by code, of how the agent's own closed trades performed for each pattern, direction, and context.
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
The one-paragraph plain-language description of a snapshot, written by code and embedded for memory search.

**Snapshot**:
The candle patterns, candle geometry, and context for one asset at one step.
