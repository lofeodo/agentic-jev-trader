# The LLM never writes lessons into memory

Most agent memory designs let the model write reflections or rules after it sees how a decision turned out. Here the agent's memory holds only reference text (the playbook) and facts computed by code (episodes, outcomes, and the track record); the LLM's stated reason for a decision is stored for auditing and is never retrieved as evidence. We chose this so that every remembered item can be checked against the data, so that one mistaken model-written rule cannot compound over a run, and so that comparing `memory_on` with `memory_off` measures the value of recorded facts alone.

## Considered Options

- **LLM-written lessons as an extra variant in version 1.** Ruled out of scope. If it returns, it comes as a new variant alongside the existing ones, so the comparison above stays intact.
