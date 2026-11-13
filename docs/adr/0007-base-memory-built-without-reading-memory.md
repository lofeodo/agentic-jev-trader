# The base memory is built by a run that reads no memory

The project compares two variants of the agent over the same days: `memory_on`, which before deciding on a trade looks up episodes (stored records of its own past decisions and how they ended), and `memory_off`, which decides without them. With nothing stored yet the two behave the same, so before any measurement a build-up run trades a year of the development period (the dates set aside for building and adjusting; 10 March 2024 to 9 March 2025 on the first dataset) to fill the base memory, the memory every `memory_on` run later starts from a copy of. That build-up run trades as `memory_off` does: Jev (the hosted decision model) makes every decision alone and the LLM (the language model that, in `memory_on`, selects which episodes Jev reads) is never called, yet every episode and every closed trade is stored. We chose this for cost: about two thirds of what a `memory_on` day costs is the LLM (about $0.055 of $0.083), so a year costs about $10 with Jev alone against about $30 with the LLM, and $30 was the project's whole spending ceiling when this was decided. Nothing is lost in the records themselves: an episode records a situation, what the agent did, and how it ended, and that is just as true when the decision was made without memory.

## Considered Options

- **Build up with the full `memory_on` agent.** The records would come from the same kind of agent that later reads them. But the $10 that buys a year with Jev alone buys only about four months this way, and a short build-up leaves the track record thin. The track record is the agent's statistics on its own finished trades, such as "18 trades, 5 made money, average loss $12". It is split into several hundred groups, and a group is shown to the agent only once it holds 10 trades (the minimum sample).
- **No build-up: start with an empty memory in the test period** (the dates kept aside for the final measurement). Free, but a measurement lasts 30 days, and for its first weeks the two variants would be nearly identical, which hides any effect.
- **One build-up run per repeat.** A repeat is one `memory_on` run and one `memory_off` run over the same days, and each measurement uses three of them. Each repeat would start from a different memory, which says more about chance, at three times the cost.

## Consequences

- The base memory holds the decisions of an agent that had no memory. If memory changes how the agent trades, its later trades will differ from the ones it reads about.
- No episode in the base memory records what the LLM selected, so checks on the LLM's selecting use the measurement runs only.
- The build-up run doubles as a year-long `memory_off` result on the development period, which can be used to check settings without touching the test period.
- The agent's settings are frozen before the build-up run. Changing how much risk the agent takes afterwards means running the build-up again, about $10.
- The base memory is the only memory a run starts from: no memory collects records from one run to the next. A run may start from it only if all its episodes were recorded before the run's first step, and code refuses otherwise. On the first dataset that is from 10 March 2025 on.
- The costs are estimates until a practice run (a brief run on the paid services that only checks the system works) measures them. If they come out higher, the build-up run is shortened from its start; the measurement runs are never shortened.
