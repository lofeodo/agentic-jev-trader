# S02. Shared contracts

**Status:** todo

**Summary:** Pydantic schemas for every table and tool payload, typed interfaces for the four tool servers, storage, job launching and run execution, the shared step clock and one config model.

## Goal

Define the contract every feature codes against. Schemas for the sixteen tables in spec section 14.1 and for every tool request and response in section 10. Interfaces for the four tool servers, including the operations only code calls (for example the broker's step advance), for storage, for the job launcher and for executing a run. The step clock: step IDs, day numbers, bar-in-day and market hours per asset class (26 steps a day for stocks, futures and options, 96 for crypto). The pattern name list shared by the feature builder and the playbook. One config model holding provider and model as a single setting, risk limits, size buckets, k and the minimum sample. All instrument types are modelled now, including futures and options fields.

**Done when:** Schemas and interfaces import cleanly, round-trip tests pass, and no payload a model can see has a field for a real symbol, name or date.

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

- Exact shape of the Jev question and answer payloads depends on S1's findings.
- How the daily loss limit behaves (blocks new trades only, or also closes positions): the spec lists it as an exit reason but assumption 4 only blocks new trades.
- Whether the feature vector has a fixed, versioned layout.
- Package name `shared/` is an addition to the spec's repository structure (PRJ-002).

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `FND` heading.
