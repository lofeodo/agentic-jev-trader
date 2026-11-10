# S03. Fakes and fixture dataset

**Status:** todo

**Summary:** In-memory implementations of every interface, scripted fake LLM and Jev responders, and a small deterministic synthetic dataset, so each feature can be tested without Snowflake, the cluster or paid APIs.

## Goal

Implement every interface from S2 in memory: the four tool servers, storage, the job launcher and the run executor. Add scripted responders that stand in for the LLM and for Jev. Generate a small, seeded, synthetic dataset in the published-dataset shape (a few masked assets across stock and crypto, with bars, instruments, candle feature rows, and a handful of futures and option instruments with quotes). No real market data goes in the repo.

**Done when:** A test drives a few steps through the fakes end to end, and the fixture dataset regenerates byte-for-byte from its seed.

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

- How realistic the fakes must be: default is contract-correct but simple (the fake broker fills at next open with no costs).
- Fixture size: default five assets and ten trading days.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `FND` heading.
