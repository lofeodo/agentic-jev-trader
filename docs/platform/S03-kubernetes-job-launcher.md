# S03. Kubernetes job launcher

**Status:** todo

**Summary:** The real job launcher that creates, reads, stops and deletes dataset-build and backtest Jobs in the namespace, with a command-line entry.

## Goal

Implement the foundation's launcher interface with the Kubernetes client: build the Job manifest for a dataset build and for a backtest, create it, report status, stop it and delete it. Add a command-line entry so a job can be started without the API. Unit tests use a fake Kubernetes client; a cluster test is marked and skipped by default.

**Done when:** Unit tests pass, and the marked cluster test starts and stops a no-op Job once S2 is in place.

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

- The cluster test can only be run after S2; record its result in this file when it is.
- How job arguments and Secrets reach the Job (environment, ConfigMap or arguments).
- Retry and time-to-live policy for finished Jobs.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `PLT` heading.
