# Decisions

One file for the whole repo. Entries record trade-offs, failure modes hit and fixes.
Each feature has its own heading and ID prefix (for example `BRK-003`), so branches
working in parallel append in different places. Step files list the IDs they added.

Entry format: ID and title, date, the decision, why, and what it costs or rules out.

## Project (PRJ)

### PRJ-001 Contract-first build order across eleven feature roadmaps

2026-11-10. The spec's build phases are sequential (dataset builder first, web app last).
The work is instead split into a small foundation feature that fixes schemas, interfaces
and fakes, nine subsystem features that each replace a fake behind a fixed interface,
and a final integration feature.
**Why:** the author asked for the build order that allows the most parallel work. With
contracts and a fixture dataset in place, no subsystem waits for another, and each agent
owns one branch and one index, which avoids conflicts on shared roadmap files.
**Cost:** real end-to-end behaviour is first seen in integration, later than in the
spec's order; contract mistakes are found late and are expensive, hence the additive-only
rule. Eleven merges into `main` need the author instead of one.

### PRJ-002 A `shared/` package for contracts and fakes

2026-11-10. Schemas, interfaces, the step clock, config and in-memory fakes live in a
`shared/` package that the spec's repository structure does not list.
**Why:** every feature imports the same contracts; they need one home that no single
subsystem owns. **Cost:** one more top-level package. To confirm in foundation S2.

### PRJ-003 Futures and options are late steps inside each feature

2026-11-10. The spec makes futures and options two late phases that cut across the builder,
the market-data server and the broker. Here the contracts model all instrument types
from the start, and each feature has its own derivative steps, joined in integration S8
and S9.
**Why:** the derivative work in three features can then run at the same time, and adding
it never changes a contract. **Cost:** contracts carry futures and options fields before
any code uses them.

### PRJ-004 Sizing arithmetic lives with the agent, not in the Jev server

2026-11-10. Bucket building and the probability-weighted dollar size (spec section 11.2)
are implemented in the agent's policy code; the Jev server only asks questions and
returns probabilities.
**Why:** the spec assigns sizing arithmetic to code and passes `size_buckets` into
`decide`, and the agent feature cannot import from the Jev feature while both are being
built in parallel. **Cost:** the spec's phase 4 lists 'size' under the Jev server, so
this is a default to confirm in the agent S2 interview.

### PRJ-005 The spec is copied into the repo; the global working rules win on conflicts

2026-11-10. The project breakdown is kept at `docs/project-breakdown.md` so every session
can read it. Where it conflicts with the global working rules (a root `ARCHITECTURE.md`
versus `docs/architecture.md`, `agent/prompts/` versus `prompts/`, cmd-only command
examples), the global rules apply unless the project `CLAUDE.md` says otherwise.
**Why:** context is cleared between sessions and the original lives outside the repo.
**Cost:** two copies of the spec; the copy in the repo is the one the roadmaps cite.

## Foundation (FND)

No entries yet.

## Platform (PLT)

No entries yet.

## Dataset builder (DSB)

No entries yet.

## Market-data server (MKD)

No entries yet.

## Broker simulator (BRK)

No entries yet.

## Memory server (MEM)

No entries yet.

## Jev decision server (JEV)

No entries yet.

## Agent loop (AGT)

No entries yet.

## Evaluation harness (EVL)

No entries yet.

## Web app (WEB)

No entries yet.

## Integration (INT)

No entries yet.
