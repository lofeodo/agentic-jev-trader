# S01. Verification and developer decisions

**Status:** done

**Summary:** Every spec VERIFY item answered with sources and an owner for what stays open, the stack moved to MCP SDK 2.x after the old adapter proved archived (smoke-tested locally), and the provider choices logged: DeepSeek, Jev direct, Alpaca and Coinbase, LangSmith free plan, Snowflake in AWS US West.

## Goal

Work through spec section 22. Check against current official docs: the Jev API (request format, Python SDK, question limits, rate limits, pricing); LangGraph, LangSmith and LangChain MCP adapter versions and usage; LangSmith free-tier limits against the traces a backtest produces; the Snowflake vector type, similarity functions and embedding functions in the account's region; the Snowflake Terraform provider; the MCP Python SDK HTTP transport; passing trace context from the agent to MCP servers; TA-Lib installation on Windows and in a container. Record each finding with its source and date. Collect the developer's decisions: LLM provider and model, data providers and budget, changes to the section 6 assumptions, and the assets of the first dataset.

**Done when:** Every item has a recorded answer or an explicit 'still open, owned by step X', and the choices made under the spec's technology rule are logged with the reason.

Spec: [project breakdown](../project-breakdown.md). Feature index: [ROADMAP.md](ROADMAP.md).

## Detailed plan

### Agreed behaviour (planning interview, 2026-11-10)

**Scope and depth**

- Official docs plus free local checks. Nothing paid, no account created in this step.
- Anything that needs an account or money is recorded as "open, owned by step X".
- Author facts: based in Canada; has a LangSmith account; no Snowflake account yet; will
  create a TypeSafe (Jev) key before the Jev work needs it.
- The documentation research ran during planning (author's choice), so execution writes
  the findings down, runs the local checks and replaces S0's placeholders.

**The four developer decisions (spec section 22)**

1. **LLM:** DeepSeek, default model `deepseek-flash`, through `langchain-deepseek`;
   `deepseek-v4-pro` is one config value away. DeepSeek stores API data in China and
   training use of API inputs is unconfirmed: accepted, because only masked data
   reaches a model.
2. **Market data and budget:** stocks from Alpaca's free plan (IEX feed only; the paid
   feed is not sold in Canada); BTC from Coinbase Exchange's public candles API; futures
   later on Databento's $125 new-account credit. $0 spent now. The options source is
   decided at the dataset builder's options step, ceiling one month of Massive at $199.
   Greeks and implied volatility are computed in code.
3. **Assumptions:** all 16 in spec section 6 kept as written (#16 is now resolved).
4. **First dataset:** SPY, QQQ, AAPL, NVDA + BTC.

**Choices forced by the findings**

- **Jev access:** direct TypeSafe API with the official `typesafe-sdk`; base URL and key
  are config, so OpenRouter (no waitlist, same price) stays a documented fallback.
- **MCP stack:** `langchain[mcp]` (`langchain.mcp.MCPAdapter`, beta) plus MCP SDK 2.x
  (`MCPServer`, Streamable HTTP), replacing the archived `langchain-mcp-adapters` and
  MCP SDK 1.30 that S0 pinned. Proven by a local smoke test before S1 closes; if it
  fails, stop and go back to the author.
- **Tracing:** LangSmith free plan (5,000 traces a month) with a tracing level in the
  config model (off / sampled / full evaluations only / everything). Per-call metrics
  go to Snowflake regardless.
- **Snowflake:** AWS US West (Oregon), Standard edition; the account is created when S4
  starts.
- **S0 placeholders:** S1 updates `requirements.txt`, `.env.example` and
  `docs/configuration.md` to match.

**Agent's calls, confirmed with the plan**

- Text embeddings: `AI_EMBED` with `snowflake-arctic-embed-m-v1.5`,
  `VECTOR(FLOAT, 768)`, `VECTOR_COSINE_SIMILARITY`.
- Jev model pinned to `jev-1.14.0`, not the moving `jev-latest` alias; the response's
  model field is logged.
- Env variable names stay provider-neutral; S2 confirms names. Alpaca gets a key and
  secret pair; the crypto key is removed (Coinbase's public API needs none).
- `alpaca-py` is pinned only if it resolves with the stack.
- S0's step file is not rewritten; its open issues get a "resolved by S1" note.

**Out of scope:** product code, the config model and contracts (S2), Terraform (S4),
creating any account or key, paid calls, the frontend check (web-app S2).

### What gets written

- `docs/verification.md` (new): one section per VERIFY item, each finding with source,
  date, confidence, status and contract impact; ends with an open-items table.
- `docs/assumptions.md` (new): the 16 assumptions confirmed, plus ambiguities found.
- `docs/DECISIONS.md` (shared): FND-007 onward.
- S0 placeholders (shared): `requirements.txt`, `.env.example`, `docs/configuration.md`,
  any file naming the old adapter or "chosen in S1", `CLAUDE.md` current state.
- Roadmap files: this step file, the foundation index, `docs/ROADMAP.md`, S0's open
  issues annotated.

### Steps (one commit each)

1. Branch, plan saved, S1 in progress.
2. Local checks in a throwaway Python 3.12 env: resolve the new requirement set, MCP
   smoke test (server with a structured tool and a health route over Streamable HTTP,
   called through `MCPAdapter`), DeepSeek model construction, `typesafe-sdk` question
   objects, `alpaca-py` resolution.
3. `docs/verification.md`.
4. `docs/assumptions.md` and the FND entries.
5. S0 placeholders, then the project env reinstalled and checked.
6. Step file, index, top-level roadmap; PR into `foundation`, merge on green CI.

### Verification

- Throwaway env: `pip check` clean; MCP smoke test passes.
- Project env: `pip check` clean; pytest 13 passed, 1 skipped; ruff clean.
- Every VERIFY item in spec section 22 has a recorded answer or an owned open item.
- CI green before merge.

## What was done

- **Research** during planning: three research passes over official docs, PyPI and
  GitHub (Jev and data providers; LangChain, MCP and LangSmith; Snowflake, Terraform and
  TA-Lib), plus DeepSeek's docs. Two spec assumptions turned out wrong:
  `langchain-mcp-adapters` is archived and needs `mcp<2`, and MCP SDK 2.x renamed
  `FastMCP` to `MCPServer`.
- **`docs/verification.md`** (new): one section per VERIFY item (Jev, LangGraph and
  LangChain, LangSmith, Snowflake vectors and embeddings, Terraform provider, MCP SDK,
  trace context, TA-Lib, data providers, DeepSeek), each finding with source, date and
  confidence and a "for the contracts" note; a local-checks section; an open-items
  table with an owner step for each item.
- **Local checks** in a throwaway Python 3.12 env: the new requirement set resolves
  with `pip check` clean; MCP smoke test passed (an `MCPServer` with a structured tool
  and `/health` over Streamable HTTP, called through `langchain.mcp.MCPAdapter`; static
  headers delivered; W3C `traceparent` reached the server's `_meta` with the client's
  trace ID); `init_chat_model("deepseek:deepseek-flash")` and `with_structured_output`
  construct; `typesafe-sdk` builds the four `decide` questions; `alpaca-py` resolves.
- **`docs/assumptions.md`** (new): the 16 spec assumptions confirmed; first dataset;
  five ambiguities (A1 to A5) with owner steps.
- **`docs/DECISIONS.md`** (shared): FND-007 to FND-013 added under the FND heading.
- **`requirements.txt`** (shared): removed `langchain-mcp-adapters==0.3.2`;
  `mcp` 1.30.0 to 2.3.0; `langchain` to `langchain[mcp]` 1.4.9; added
  `langchain-deepseek==1.1.1`, `typesafe-sdk==0.7.5`, `alpaca-py==0.45.0`.
- **`.env.example`** (shared) and `docs/configuration.md`: DeepSeek defaults, Jev URL
  and a new `JEV_MODEL`, Alpaca key and secret (`STOCK_DATA_API_SECRET` added,
  `CRYPTO_DATA_API_KEY` removed), key-pair sign-in marked confirmed.
- **Project env** updated: adapter uninstalled, requirements reinstalled; `pip check`
  clean, pytest 13 passed and 1 skipped, ruff lint and format clean.
- **Other docs:** `CLAUDE.md` current state and two gotchas (check verification.md
  first; the MCP 2.x import path); S0's open issues annotated as resolved; S5's vector
  dimension note and S6's adapter name updated.

## Deviations from plan

- Added `JEV_MODEL` to `.env.example` and a `STOCK_DATA_API_SECRET` (Alpaca needs a key
  ID and a secret); the plan named the pair without the variable name.
- `opentelemetry-sdk` was installed in the throwaway env only, to create a span for the
  trace-context check; it is not a project dependency yet (S6 decides).

## Open issues

The full table is at the end of [verification.md](../verification.md). The ones that
shape the next steps:

- **S2:** reserve trace context on every tool request; a tracing level in the config
  model; the candidate schema must fit DeepSeek's strict mode; resolve ambiguities A1
  (what a "day" is for the 3% stop) and A2 (exposure for options and futures).
- **S4:** how `REF.ASSET_KEY` is hidden from `AGENT_ROLE`, since Terraform cannot grant
  "all tables except one" (separate schema, or per-table grants); AI functions on a
  trial account need a card.
- **S6:** prove the agent-to-server trace link inside LangSmith (the MCP side works).
- What the `editorial-ui` skill specifies for the frontend is checked in web-app S2.

## Decisions

FND-007, FND-008, FND-009, FND-010, FND-011, FND-012, FND-013 in `docs/DECISIONS.md`.
