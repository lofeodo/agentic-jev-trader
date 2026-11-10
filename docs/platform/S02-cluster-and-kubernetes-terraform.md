# S02. Cluster and Kubernetes Terraform

**Status:** todo

**Summary:** kind cluster creation and a Terraform module for the namespace, Secrets, the agent ConfigMap, the server and API Deployments with Services, and the Job-only ServiceAccount and Role, with stub servers answering in the cluster.

## Goal

Script the kind cluster and write the `kubernetes` module from spec section 14.2: namespace, the five Secrets fed from `.env`, the `agent-config` ConfigMap, Deployments and Services for the four MCP servers and the API, the ServiceAccount and Role for Jobs, and the setup Job that applies SQL migrations.

**Done when:** After `terraform apply`, the four stub servers answer over HTTP inside the cluster and the setup Job completes.

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

- Deploys need the author's go-ahead.
- How Secrets are populated from `.env` without committing values or leaving them in shared state.
- Whether Deployments for services that do not exist yet (web) are declared now or added later.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `PLT` heading.
