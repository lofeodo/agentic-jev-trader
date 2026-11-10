# S02. Validation and quality report

**Status:** todo

**Summary:** Checks for missing, duplicate and zero-volume bars and split-driven price jumps, split adjustment, and a quality report per build.

## Goal

Validate raw bars against the step clock: missing bars, duplicates, zero-volume gaps, and jumps caused by stock splits. Adjust for splits. Produce the quality report stored with the dataset.

**Done when:** Each check is tested on hand-made bad data, and split adjustment is tested on a constructed split.

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

- What makes a build fail outright versus pass with warnings.
- Whether small gaps are filled or left as non-tradable steps.
- Where split information comes from (provider corporate actions or jump detection).

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `DSB` heading.
