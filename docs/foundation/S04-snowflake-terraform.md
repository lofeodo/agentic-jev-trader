# S04. Snowflake Terraform

**Status:** todo

**Summary:** A Terraform module creating the database, the six schemas, the extra-small warehouse, the three roles with their grants and the service users.

## Goal

Write the `snowflake` module from spec sections 14.1 and 14.3: database `TRADING_AGENT`, schemas, an extra-small warehouse that suspends after 60 seconds, `AGENT_ROLE`, `BUILDER_ROLE` and `APP_ROLE` with the read and write grants in the roles table, and one service user per role. State is local. Grants must keep `REF.ASSET_KEY` unreadable by `AGENT_ROLE` even though the table is created later by a migration.

**Done when:** `terraform apply` succeeds against the developer's account and a second apply shows no changes.

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

- `terraform apply` is a deploy: it needs the author's explicit go-ahead in that session.
- Provider name and version come from S1.
- How service-user credentials are generated and handed to `.env` without entering Terraform state in plain text.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `FND` heading.
