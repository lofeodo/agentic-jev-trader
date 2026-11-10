# S05. Episode search

**Status:** todo

**Summary:** The RAG tool: numeric and text similarity over past episodes in Snowflake, merged into one ranking, limited to earlier steps and to outcomes already visible.

## Goal

Implement `search` as in spec section 13.5: compare the normalised feature vector, compare the embedded situation text, merge both rankings, and return the k most similar episodes with outcomes and tags. The LLM's stated reason is never returned.

**Done when:** Search returns sensible neighbours on the fixture data, and tests prove no episode from the current or a later step and no not-yet-visible outcome is returned.

Spec: [project breakdown](../project-breakdown.md). Feature index: [ROADMAP.md](ROADMAP.md).

## Detailed plan

Not written yet. It is filled in when the step starts, in plan mode, and opens with the
behaviour agreed in the planning interview.

## What was done

Nothing yet.

## Deviations from plan

None yet.

## Open issues

To settle in the planning interview:

- Vector type, similarity and embedding functions come from foundation S1.
- How the two rankings are merged (default: reciprocal rank fusion).
- Whether search is restricted to the same asset or spans all assets in the namespace.
- Unit tests need a local stand-in for Snowflake vector search.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `MEM` heading.
