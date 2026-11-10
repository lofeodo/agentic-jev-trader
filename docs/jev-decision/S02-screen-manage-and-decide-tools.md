# S02. Screen, manage and decide tools

**Status:** todo

**Summary:** The screen, manage and decide tools returning each choice with per-option probabilities, conviction and the relevance answer, with latency, retries and cost recorded per call.

## Goal

Implement `screen`, `manage` and `decide` on top of the client. `decide` asks all four questions of spec section 11.1 in one call. Record per-call metrics so model cost can be subtracted in the evaluation.

**Done when:** The three tools pass contract tests against recorded responses and write a metric row per call.

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

- Behaviour when Jev is unavailable or times out: default is 'no trade' for decide, 'hold' for manage, 'no' for screen.
- How Jev cost per call is known.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `JEV` heading.
