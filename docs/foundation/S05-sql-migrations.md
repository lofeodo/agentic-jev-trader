# S05. SQL migrations

**Status:** todo

**Summary:** Versioned SQL migrations for all sixteen tables matching the shared schemas, a runner that applies them, and a check that the agent role cannot read the asset key.

## Goal

Write migration files for every table in spec section 14.1, with column names and types matching the S2 schemas, including the vector columns verified in S1. Write a portable Python runner that applies pending migrations and records which ran; the cluster's setup job reuses it later.

**Done when:** Migrations apply cleanly to an empty database, re-running is a no-op, a test compares table columns with the schemas, and a test confirms `AGENT_ROLE` is refused on `REF.ASSET_KEY`.

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

- Applying migrations to the real account is a deploy and needs the author's go-ahead.
- Vector dimensions: S1 chose `snowflake-arctic-embed-m-v1.5`, so the situation embedding is `VECTOR(FLOAT, 768)`; the numeric feature vector's length is fixed by S2 (FND-013). Vectors cannot be bound as parameters: inserts cast an array in SQL.
- Whether schema-versus-table drift is checked in CI or only on demand, since CI has no Snowflake access by default.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `FND` heading.
