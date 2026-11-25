# CLAUDE.md

## Model recommendation on skill invocation (temporary)

Temporary while I learn which model fits which phase; remove this section once I no longer need it.

When I invoke one of the skills below, start your first reply with one line recommending the model and effort for it, e.g. `Model: Opus, high effort`. If the current model or effort differs, say so and suggest switching with `/model`. Then carry on with the skill; don't wait for me to switch.

| Skill | Model / effort |
|---|---|
| `/wayfinder` | Fable, high |
| `/grill-with-docs`, `/grill-me`, `/to-spec`, `/to-tickets` | Opus, high (Fable for big or novel designs) |
| `/diagnosing-bugs` | Opus high, or Fable for hard ones |
| `/code-review` | Opus, high |
| `/implement`, `/tdd` | Opus, medium (high if a ticket keeps going red) |
| `/implement-spec` | Opus, medium |
| `/retro`, `/improve-codebase-architecture`, `/prototype` | Opus, medium–high |
| `/pr`, `/handoff`, `/wait-what`, `/wizard` | Sonnet, medium |
| `/research` | Sonnet, medium |

Rule of thumb: more thinking where decisions get made and mistakes compound; less where a spec or ticket already holds the decisions. Switch at phase boundaries, not mid-phase.

## Plain language

I'm new to finance and trading. This applies to everything I read: chat, issues, comments, and docs.

- Explain each finance, trading, or statistics term in everyday words where it first appears in a message or issue, with a small example in dollars. Terms from `GLOSSARY.md` get the same treatment.
- Lead with what happens to the account, then name the term for it.
- When a question needs background, give the explainer first, then ask.

## Design lens

- **Emulate a successful day trader** (someone who opens and closes trades within the same day). The agent is meant to work the way one does. For each design choice, ask how such a trader would do it, and recommend from there.
- **Reliability first, for now.** Prefer a standard tool used as it comes over our own adjustments to it.
- **The spec is the source.** Version 1 is specified in the issue [Spec: version 1 of the trading agent with memory](https://github.com/lofeodo/agentic-jev-trader/issues/82) and its comments: ten appendices, then the record of the decisions made while it was assembled. What the spec leaves open is listed at the end of each appendix. `docs/project-breakdown.md` is the original brief, superseded and kept for history: it carries no authority.

## Commands

The conda env is `agentic-jev-trader` (Python 3.12). Install or update the pinned dependencies:

```
conda run -n agentic-jev-trader python -m pip install -r requirements.txt
```

The free tests (`tests/unit` and `tests/recorded`, network blocked), exactly as CI runs them:

```
conda run -n agentic-jev-trader python -m pytest tests/unit tests/recorded --block-network
```

Style check, as CI runs it (`ruff format .` fixes formatting):

```
conda run -n agentic-jev-trader python -m ruff check .
conda run -n agentic-jev-trader python -m ruff format --check .
```

Hand-run groups (spec appendix 10, section 6):

- `tests/snowflake`: real queries against `TRADING_AGENT_TEST`. Skipped unless the `SNOWFLAKE_*` login in `.env.example` is set. `conda run -n agentic-jev-trader python -m pytest tests/snowflake`
- `tests/paid`: real LLM or Jev calls. Skipped unless `--run-paid` is given. They cost money: run only with my go-ahead. `conda run -n agentic-jev-trader python -m pytest tests/paid --run-paid`

- Saving fresh answers for `tests/recorded` (spec appendix 10, section 7): real LLM and Jev calls, keys read from `.env`. They cost money: run only with my go-ahead. `--record-mode=once` records only the tests whose file under `cassettes/` is missing, so delete the files (cassettes) to be re-recorded first. `conda run -n agentic-jev-trader python -m pytest tests/recorded --record-mode=once`

Build a dataset from its settings file in `datasets/` (downloads are free; it writes to Snowflake as the builder login, so ask before running it; `--database TRADING_AGENT_TEST` builds into the test database, `--no-check` publishes past the two limits):

```
conda run -n agentic-jev-trader python -m jev_trader.dataset build datasets/first.toml
```

Start a sim on a published dataset, or resume one from its last completed step (logs in as the sim login and writes to Snowflake; `start` is for `buy_hold`; `--market "falling market"` runs one test period, `--database TRADING_AGENT_TEST` the test database):

```
conda run -n agentic-jev-trader python -m jev_trader.sim start --dataset 1 --variant buy_hold
conda run -n agentic-jev-trader python -m jev_trader.sim resume 12
```

Run a practice sim of the agent without memory: at most one replayed day and 25 cents (`--spending-cap 0.40` raises the cap for that one sim). It calls Jev, so it costs money: run it only with my go-ahead. It needs `infra/migrations/V5__jev_requests_and_decisions.sql`, `V6__full_evaluation_columns.sql`, `V7__position_review_columns.sql` and `V8__episode_outcomes.sql` applied:

```
conda run -n agentic-jev-trader python -m jev_trader.sim practice --dataset 1
```

`--memory-from <sim>` makes it a practice sim of the agent with memory, starting from a copy of the records (past decisions and how they turned out) that a finished sim left behind. This is for the rehearsal: three one-day practice sims before the year-long build-up sim, where the second and third start from the records the first left. Without `--memory-from`, a sim with memory starts from the base memory: the records of the latest finished build-up sim, the one-year sim that only fills memory. The checker refuses a memory holding anything recorded at or after the sim's first step, so the agent never remembers its own future. The agent with memory is not built yet, so for now the checker refuses such a sim before creating it ("not built yet").

Start the API (logs in as the API login, answers this computer only) and the web app, each in its own terminal, then open http://127.0.0.1:5173. The API reads everything; its only writes are a sim's row in `SIM.SIMS` (start, Stop, Resume) and a dataset's row in `REF.DATASETS` (build, Stop). Starting or resuming a sim of the agent starts a job that calls Jev, so it costs money: ask first. A build from the Datasets screen runs `python -m jev_trader.dataset build` as the builder login, writing to Snowflake: ask first, as for the command. `JOB_LAUNCHER` in `.env` picks how jobs start (`local`, the default, is the only one built); each sim job prints to `logs/sims/sim-<id>.log`, each build to `logs/datasets/dataset-<id>.log` beside its settings file:

```
conda run -n agentic-jev-trader python -m jev_trader.api serve
npm run dev --prefix web
```

After changing what the API answers, regenerate the web app's data types (CI fails if they differ):

```
conda run -n agentic-jev-trader python -m jev_trader.api describe web/openapi.json
npm run types --prefix web
```

Save a copy of every table on this computer, so the results survive the Snowflake trial ending about 2026-12-12 (spec appendix 10, section 15). The copy is Parquet files (a common file format for tables) in `saved-tables/` (gitignored), one dated folder per save, with a `manifest.json` listing each table's rows and column types for loading it into a new account later. It logs in as the API login and only reads; run it while no sim or build is writing. The real database is several GB and takes a while; `--database TRADING_AGENT_TEST` saves the test database:

```
conda run -n agentic-jev-trader python -m jev_trader.storage save
```

Start the memory MCP server, the agent's only MCP server (three read-only lookups at `/mcp`, its health at `/health`). It logs in as the memory login, whose role can only read, and takes its host, port and allowed host names from `config/memory_server.toml`; `--database TRADING_AGENT_TEST` serves the test database:

```
conda run -n agentic-jev-trader python -m jev_trader.memory serve
```

Gotchas:

- `requirements.txt` installs this package with `-e .`, so `python -m jev_trader...` works. An install run from a git worktree points the shared conda env at that worktree: rerun the install from the main checkout once the worktree is gone. In a worktree, tests need nothing (pytest adds `src` itself), but `python -m jev_trader...` runs the main checkout's code unless `PYTHONPATH` points at the worktree's `src` (in bash: `PYTHONPATH="$(pwd)/src" conda run ...`).
- `.env` is gitignored, so it lives only in the main checkout: a git worktree has none. There, `tests/snowflake` skips with "Snowflake login not set" (the login is set; the worktree just can't see it), and anything else that reads `.env` finds nothing. Load the main checkout's `.env` into the environment first, never copy it: a short Python script that calls `dotenv.load_dotenv("<main checkout>/.env")` and then `pytest.main([...])`, run from the worktree.
- A sim job started by the API runs the code of the checkout the API runs from, whichever copy is installed.
- `tests/conftest.py` holds the folder rules. Tests in `unit` and `recorded` get pytest-recording's `block_network` marker, so they cannot reach the network even without `--block-network`. LangSmith tracing is set off for every test.
- `conda run` cannot take a multi-line `python -c` script. Write the script to a file instead.
- Every refusal before a sim starts or resumes comes from `src/jev_trader/sim/checker.py`; add a new one there, not in the command or the API. `run_sim` keeps its own guards for carrying a sim on (finished, cap already reached, changed wording), and `api/sim_jobs.py` the checks only the API makes (command-line-only kinds, days, a resume's new cap). The money settings (ceiling, caps, estimate figures) live in `config/spending.toml`.

## Walkthroughs

Two pages are how I read what the models are sent: every message and every reply, word for word on made-up data, with a plain-language note beside each.

- `docs/llm-prompt-walkthrough.html`: the LLM's prompt.
- `docs/jev-reading-walkthrough.html`: what Jev (the decision model) reads and is asked.

A change to what a model is sent updates its page in the same pull request, so page and text always match:

- **the LLM:** system prompt, tool descriptions, message layouts, the limit and re-ask messages;
- **Jev:** the sections of its background, the wording of a question or an option, which questions a request holds.

The pages share one made-up story and one way of writing a past episode: a change to how an episode is written updates both.

## Snowflake setup

`infra/README.md` holds the commands (Terraform, the numbered SQL files, the live check). `terraform apply` changes the developer's account: ask before each one. Private keys and Terraform's state live outside the repo, in `SNOWFLAKE_LOCAL_DIR`.

Gotcha: `conda run` on Windows crashes when a program prints characters outside the old Windows code page, so scripts run through it print plain ASCII.

## Review gate

The `review-gate` skill labels a PR `requires-human-review` only when its blast radius is Wide (the damage would reach outside the code) or its door is one-way (a later PR could not undo the damage). In this project a PR is Wide, and always gets the label, when it:

- places orders with real money (an order is an instruction to buy or sell, such as "buy $1,000 of this stock");
- changes risk limits that guard real money (a risk limit is a cap on the account that code enforces, such as never risking more than $100 of a $10,000 account on one trade);
- changes how API keys are stored, sent, logged, or exposed. Code that only reads a key from `.env` the usual way doesn't count.

Sims trade pretend money. Their orders and risk limits don't count: a mistake there shows up as a wrong number in a sim's results, and a later PR fixes it.

## Agent skills

### Issue tracker

Issues live in GitHub Issues for lofeodo/agentic-jev-trader (gh CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
