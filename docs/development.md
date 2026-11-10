# Development

Every command here works unchanged in Windows `cmd` and in bash or zsh. Run them from
the repo root.

## Environment

One conda env, `agentic-jev-trader`, on Python 3.12 (decision FND-001). Create it once,
then install the pinned dependencies:

```text
conda create -n agentic-jev-trader python=3.12 -y
conda run -n agentic-jev-trader python -m pip install -r requirements.txt
```

Re-run the install line whenever `requirements.txt` changes. All Python is run through
the env with `conda run -n agentic-jev-trader ...`, so there is nothing to activate.

Secrets go in `.env` at the repo root, copied from `.env.example`; see
[configuration.md](configuration.md). Nothing in this step reads them yet.

### Dependencies

`requirements.txt` pins direct dependencies exactly; their own dependencies are left to
float (decision FND-002). To add a package: install it in the env, add it with its exact
version under the matching heading, and note the change in the step's "What was done",
because the file is shared by every feature.

## Tests

```text
conda run -n agentic-jev-trader python -m pytest
```

Suites live in `tests/unit/`, `tests/replay/` and `tests/behavior/`. The repo root is on
the import path, so tests import packages directly (`import shared`), with no install
step (decision FND-003).

### Paid tests

Any test that calls a paid API (an LLM, Jev, a data provider, Snowflake) is marked
`@pytest.mark.paid`. Those tests are skipped unless the flag is given:

```text
conda run -n agentic-jev-trader python -m pytest --run-paid
```

CI never passes the flag. Unit and replay tests must never call a paid API.

## Lint and format

```text
conda run -n agentic-jev-trader python -m ruff check .
conda run -n agentic-jev-trader python -m ruff format .
```

CI runs `ruff check .` and `ruff format --check .`; settings are in `pyproject.toml`.
Line endings are normalised to LF by `.gitattributes`.

## CI

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs one Ubuntu job on every
pull request and on pushes to `main` and the eleven feature branches: install, lint,
format check, tests (decision FND-004). Windows is covered by running the same commands
locally.

## Branches and pull requests

- One long-lived branch per feature, named after it (`foundation`, `memory`, ...), off
  `main`.
- One short-lived branch per step, `step-NN-<slug>`, off the feature branch, merged back
  through a PR once CI is green (merge commit, no squash), then deleted.
- A feature branch merges into `main` only with the author's approval. Nothing is pushed
  to `main` directly and nothing is force-pushed.
- The working memory is in `docs/`: [ROADMAP.md](ROADMAP.md) lists the features, each
  feature folder has an index and one file per step, and
  [DECISIONS.md](DECISIONS.md) logs trade-offs.
