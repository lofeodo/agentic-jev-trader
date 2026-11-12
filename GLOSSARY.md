# Trading Agent with Memory

An agent that trades in a historical market simulation, records every decision, and uses those records to trade better over time. This glossary is the project's shared vocabulary.

## Language

### Time and data

**Bar**:
One 15-minute candle: open, high, low, close, volume.
_Avoid_: Candle (for the data row), tick

**Step**:
One 15-minute decision point on the clock shared by all assets.
_Avoid_: Tick, turn, iteration

**Dataset**:
A fixed, versioned set of assets, instruments, bars, and candle features that runs are executed on. Once published it never changes.
_Avoid_: Data set, universe

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
The mapping from each masked ID back to the real asset and its price scale. Never visible to the agent.
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
How far a step's evaluation went for one asset: 0 is code only, 1 is a Jev screen or manage call, 2 is a full evaluation.
_Avoid_: Level, stage

**Full evaluation**:
The Tier 2 path, where the LLM proposes candidate trades and Jev picks and sizes one.

**Candidate trade**:
One fully specified trade proposed by the LLM: instrument, direction, stop price, target price, and a reason.
_Avoid_: Proposal, idea, signal

**Decision**:
What the agent did for one asset at one step, including "no action".
_Avoid_: Action, move

**Jev**:
The hosted decision model from TypeSafe AI. State goes in; choice, score, and yes/no answers with probabilities come out.

**Stop price**:
The price, set at entry, at which code closes the position.
_Avoid_: Stop loss, stop

**Target price**:
The advisory price at which the trade would have met its goal. Code never acts on it.
_Avoid_: Take profit

### Memory

**Playbook**:
Reference entries describing what each candle pattern traditionally means. Shared by all runs and read only.
_Avoid_: Rulebook, theory

**Track record**:
Statistics, computed by code, of how the agent's own closed trades performed for each pattern and context.
_Avoid_: Stats, performance history

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
