# S00. Repo scaffold

**Status:** done

**Summary:** Spec layout as importable packages, a Python 3.12 conda env with every spec-named dependency pinned, pytest with paid tests skipped by default, a Linux CI job for lint and tests, the project CLAUDE.md, a short README and three docs topic files.

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

- **Branches:** `foundation` created off `main` and pushed; this step on
  `step-00-repo-scaffold`.
- **Layout:** empty packages (`__init__.py`) `agent`, `agent.nodes`, `mcp_servers` with
  `market_data`, `broker_sim`, `memory`, `jev_decision`, `dataset_builder`,
  `dataset_builder.providers`, `eval`, `eval.baselines`, `api`, `shared`. Placeholder
  folders: `prompts/`, `playbook/`, `web/`, `infra/terraform/snowflake/`,
  `infra/terraform/kubernetes/`, `infra/sql/migrations/`, `infra/docker/`, `scripts/`,
  `tests/replay/`. No module files: each belongs to the feature that owns it.
- **Environment:** conda env `agentic-jev-trader`, Python 3.12.16, created on the
  author's machine. `requirements.txt` (shared file, created here) pins langgraph
  1.2.20, langchain 1.4.9, langsmith 0.14.17, mcp 1.30.0, langchain-mcp-adapters 0.3.2,
  pydantic 2.14.3, pandas 3.1.1, TA-Lib 0.8.3, snowflake-connector-python[pandas]
  5.2.0, fastapi 0.162.3, uvicorn 0.54.0, httpx 0.28.1, kubernetes 37.0.2, pytest 9.2.0,
  pytest-asyncio 1.4.1.post1, ruff 0.17.4. TA-Lib installed from a prebuilt wheel on
  Windows, with no C library setup. `pip check` is clean.
- **Test setup:** `pyproject.toml` holds pytest settings (repo root on `pythonpath`,
  `testpaths = tests`, importlib import mode, strict markers, asyncio auto mode, the
  `paid` marker) and ruff settings (py312, line length 100, rules E, F, I, UP, B).
  Root `conftest.py` adds `--run-paid` and skips `paid` tests without it.
  `tests/unit/test_smoke.py` imports all 13 packages; `tests/behavior/test_paid_marker.py`
  checks the switch. Result: 13 passed, 1 skipped; with `--run-paid`, 14 passed.
- **CI:** `.github/workflows/ci.yml`, one `ubuntu-latest` job on every pull request and
  on pushes to `main` and the eleven feature branches: install, `ruff check`,
  `ruff format --check`, `pytest`. Concurrency cancels superseded runs.
- **Config and docs:** `.gitignore` (Python, secrets, Terraform state, web build output,
  editors, Claude worktrees), `.gitattributes` (LF), `.env.example` (shared file,
  created here; names provisional), `CLAUDE.md`, `README.md` (shared file, created
  here), `docs/development.md`, `docs/architecture.md`, `docs/configuration.md`.
- **Checked:** the install and test commands ran through `cmd` and through bash with
  the same results; ruff lint and format check are clean.

## Deviations from plan

- Added `.gitattributes` to normalise line endings to LF (FND-006); not in the plan.
  Git warned about CRLF conversion on the first commit, and the CI format check
  compares bytes.
- Snowflake credentials in `.env.example` are key-pair paths
  (`SNOWFLAKE_<ROLE>_PRIVATE_KEY_PATH`), not passwords, because Snowflake service users
  cannot sign in with a password. Still provisional (see open issues).
- The smoke test is parametrised per package, so the default run reports 13 passed and
  1 skipped rather than the plan's 1 and 1.

## Open issues

- S1 confirms the Snowflake authentication method for service users (key pair
  assumed); S4 creates the users to match and S2 confirms the variable names.
- S1 chooses the LLM provider and adds its package to `requirements.txt`, and the data
  providers and their SDKs if any.
- TA-Lib on Linux is first installed by CI on this step's PR; container images (platform
  S1) depend on the same wheel.
- The `readme-writing` skill is to be offered again once something runs (end of
  foundation or integration).

## Decisions

FND-001, FND-002, FND-003, FND-004, FND-005, FND-006 in `docs/DECISIONS.md`.
