# The LLM never writes lessons into memory

Most agent memory designs let the model write lessons after it sees how a decision turned out. Here the agent's memory holds only reference text (the playbook) and records built by code (episodes with their outcomes, the track record, and position journals). The LLM's stated reason for a trade appears again only in the position journal of the position it opened, while that position is open; otherwise it is kept for auditing, and memory search never returns it as evidence for another decision. We chose this so that every remembered item can be checked against the data, so that one mistaken lesson cannot compound over a run, and so that comparing `memory_on` with `memory_off` measures what the playbook and the recorded facts add, with no lessons in the mix.

## Considered Options

- **Lessons as an extra variant.** Ruled out of scope for version 1.
