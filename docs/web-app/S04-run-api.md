# S04. Run API

**Status:** todo

**Summary:** Creating, starting, stopping and resuming runs as jobs, the run list, and the live-run data polled by the app.

## Goal

Replace the stubbed run routes: write `SIM.RUNS`, start, stop and resume the backtest Job through the launcher, list runs with status, config, model cost and duration, and serve the live view (current step, value series, open positions with journals, latest decisions and trades, cost so far).

**Done when:** Tests cover each route against fake storage and the fake launcher, including stop and resume.

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

- What 'stop' leaves behind and whether a stopped run can always resume.
- How the polled payload stays small on long runs.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `WEB` heading.
