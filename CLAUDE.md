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

Gotchas:

- `requirements.txt` installs this package with `-e .`, so `python -m jev_trader...` works. An install run from a git worktree points the shared conda env at that worktree: rerun the install from the main checkout once the worktree is gone. In a worktree, tests need nothing (pytest adds `src` itself).
- `tests/conftest.py` holds the folder rules. Tests in `unit` and `recorded` get pytest-recording's `block_network` marker, so they cannot reach the network even without `--block-network`. LangSmith tracing is set off for every test.
- `conda run` cannot take a multi-line `python -c` script. Write the script to a file instead.

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

Per the `review-gate` skill, a PR always gets the `requires-human-review` label when it:

- places orders (an order is an instruction to buy or sell, such as "buy $1,000 of this stock");
- changes risk limits (a risk limit is a cap on the account that code enforces, such as never risking more than $100 of a $10,000 account on one trade);
- changes how API keys are stored, sent, logged, or exposed. Code that only reads a key from `.env` the usual way doesn't count.

## Agent skills

### Issue tracker

Issues live in GitHub Issues for lofeodo/agentic-jev-trader (gh CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
