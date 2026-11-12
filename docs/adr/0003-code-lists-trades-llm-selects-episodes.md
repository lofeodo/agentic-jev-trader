# Code lists the candidate trades; the LLM only selects episodes

Most trading agents let the LLM propose the trades. Here code lists the candidate trades for an asset from fixed settings, and Jev either picks one of them and chooses how many dollars to put into it, or picks "no trade". A candidate trade is a long (a bet on a rise) or a short (a bet on a fall) with a stop price, the price at which code closes the position to cap its loss, set tight, medium, or wide. For an asset at $100 that typically moves $0.60 in one 15-minute bar, a long's stop price is $99.40, $98.80, or $98.20, so a $1,000 position loses about $6, $12, or $18 if the stop price is hit. The LLM's only job is to choose, with read-only tools, which episodes (the stored records of past decisions and how they turned out) Jev is shown. It writes nothing that Jev reads, and nothing into memory except a one-line note on why it chose those episodes, kept for auditing. We chose this because the project measures Jev's trading ability, so every option Jev picks from and every word it reads is written by code, while the LLM still does real agentic work by deciding what to look up.

## Considered Options

- **The LLM proposes up to 5 trades with a reason for each (the original brief).** Jev's documentation says text in its background can steer its answers, so the LLM's reasons could decide trades that are then credited to Jev, and the list of trades would differ from run to run.
- **No LLM.** Code would hand Jev the 5 most similar episodes. Cheapest and simplest, but nothing in the system would choose its own tools. Kept for a later version as an extra variant.
- **The LLM also writes lessons.** Ruled out by ADR 0001.

## Consequences

- The LLM is given read-only tools only. It cannot place an order, write to memory, or call Jev.
- Choosing which episodes Jev sees is still influence. Code always adds the track record for the situation (for example "18 closed trades, 5 wins, average loss of $12"), so the LLM can pick examples but cannot hide the totals.
- ADR 0001 describes what happens to "the LLM's stated reason for a trade". The LLM no longer states one, so a position journal's "why it was opened" holds only facts recorded by code at entry. The LLM's one-line note is never shown to Jev or returned by memory search.
- There is no plain-LLM stand-in for Jev. If Jev fails after retries, the run stops.
