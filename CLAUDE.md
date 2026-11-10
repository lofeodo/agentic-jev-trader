# CLAUDE.md

Working instructions for agents in this repo. They extend the global working rules.
Explanations live in `docs/`; this file only points to them.

## What this is

A LangGraph trading agent with memory, run on a historical market simulation, with four
custom MCP servers, Snowflake storage, Kubernetes (kind), Terraform, LangSmith and a web
app. Spec: [docs/project-breakdown.md](docs/project-breakdown.md). Map:
[docs/architecture.md](docs/architecture.md).

## Start every session here

1. [docs/ROADMAP.md](docs/ROADMAP.md): eleven features and their status.
2. The feature's index, `docs/<feature>/ROADMAP.md`, then the step file being worked on.
3. [docs/DECISIONS.md](docs/DECISIONS.md) entries the step file cites.

## Commands

All Python runs through the conda env; nothing needs activating. Commands must work in
Windows `cmd` and bash alike: forward slashes, one command per line, no `&&`, no shell
variables.

```text
conda run -n agentic-jev-trader python -m pip install -r requirements.txt
conda run -n agentic-jev-trader python -m pytest
conda run -n agentic-jev-trader python -m pytest --run-paid
conda run -n agentic-jev-trader python -m ruff check .
conda run -n agentic-jev-trader python -m ruff format .
```

Details: [docs/development.md](docs/development.md).

## Rules

- **Spec versus global rules:** where `docs/project-breakdown.md` disagrees with the
  global working rules, the global rules win (PRJ-005): `docs/architecture.md`, not a
  root `ARCHITECTURE.md`; prompts in top-level `prompts/`; forward-slash commands.
- **Paid APIs:** a test that calls an LLM, Jev, a data provider or Snowflake is marked
  `@pytest.mark.paid`. Unit and replay tests never call paid APIs.
- **Shared files:** `shared/` (contracts), `requirements.txt`, `.env.example`,
  `README.md`, `docs/DECISIONS.md`. Edit them only with a one-line note in the step's
  "What was done". Decision IDs carry the feature prefix (`FND-`, `MEM-`, ...).
- **Contracts:** after foundation merges, a contract change is additive only (new
  optional field, new method). A breaking change stops and goes to the author.
- **Imports:** the repo root is on the import path; there is no installable package.
  Packages import each other absolutely (`from shared.schemas import ...`).
- **Dependencies:** exact pins for direct dependencies only. Add a package with its
  exact version under the matching heading in `requirements.txt`.
- **Secrets:** only in `.env` (never committed); every variable is listed in
  `.env.example` and [docs/configuration.md](docs/configuration.md).
- **Masking:** no real asset name, symbol, date or price level may reach a model input.
- **Branches:** step branch `step-NN-<slug>` off the feature branch, PR into the feature
  branch, merge when CI is green. Never push to or check out `main` for work.

## Gotchas

- `tests/` packages have no `__init__.py`; pytest uses `--import-mode=importlib`, so test
  file names may repeat across folders.
- `eval` is a package name here; it shadows nothing (the builtin is a function, not a
  module), but never `from eval import *`.
- Before relying on a library API, version, price or limit, check
  [docs/verification.md](docs/verification.md): several spec assumptions were wrong
  (archived MCP adapter, MCP SDK 2.x renames, Jev limits).
- MCP SDK 2.x: `from mcp.server.mcpserver import MCPServer`; the README's
  `from mcp.server import MCPServer` fails in 2.3.0. Agent side:
  `from langchain.mcp import MCPAdapter` (beta).
- Background agents in a worktree: `git` commands are checked to stay inside the
  worktree, so keep them simple and separate.

## Current state

Foundation S0 (scaffold) and S1 (verification and developer decisions) are done:
layout, env, CI and docs exist, with no product code; every spec VERIFY item is
answered in [docs/verification.md](docs/verification.md) and the technology choices are
FND-007 to FND-013. Next are foundation S2 (contracts in `shared/`) and S4 (Snowflake
Terraform), which can run in parallel.
