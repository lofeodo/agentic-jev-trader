# S01. Jev client and questions

**Status:** todo

**Summary:** A Jev API client and builders that turn agent state into choice, score and yes/no questions and parse the returned probabilities, tested on recorded responses.

## Goal

Wrap the Jev API with retries and rate limiting. Build the state described in spec section 11.3 and the questions in 11.1 and 11.4. Parse answers into the contract's response shape.

**Done when:** Question building and parsing are tested on recorded responses, and a marked test makes one real call.

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

- Request format, SDK and limits come from foundation S1.
- How the state is serialised and how large it may get.
- Recording real responses needs the Jev API key and costs money.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `JEV` heading.
