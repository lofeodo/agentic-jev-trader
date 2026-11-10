# S01. Real servers in the cluster

**Status:** todo

**Summary:** The four real servers deployed in place of the stubs, with every tool answering in the cluster against Snowflake.

## Goal

Switch the Deployments from stubs to the real market-data, broker-sim, memory and jev-decision servers and check every tool over HTTP inside the cluster.

**Done when:** A marked integration test calls every tool on every server in the cluster and passes.

Other features this step needs in `main`: platform, market-data, broker-sim, memory, jev-decision.

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

- Uses the fixture dataset loaded into Snowflake until S2 provides a real one.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `INT` heading.
