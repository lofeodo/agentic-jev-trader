# The rehearsal starts from its own small memory, the one exception to the base memory

Supersedes one line of ADR 0007: "The base memory is the only memory a run starts from." Everything else in ADR 0007 stands.

A memory is the records a sim leaves behind: each decision it made and how it turned out ("bet $800 on a rise; closed 6 bars later, up $9"). The base memory is the memory the one-year build-up sim leaves, and every sim whose results count starts from its own copy of it. The rehearsal is three practice sims of one replayed day each, about 50 cents in all, run before the build-up sim. It tries the whole agent end to end once, so that a gap in what is stored shows up before the year (about $10) is paid for: day one with Jev (the decision model) alone, then the next day twice with memory, once with each LLM (the language model that picks which past decisions Jev reads). The rehearsal comes before the build-up sim, so there is no base memory yet. Its two sims with memory therefore start from a copy of the small memory the day-one sim left. That is the only exception, and the code holds it to that:

- A sim whose results count (free, measurement) starts only from the base memory: the latest finished build-up sim's.
- A practice sim starts from the base memory, or from the memory a practice sim without memory left (the rehearsal's day one). It cannot start from any other sim's memory.
- The date rule holds everywhere, the rehearsal included: a sim is refused if its memory holds anything recorded at or after its own first step, so the agent never remembers its own future. Day one's records must all come before day two's first step.
- Memory still never grows from one counting sim to the next: each starts from a fresh copy of the base memory, and its own records stay in that copy.

## Considered Options

- **Run the rehearsal's memory sims on an empty memory.** No exception needed, but the LLM would find nothing to pick and Jev nothing to read, so the part the rehearsal exists to test (searching, picking and reading past decisions) would not run at all.
- **Build a short base memory first, then rehearse from it.** That is the build-up sim itself, the expensive step the rehearsal is meant to check before it runs.
- **Let any practice sim start from any finished sim's memory.** Simpler, but it would let a practice sim read a memory built differently (by a holding sim, or one that already read memory), and nothing needs it.
