# S01. Container images

**Status:** todo

**Summary:** A base Python image with TA-Lib and one image per service and job, built and loaded into kind by one cross-platform script.

## Goal

Write the base image and the per-target images: four MCP servers, the API, the dataset build job, the backtest job and the migration setup job. One portable Python script builds them and loads them into the kind cluster.

**Done when:** Every image builds, TA-Lib imports inside the base image, and a stub server container answers its health check.

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

- TA-Lib container install method comes from foundation S1.
- The web image is added by web-app once the frontend exists.
- Image tagging scheme for a local-only cluster.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `PLT` heading.
