# S02. Persistence and tools

**Status:** todo

**Summary:** The four broker tools and the step-advance operation over the engine, with trades and per-step portfolio rows stored in Snowflake and account state rebuilt after a restart.

## Goal

Expose `get_portfolio`, `place_order`, `close_position` and `get_trade_history`, plus the step-advance operation, keyed by `run_id`. Write `SIM.TRADES` and `SIM.PORTFOLIO_STEPS`. Rebuild a run's account from stored rows so a restarted backtest resumes correctly.

**Done when:** A scripted run over the fixture dataset stores the expected rows, and killing and restarting mid-run gives identical results.

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

- Whether the server holds run state in memory or is stateless per call.
- Idempotency when the runner repeats a step after a crash.
- Order rejection messages the LLM will see.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `BRK` heading.
