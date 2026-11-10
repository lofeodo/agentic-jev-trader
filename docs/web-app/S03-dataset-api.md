# S03. Dataset API

**Status:** todo

**Summary:** Dataset list and detail, asset search, and starting and following a build job.

## Goal

Replace the stubbed dataset routes with real ones: read `REF` tables, search assets through the provider interface, write the new dataset row, start the build Job through the launcher, and report progress and the quality report.

**Done when:** Tests cover each route against fake storage and the fake launcher, including a failed build.

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

- Asset search needs the dataset-builder's providers at runtime; until integration it uses the fake.
- Validation of the request (date range, split, instrument types).

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `WEB` heading.
