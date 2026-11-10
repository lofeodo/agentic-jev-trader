# S04. Tier 2 graph

**Status:** todo

**Summary:** The LangGraph full evaluation: observe, retrieve with memory on or off, propose up to five candidates through tools, decide, gate, act and record, with the principles in a versioned system prompt.

## Goal

Build the seven nodes of spec section 9.3 and the shared state. The system prompt carries the eight principles of section 12.3 and never the full playbook. With memory off, retrieve returns open positions only. A proposed candidate must be fully specified, including a stop price.

**Done when:** Scripted model responses drive the graph to the expected tool calls, orders and stored records, in both memory modes.

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

- LLM provider and model come from foundation S1.
- Which tools the LLM may call in propose, and the cap on tool calls.
- How malformed or incomplete candidates are handled.
- Prompt changes are logged in `docs/PROMPTS.md`.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `AGT` heading.
