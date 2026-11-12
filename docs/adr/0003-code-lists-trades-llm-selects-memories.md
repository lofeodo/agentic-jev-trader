# Code lists the candidate trades; the LLM only selects memories

Most trading agents let the LLM propose the trades. Here code lists every candidate trade for an asset from fixed settings: a long (a bet on a rise) or a short (a bet on a fall), each with a tight, medium, or wide stop price (for an asset at $100 that typically moves $0.60 per bar, a long's stop price sits at $99.40, $98.80, or $98.20), plus "no trade". Jev picks one and sizes it. The LLM's only job is to choose, with read-only tools, which past episodes Jev is shown; it writes nothing that Jev reads and nothing into memory. We chose this because the project measures Jev's trading ability, so every option Jev picks from and every word it reads must come from code and be repeatable, while the LLM still does real agentic work by deciding what to look up.

## Considered Options

- **The LLM proposes up to 5 trades with a reason for each (the original brief).** Jev can be steered by text in its background, so the LLM's reasons would decide trades that are credited to Jev, and the list of trades would differ from run to run.
- **No LLM.** Code would hand Jev the 5 most similar past episodes. Cheapest and simplest, but nothing in the system would choose its own tools. Kept as a comparison run for a later version.
- **The LLM also writes lessons.** Ruled out by ADR 0001.

## Consequences

- The LLM is given read-only tools only. It cannot place an order, write to memory, or call Jev.
- Choosing which episodes Jev sees is still influence. Code always adds the full track record (for example "18 trades, 5 wins, average loss of $12"), so the LLM can pick examples but cannot hide the totals.
- ADR 0001 describes what happens to "the LLM's stated reason for a trade". The LLM no longer states one. It writes a one-line note on why it selected its episodes, kept for auditing only and never shown to Jev or returned by memory search.
- There is no plain-LLM stand-in for Jev. If Jev fails after retries, the run stops.
