# S00. Repo scaffold

**Status:** in progress

**Summary:** Repo layout, a conda env with pinned dependencies, pytest, a CI workflow that runs an empty suite, the project CLAUDE.md and the docs skeleton.

## Goal

Create the folder layout from spec section 20, the `agentic-jev-trader` conda env, a pinned `requirements.txt`, `.env.example` listing every variable, pytest configuration with a marker for tests that call paid APIs (skipped by default), a GitHub Actions workflow, a project `CLAUDE.md` and a glanceable README. Pin every dependency the spec already names so later features rarely touch `requirements.txt`.

**Done when:** CI runs the empty test suite green, and the documented env setup commands work unchanged in Windows cmd and in bash.

Spec: [project breakdown](../project-breakdown.md). Feature index: [ROADMAP.md](ROADMAP.md).

## Detailed plan

### Agreed behaviour (confirmed in the planning interview, 2026-11-10)

- **Setup:** three commands create and fill a Python 3.12 conda env named
  `agentic-jev-trader`; the same commands work in cmd and bash. The env is created on
  the author's machine in this step.
- **Dependencies:** one `requirements.txt` with exact pins for everything the spec
  names, plus pytest and ruff. No LLM provider package (S1 decides). A package that will
  not install is left out and logged as an open issue.
- **Tests:** `python -m pytest` from the repo root passes. One smoke test imports every
  package (an empty suite makes pytest exit non-zero). Tests marked `paid` are skipped
  unless `--run-paid` is given.
- **CI:** one Ubuntu job on every PR and on pushes to `main` and the feature branches:
  install, ruff lint, ruff format check, pytest.
- **Layout:** every folder from spec section 20, plus `shared/` (PRJ-002) and a
  top-level `prompts/`; `docs/architecture.md` instead of a root `ARCHITECTURE.md`
  (PRJ-005). Python folders are packages; the others hold a placeholder. Repo root on
  the import path, no installable package.
- **Files:** `.env.example` (known variables, provisional names), `.gitignore` filled,
  project `CLAUDE.md`, minimal README (the `readme-writing` skill is offered again
  later), `docs/development.md`, `docs/architecture.md`, `docs/configuration.md`.
- **Out of scope:** product code, contracts and the config model (S2), VERIFY items
  (S1), Terraform, Docker, the cluster, frontend tooling in `web/`, a licence file.
- **Flow:** `foundation` branch off `main`; work on `step-00-repo-scaffold`; PR into
  `foundation`, merged when CI is green.

Interview answers: Python 3.12 (author's choice; 3.13 was the recommendation); all
spec-named dependencies without a provider package; Linux-only CI with tests and lint;
global rules win over the spec layout; minimal README now; only docs files with real
content; repo root on the path; known env variables under provisional names.

### What gets created

- **Python packages** (empty `__init__.py`): `agent/`, `agent/nodes/`, `mcp_servers/`
  with `market_data/`, `broker_sim/`, `memory/`, `jev_decision/`, `dataset_builder/`,
  `dataset_builder/providers/`, `eval/`, `eval/baselines/`, `api/`, `shared/`. Module
  files the spec names (`graph.py`, `policy.py`, ...) belong to the features that own
  them and are not created here.
- **Placeholder folders** (`.gitkeep`): `prompts/`, `playbook/`, `web/`,
  `infra/terraform/snowflake/`, `infra/terraform/kubernetes/`, `infra/sql/migrations/`,
  `infra/docker/`, `scripts/`, `tests/replay/`.
- **Dependencies:** install the top-level packages unpinned in the new env, read the
  resolved versions, write `requirements.txt` with exact pins for direct dependencies
  only, grouped by area; check with `pip check`. Spec-named: `langgraph`, `langchain`,
  `langsmith`, `mcp`, `langchain-mcp-adapters`, `pydantic`, `TA-Lib`, `pandas`,
  `snowflake-connector-python[pandas]`, `fastapi`, `pytest`. Implied: `uvicorn`,
  `httpx`, `pytest-asyncio`, `kubernetes`, `ruff`.
- **`pyproject.toml`** (settings only): pytest (`pythonpath = ["."]`, `testpaths`,
  importlib import mode, strict markers, asyncio auto mode, the `paid` marker) and ruff
  (py312, line length 100, rules `E, F, I, UP, B`).
- **Tests:** root `conftest.py` adds `--run-paid` and skips `paid` tests without it;
  `tests/unit/test_smoke.py` imports every package; `tests/behavior/test_paid_marker.py`
  is one `paid` test that checks the flag.
- **CI:** `.github/workflows/ci.yml`, one `ubuntu-latest` job on pull requests and on
  pushes to `main` and the feature branches: install, `ruff check`, `ruff format
  --check`, `pytest`.
- **Config and docs:** `.gitignore`, `.env.example`, `CLAUDE.md`, `README.md`,
  `docs/development.md`, `docs/architecture.md`, `docs/configuration.md`.

### Commits

1. Plan and `in progress` status.
2. Layout: packages, placeholders, `.gitignore`.
3. `requirements.txt`, `pyproject.toml`, `conftest.py`, the two tests.
4. CI workflow.
5. `.env.example`, `CLAUDE.md`, `README.md`, the three docs files.
6. Step file, decisions, index and top-level roadmap.

### Verification

- `pip check` reports no conflicts.
- `python -m pytest` gives 1 passed, 1 skipped; with `--run-paid`, 2 passed.
- `ruff check .` and `ruff format --check .` are clean.
- Install and test commands run once through `cmd /c` and once through bash.
- The PR's CI run is green before the merge.

## What was done

Nothing yet.

## Deviations from plan

None yet.

## Open issues

None yet.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `FND` heading.
