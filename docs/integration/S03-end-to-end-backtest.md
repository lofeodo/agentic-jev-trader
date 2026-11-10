# S03. End-to-end backtest

**Status:** todo

**Summary:** A five-day memory-off backtest run as a cluster Job with real models, a trace for every full evaluation, a working resume and a clean masking scan.

## Goal

Run the agent as a backtest Job against the real servers and the real dataset. Check that sizes come from Jev and probabilities are stored, that every Tier 2 decision has a LangSmith trace, that a killed job resumes, and that no real symbol or name appears in any model input.

**Done when:** The five-day run finishes, the checks above pass, and model cost for the run is recorded.

Other features this step needs in `main`: agent.

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

- Real model calls cost money: agree a budget for this run first.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `INT` heading.
