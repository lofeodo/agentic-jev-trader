# S02. Episodes and outcomes

**Status:** todo

**Summary:** Decision episodes written at every step, and code-computed outcomes and direction checks stored with the step from which each becomes visible.

## Goal

Implement `write_decision` and `write_outcome` for the record in spec section 13.2: realised profit or loss, exit reason, best and worst point, bars held, and direction checks after 1 bar, 4 bars and at the end of the day, also for 'no trade' decisions. Each outcome carries `available_from_step`.

**Done when:** Tests cover each outcome kind and prove an outcome is invisible before its `available_from_step`.

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

- Whether outcome calculation lives in this server or in the caller; default is a pure module here that the runner calls through `write_outcome`.
- Storage volume: one episode per asset per step, including Tier 0 and Tier 1 stops.
- Where the text embedding is computed (in Snowflake at write time or at search time).

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `MEM` heading.
