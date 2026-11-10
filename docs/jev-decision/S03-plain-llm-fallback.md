# S03. Plain LLM fallback

**Status:** todo

**Summary:** A plain LLM implementation behind the same three tools, switchable by config, so Jev can be replaced without touching the agent.

## Goal

Answer the same questions with the configured LLM, returning probabilities in the same shape. Selected by one config setting.

**Done when:** The contract tests from S2 pass with the fallback selected, using a scripted LLM.

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

- How an LLM produces per-option probabilities (asked directly, or from token probabilities where the provider offers them).
- Whether the fallback is also an evaluation variant or only a safety net.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `JEV` heading.
