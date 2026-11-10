# S06. Assembly and variants

**Status:** todo

**Summary:** The three tiers wired into the runner over MCP clients, the memory-off and memory-on variants, and a five-day fixture backtest that completes on scripted models with no real name in any model input.

## Goal

Connect the runner to the tiers and to the stub servers over MCP, add the variant switch and seed-memory option, and provide the entry point the backtest Job runs.

**Done when:** A five-day backtest on the fixture dataset finishes for both variants from one command, and a test scans every model input for real symbols and names.

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

- Whether the runner talks to the servers in-process for tests and over HTTP in the cluster.
- What 'seed' controls in a run (model sampling, tie-breaks, order of assets).

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `AGT` heading.
