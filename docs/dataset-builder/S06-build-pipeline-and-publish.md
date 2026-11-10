# S06. Build pipeline and publish

**Status:** todo

**Summary:** The end-to-end build that downloads, validates, masks, computes features and publishes an immutable dataset with its development and test split, runnable from the command line.

## Goal

Join the five pieces into the build from spec section 8.2, write the dataset tables through the builder role, record status and the quality report, and publish under a new `dataset_id`. Provide the command-line entry the build Job runs. Enforce immutability: a published dataset cannot be changed.

**Done when:** A five-asset spot dataset builds from the command line into Snowflake, a second build of the same inputs gets a new ID, and a test confirms a published dataset rejects changes.

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

- How the development and test split is expressed (date, day number or share).
- Behaviour when a build fails midway: default is leave status `failed` and never publish partial data.
- Progress reporting for the web app's build view.
- Writing to the real account needs Snowflake credentials for the builder role.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `DSB` heading.
