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

### FND-001 Python 3.12 for the env and the container images

2026-11-10. The conda env `agentic-jev-trader` and, later, the images use Python 3.12.
**Why:** the author's choice in the S0 interview. PyPI was checked first: LangGraph
1.2.20 declares support up to 3.13; TA-Lib 0.8.3 and the Snowflake connector 5.2.0 ship
Windows and Linux wheels for 3.11 to 3.15. 3.13 was recommended as the newest fully
supported version; 3.14 (the machine's default Python) is not yet declared by LangGraph.
**Cost:** 3.12 reaches end of security support sooner than 3.13, so an upgrade comes
earlier; nothing here needs a newer feature.

### FND-002 Exact pins for direct dependencies only

2026-11-10. `requirements.txt` pins every direct dependency with `==`; transitive ones
float. All packages the spec names are pinned now, plus `uvicorn`, `httpx`,
`pytest-asyncio`, `kubernetes` and `ruff`, which the spec implies.
**Why:** later features rarely need to edit this shared file, and a full lock file would
conflict on every parallel dependency change. **Cost:** a transitive release can break
an install or CI without any change here; the fix is to pin that package when it happens.
No LLM provider package yet: foundation S1 chooses the provider.

### FND-003 The repo root is on the import path; no installable package

2026-11-10. `pyproject.toml` holds only tool settings. pytest adds the repo root through
`pythonpath`, code runs from the root as `python -m <package>`, and images copy folders.
**Why:** a single solo repo with several entry points; it removes a `pip install -e .`
setup step and packaging metadata. **Cost:** code run from another directory cannot
import the packages; container images must set the working directory to the copied root.

### FND-004 CI runs on Linux only, with ruff and pytest

2026-11-10. One Ubuntu job on every PR and on pushes to `main` and the eleven feature
branches: install, `ruff check`, `ruff format --check`, `pytest`.
**Why:** Linux matches the containers; Windows is exercised by local runs, and the setup
was checked through `cmd` in S0. One job keeps CI fast across sixty step PRs.
**Cost:** a Windows-only break (path handling, a wheel missing on Windows) is caught
only locally.

### FND-005 Paid tests behind a `paid` marker and a `--run-paid` flag

2026-11-10. Any test that calls an LLM, Jev, a data provider or Snowflake carries
`@pytest.mark.paid`; a root `conftest.py` skips those unless pytest gets `--run-paid`.
Markers are strict, so a typo in a marker name fails collection.
**Why:** the global rule that unit tests never call paid APIs and such tests are skipped
by default. **Cost:** paid tests never run in CI; they are run by hand before releases
or prompt and model changes.

### FND-006 Line endings normalised to LF

2026-11-10. `.gitattributes` stores text files with LF (`*.bat` and `*.cmd` keep CRLF).
**Why:** the repo is edited on Windows and checked on Linux; the same bytes everywhere
keep `ruff format --check` and diffs stable. **Cost:** none expected; Windows editors
handle LF.

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
