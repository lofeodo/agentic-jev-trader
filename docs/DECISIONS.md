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

### FND-007 DeepSeek `deepseek-flash` is the agent's LLM

2026-11-10. Spec decision 1. The agent's model is DeepSeek through `langchain-deepseek`,
default `deepseek-flash` (V4.1 Flash), selected as `init_chat_model("deepseek:deepseek-flash")`
so provider and model stay one config setting; `deepseek-v4-pro` is the documented
step up. Facts: [verification.md](verification.md) section 10.
**Why:** the author's choice. Flash costs $0.15 in / $0.60 out per million tokens
off-peak (Canadian daytime is off-peak), roughly $0.20 to $0.40 per simulated day at an
estimated 50 full evaluations, so model cost barely dents the net-profit metric; it has
a 1M context, tool calls and JSON output.
**Cost:** DeepSeek stores API data in China and whether API inputs are used for
training is unconfirmed. Accepted because only masked data reaches a model (assumption
11); that rule is now also what protects the data. Strict tool schemas are beta and
need a different base URL, and they forbid length and item-count limits, so the
candidate schema must fit strict mode and the "up to 5 candidates" rule is enforced in
code. Thinking mode is on by default and adds output tokens.

### FND-008 Jev through the direct TypeSafe API, pinned to `jev-1.14.0`

2026-11-10. The jev-decision server uses the official `typesafe-sdk` against
`https://api.typesafe.ai` with the model pinned to `jev-1.14.0`. Base URL, key and model
are config, so OpenRouter (which serves Jev with no waitlist at the same $0.042 per
million input tokens) is a config change, not a code change. The response's `model`
and `request_id` are stored with every answer.
**Why:** the author is creating a TypeSafe key before the Jev work needs it. Pinning
the version, not the moving `jev-latest` alias, keeps runs comparable across the
development and test periods.
**Cost:** a pinned version gets 30 days' notice before deprecation (blog statement, no
formal policy). Jev is not deterministic (about 4% of near-even decisions flip on
repeat), so replay tests use recorded responses. Jev is weak at comparing numbers, so
the state sent to it carries code-computed comparisons, not raw values.

### FND-009 Market data: Alpaca free for stocks, Coinbase for crypto, $0 for now

2026-11-10. Spec decision 2. Stocks and funds: Alpaca's free plan through a paper-only
account (IEX feed, history back to 2016), via `alpaca-py`. Crypto: Coinbase Exchange's
public candles API (no account). Futures: Databento, paid from its $125 new-account
credit (dataset-builder S7). Options: decided at dataset-builder S8 between real quotes
(Massive's $199-a-month plan for one month) and modelled spreads; nothing is spent
before then. Option Greeks and implied volatility are computed in code. Binance is not
used (withdrew from Canada).
**Why:** the author is in Canada, where Alpaca does not sell its paid full-market feed;
all providers chosen are official APIs and free at this stage.
**Cost:** IEX is a small share of US volume, so volume features are IEX-only; they stay
self-consistent because the "normal volume" baseline uses the same feed, and the
quality report states it. Coinbase's history depth is undocumented; Kraken's quarterly
CSV download is the fallback (its API returns only the latest 720 candles).

### FND-010 Section 6 assumptions kept; first dataset is SPY, QQQ, AAPL, NVDA and BTC

2026-11-10. Spec decisions 3 and 4. All sixteen assumptions stand as written (#16 is
resolved by FND-007), recorded in [assumptions.md](assumptions.md) with five ambiguities
assigned to owner steps. The first dataset holds SPY, QQQ, AAPL, NVDA and BTC.
**Why:** the assumptions are conservative and the roadmaps were written against them.
The asset set has the deepest options markets, mixes index funds with single stocks,
and SPY and QQQ map to the micro futures MES and MNQ, so the futures steps can reuse the
dataset.
**Cost:** SPY and QQQ are highly correlated, so the stock side has less variety than
four unrelated names.

### FND-011 MCP stack: `langchain[mcp]` and MCP SDK 2.x, replacing the archived adapter

2026-11-10. The agent reaches the servers through `langchain.mcp.MCPAdapter` (installed
as `langchain[mcp]`); the servers use MCP SDK 2.3.0 (`MCPServer` from
`mcp.server.mcpserver`) over Streamable HTTP with a `/health` route. This replaces
`langchain-mcp-adapters` 0.3.2 and `mcp` 1.30.0, pinned in S0 (FND-002), and adds
`fastmcp` as a transitive dependency.
**Why:** the old adapter's repository was archived on 2026-09-16 and it requires
`mcp<2`; the two paths cannot be installed together. The new path matches the current
MCP spec (2026-07-28), and a local smoke test passed: tool listing, a structured call,
static headers and W3C `traceparent` propagation in `_meta`
([verification.md](verification.md) section 11).
**Cost:** `langchain.mcp` is labelled beta, so its API may change; the adapter returns
structured results as JSON text the agent parses back; transport objects cannot be
passed in its config (headers go in the config dict). The spec's named bridge package
is no longer used.

### FND-012 LangSmith free plan with a tracing level in config

2026-11-10. Tracing stays on LangSmith's Developer plan (5,000 traces a month, a hard
cap without a card, 14-day retention). The config model (S2) gets a tracing level:
off, sampled, full evaluations only, or everything. Per-call metrics (tokens, cost,
latency, retries) are written to Snowflake on every call whatever the level.
**Why:** at the spec's layout a 5-asset backtest makes about 100 to 150 traces per
simulated day, so one 60-day run alone exceeds the monthly cap; the price of extra
traces is unconfirmed. Short development runs can still trace everything.
**Cost:** a sampled-out decision has metrics and an episode but no trace to open, so
the spec's "every trade links to its trace" holds only at the higher levels. Adding a
card later lifts the cap.

### FND-013 Snowflake: AWS US West, Standard edition, key-pair service users, arctic embeddings

2026-11-10. The account (created when S4 starts) is Standard edition in AWS US West
(Oregon). Service users are `TYPE = SERVICE` with key-pair authentication. Terraform uses
the `snowflakedb/snowflake` provider (2.23.0 at time of writing). Situation text is
embedded with `AI_EMBED('snowflake-arctic-embed-m-v1.5', ...)` into `VECTOR(FLOAT, 768)`
and searched with `VECTOR_COSINE_SIMILARITY`.
**Why:** $2.00 per credit, the cheapest listed, with every needed AI model available
natively; residency is not a constraint for public market data. Password sign-in is
blocked for non-human users. The 768-dimension English model fits short situation
texts and costs least to store and scan.
**Cost:** AI functions are disabled on a trial account until a card is added. Vectors
cannot be bound as parameters, so inserts cast arrays in SQL. Terraform cannot grant
"all tables in a schema except one", which affects how `REF.ASSET_KEY` is hidden from
`AGENT_ROLE` (open item for the S4 interview).

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
