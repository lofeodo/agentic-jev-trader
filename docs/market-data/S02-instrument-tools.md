# S02. Instrument tools

**Status:** todo

**Summary:** Instrument listing and detail for spot, futures contracts and a shortlist of option contracts with strike, expiry, bid, ask and Greeks, all as of the step.

## Goal

Implement `list_instruments` and `get_instrument`. Spot returns one row; futures returns the tradable contracts; options returns a shortlist with quotes as of the step. Expired or not-yet-listed contracts are never returned.

**Done when:** Each instrument type is tested on the fixture dataset, including quotes that must not come from a later step.

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

- How the option shortlist is chosen (count, strikes around the money, minimum days to expiry).
- Whether the seven-day minimum expiry is applied here, in the agent's gate, or both.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `MKD` heading.
