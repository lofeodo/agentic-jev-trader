# The base memory is built by a run that reads no memory

A `memory_on` run with an empty memory behaves like `memory_off`, so before the test period a build-up run trades a year of the development period (10 March 2024 to 9 March 2025 on the first dataset) to fill the base memory. That run trades the way `memory_off` does: Jev decides alone and the LLM is never called, yet every episode and closed trade is stored as a run with memory would store it. We chose this because about two thirds of a `memory_on` day's cost is the LLM selecting episodes (about $0.055 of $0.083), so a year costs about $10 with Jev alone against about $30 with the LLM, and $30 would have been the whole budget. An episode records a situation, what the agent did, and how it ended, and that record is just as true when the decision was made without memory.

## Considered Options

- **Build up with the full `memory_on` agent.** The records would come from the same kind of agent that later reads them, but the money a year costs with Jev alone buys only about four months this way, and the track record needs many closed trades before its groups reach the minimum sample.
- **No build-up: start with an empty memory in the test period.** Free, but in a 30-day measurement the first weeks would compare two nearly identical agents and hide any effect.
- **One build-up per repeat.** Each repeat would start from a different memory, which says more about chance, at three times the cost.

## Consequences

- The base memory holds the decisions of an agent that had no memory. If memory changes how the agent trades, its own later trades will differ from the ones it reads about.
- No episode in the base memory records an LLM selection, so checks on what the LLM selects use the measurement runs only.
- The build-up run doubles as a year-long `memory_off` result on the development period, which can be used to check settings without touching the test period.
- The agent's settings are frozen before the build-up run. Changing how much risk the agent takes afterwards means running the build-up again, about $10.
- A run may only start from a memory whose records all end before the run's first step, so this base memory can be used from 10 March 2025 on.
- The costs are estimates until a practice run measures them. If they come out higher, the build-up run is shortened from its start; the measurement runs are never shortened.
