# Verification

Answers to every item the spec marks **VERIFY** (spec section 22), checked in foundation
S1 on **2026-11-10**. Each finding gives its source, a confidence and what it means for
the contracts. Choices made from these findings are in [DECISIONS.md](DECISIONS.md)
(FND-007 onward); open items, each with an owner step, are listed at the end.

**Confidence:** *high* = read on an official page or the package's own metadata;
*medium* = official page seen only in summary, or a vendor's statement outside its docs;
*low* = third-party only. **Local** = proved on the author's machine in S1 (Windows,
Python 3.12).

Facts here go stale. When a step depends on one, it rechecks the version or price it
needs rather than trusting this file.

## 1. Jev (TypeSafe AI)

Spec items: Verify 1; section 11.

| Finding | Source | Conf. |
| --- | --- | --- |
| Endpoint `POST https://api.typesafe.ai/v1/systemone`, `Authorization: Bearer <key>`. `GET /v1/models` lists models; OpenAPI at `api.typesafe.ai/openapi.json`. | [docs.typesafe.ai/api/system-one](https://docs.typesafe.ai/api/system-one.md), [quickstart](https://docs.typesafe.ai/introduction/quickstart.md) | high |
| Body: `model`, `state` (string, object or array; a named-field object is recommended), `questions` (map of your names to question objects, at least one), optional `assets` (images). No seed, no temperature. | system-one, [concepts/state](https://docs.typesafe.ai/concepts/state.md) | high |
| Question types: `choice` (criteria = label to description, **1 to 255 options**), `score` (ordered list of levels, lowest first, **1 to 10 levels**), `noul` (yes/no; optional `true`/`false` descriptions). A fourth, `box`, needs an image. The spec's "2 to 10" score levels comes from a reseller. | system-one; [AI/ML API reseller page](https://docs.aimlapi.com/api-references/decision-models/typesafe/jev.md) says 2 to 10 | high |
| **One call can mix question types**, with no limit on the number of questions; each is answered independently against the same state. The request must fit the context window. | [primitives](https://docs.typesafe.ai/primitives.md) | high |
| Response: `model`, `answers` (by name), `usage` (`input_tokens`, `output_tokens`). Choice: `choice`, `confidence`, `probabilities` (label to p). Score: `score` (probability-weighted expected value, can be fractional), `confidence`, `legend`, `probabilities` (level index to p). Noul: `noul` = P(yes). The returned `model` can differ from an alias sent. | system-one, [SDK response types](https://docs.typesafe.ai/sdk/python/api/types/responses.md) | high |
| Context: 64k tokens per request and 32k per question by default; a `TypeSafe-Danger-Zone-Long-Context: true` header raises both to 262k. Over the limit: `400 max_tokens_exceeded`. Body at most 32 MiB; nesting at most 64 levels; numbers must be finite. | [models](https://docs.typesafe.ai/models.md), [errors](https://docs.typesafe.ai/api/errors.md) | high |
| Rate limits are per organisation in tokens and requests per second, shown only in the developer console. 429 = rate limited, 529 = overloaded; the SDK backs off exponentially. | models, errors | high |
| Price: **$0.042 per million input tokens, output free**, same for 1.13 and 1.14. Same on OpenRouter. No dedicated pricing page on typesafe.ai. | models, [typesafe.ai](https://typesafe.ai), [OpenRouter endpoints](https://openrouter.ai/api/v1/models/typesafe/jev-1.14/endpoints) | high |
| Python SDK `typesafe-sdk` **0.7.5** (2026-10-14), Python >= 3.10, MIT, depends on pydantic >= 2.12. Env var `TYPESAFE_API_KEY`. Clients `TypeSafeClient` (sync) and `AsyncTypeSafeClient`; `client.system_one(state=..., questions={...})` with `Choice`, `Score`, `Noul` question models; answers in `r.choices[...]`, `r.scores[...]`, `r.nouls[...]`. Typed, frozen Pydantic responses with `request_id`. | [PyPI](https://pypi.org/pypi/typesafe-sdk/json), [SDK docs](https://docs.typesafe.ai/sdk/python.md) | high |
| Models: `jev-1.14.0` (2026-10-14) and `jev-1.13.0`. Aliases `jev-latest` and `jev-preview` both point to 1.14.0 and move with releases. A blog post promises 60 days' notice before 1.13 is deprecated and 30 days for 1.14; there is no formal policy page. | models, [changelog](https://docs.typesafe.ai/changelog.md), [blog: jev-1-14](https://typesafe.ai/blog/jev-1-14) | high / medium |
| **Not deterministic.** In TypeSafe's own test, the least stable decision flipped on 4.0% of 15 repeats on average (worst 6.7%), mostly near 50/50. | [consistency cookbook](https://docs.typesafe.ai/cookbooks/consistency_choice_cookbook.md) | high |
| **"Not a calculator."** Numeric comparisons ("cannot reliably judge whether two values are near each other"), dates and counting are unreliable; score values are only weakly calibrated (fine for thresholds, not interpolation); accuracy drops as irrelevant state grows. | [model-jaggedness](https://docs.typesafe.ai/model-jaggedness.md) | high |
| Access: "early access". A waitlist is mentioned only in the 2026-09-15 launch post; whether it still applies is unknown (the console returned 403). Keys come from `console.typesafe.ai/keys`. | [typesafe.ai](https://typesafe.ai), [launch post](https://typesafe.ai/blog/introducing-system-one-models-and-jev) | medium |
| Fallback route: **OpenRouter serves Jev with no waitlist**, models `typesafe/jev-1.14`, `typesafe/jev-1.13`. The official SDK works against it with `base_url="https://openrouter.ai/api"` and an OpenRouter key; model listing does not work there. | [OpenRouter guide](https://openrouter.ai/docs/guides/community/jev.md), [OpenRouter SDK guide](https://openrouter.ai/docs/guides/community/typesafe-sdk.md) | high |
| Data use: TypeSafe will not train on inputs; services hosted in the US; retention "as long as reasonably necessary"; zero retention for enterprise only. | [privacy policy](https://typesafe.ai/legal/privacy-policy), [legal](https://docs.typesafe.ai/legal.md) | high |

**For the contracts:**

- The spec's `decide` call (choice, choice, score, yes/no in one request) is supported
  as designed. The `conviction` score keeps its 5 levels.
- Store per answer: winning label, confidence and the full probability map, plus the
  response `model` and `request_id`. Sizing uses the probability map, not the winner.
- Because Jev is weak at numbers, the state sent to it should carry code-computed
  comparisons and labels ("volume 1.8x normal", "below VWAP") rather than raw values
  to compare. This matches the situation text the spec already generates.
- Replay tests cannot expect identical Jev answers on a re-run; they replay recorded
  responses.
- Base URL, key and model are config (FND-008).

## 2. LangGraph, LangChain and the MCP bridge

Spec items: Verify 2; section 5 "MCP to LangGraph bridge".

| Finding | Source | Conf. |
| --- | --- | --- |
| `langgraph` **1.2.20** (2026-11-05), Python >= 3.10, classifiers 3.10 to 3.13. Typed state as `TypedDict` or dataclass (Pydantic only when validation is needed); reducers via `Annotated`; `StateGraph(State, context_schema=Context)`. | [PyPI](https://pypi.org/pypi/langgraph/json), [graph API](https://docs.langchain.com/oss/python/langgraph/graph-api) | high |
| Checkpointing via `compile(checkpointer=...)` and a `thread_id`. Official checkpointers: memory, SQLite, Postgres, AWS, MongoDB, Azure Cosmos DB. **No Snowflake checkpointer** (the third-party `langgraph-checkpoint-snowflake` 0.1.0 is from 2024 and stale). | [persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [checkpointer list](https://docs.langchain.com/oss/python/integrations/checkpointers/index.md) | high |
| `langchain` **1.4.9** (2026-11-04), `langchain-core` **1.7.7**. Provider and model as one setting: `init_chat_model("{provider}:{model}")`. | [PyPI](https://pypi.org/pypi/langchain/json), [models](https://docs.langchain.com/oss/python/langchain/models) | high |
| **`langchain-mcp-adapters` is archived** (GitHub `archived: true`, last push 2026-09-16). Its last release 0.3.2 requires `mcp<2.0.0`. | [PyPI](https://pypi.org/pypi/langchain-mcp-adapters/json), GitHub API (checked locally with `gh`) | high, local |
| Replacement: **`from langchain.mcp import MCPAdapter`**, installed as `langchain[mcp]>=1.4.0`, labelled **beta**. It is built on `fastmcp` 4, which requires `mcp>=2.3.0,<3`, so the old and new paths cannot be installed together. Config is `{"mcpServers": {name: {"url": url}}}`; a URL means Streamable HTTP. Static headers go on a fastmcp `StreamableHttpTransport(url, headers=...)`. By default each tool call opens and releases the client; keeping the adapter context open reuses the connection. | [migration guide](https://docs.langchain.com/oss/python/migrate/langchain-mcp-adapters), [MCP in LangChain](https://docs.langchain.com/oss/python/langchain/mcp), [connections](https://docs.langchain.com/oss/python/langchain/mcp/connections.md) | high |
| Version set used by this repo (FND-011): langgraph 1.2.20, langchain[mcp] 1.4.9, langsmith 0.14.17, mcp 2.3.0, pydantic 2.14.3, Python 3.12. See section 11 for the local resolution. | PyPI metadata; local | high |

**For the contracts:** the agent reaches servers through `MCPAdapter`; S6 builds the
client check on it. Resume (spec 9.5) stays as designed, from the last completed step
stored in `SIM.RUNS`, not from a LangGraph checkpointer.

## 3. LangSmith

Spec items: Verify 2 and 3; section 15.

| Finding | Source | Conf. |
| --- | --- | --- |
| `langsmith` **0.14.17** (2026-11-02), Python >= 3.10. | [PyPI](https://pypi.org/pypi/langsmith/json) | high |
| Developer (free) plan: 1 seat, **up to 5,000 base traces a month**, base traces kept 14 days. Without a card the 5,000 is a hard cap; adding a card turns on pay-as-you-go. | [pricing](https://www.langchain.com/pricing), [billing](https://docs.langchain.com/langsmith/billing) | high |
| Ingestion limits: 50,000 events an hour and 500 MB an hour without a card (250,000 and 2.5 GB with one). An event is the creation or update of a run. At most 25,000 runs per trace. | [administration overview](https://docs.langchain.com/langsmith/administration-overview) | high |
| A trace is one root run with any number of child runs, so each counts once against the 5,000. | [pricing FAQ](https://www.langchain.com/pricing) | high |
| Tracing is on only when `LANGSMITH_TRACING` (or the older `LANGCHAIN_TRACING_V2`) is `"true"`; an API key alone does not turn it on. `tracing_context(enabled=False)` turns it off in code. | langsmith source `utils.py`, [trace with LangChain](https://docs.langchain.com/langsmith/trace-with-langchain) | high |
| Price per extra 1,000 traces: **not confirmed** (official pages say only "pay-as-you-go"; third parties disagree). | — | open |
| Datasets and evaluations on the free plan: appear included. | pricing table | medium |

**Trace volume against the free plan** (estimate, to be measured in agent S5): the spec
layout is one trace per step for the Tier 1 screens plus one per asset that reaches
Tier 2. With BTC on the shared clock there are 96 steps a day, so about 100 to 150
traces per simulated day for 5 assets: about 750 for a 5-day run and about 9,000 for a
60-day run. One 60-day run alone exceeds 5,000. A fast replay could also approach the
50,000 events an hour.

**For the contracts:** a tracing level in the config model (FND-012). Per-call tokens,
cost, latency and retries are recorded in Snowflake on every call, traced or not.

## 4. Snowflake vectors and embeddings

Spec items: Verify 4; section 13.5.

| Finding | Source | Conf. |
| --- | --- | --- |
| `VECTOR(<INT or FLOAT>, <dim>)`, 32-bit elements, **dimension at most 4096**. Not allowed in VARIANT, clustering keys, primary keys of hybrid tables, Snowflake Scripting, Iceberg tables, search optimisation, Snowpipe or **bind variables**. | [VECTOR type](https://docs.snowflake.com/en/sql-reference/data-types-vector) | high |
| Inserting: cast an ARRAY (`[1,2,3]::VECTOR(FLOAT,3)`). COPY cannot load VECTOR directly: load as ARRAY, then cast. Python connector supports VECTOR from 3.6, but **without server-side binding**: the official example builds each vector into the SQL text. Whether `write_pandas` handles VECTOR is not documented. | VECTOR type, [vector embeddings](https://docs.snowflake.com/en/user-guide/snowflake-cortex/vector-embeddings) | high / open |
| Similarity: `VECTOR_COSINE_SIMILARITY`, `VECTOR_INNER_PRODUCT`, `VECTOR_L1_DISTANCE`, `VECTOR_L2_DISTANCE`, each over two vectors; no token cost. The docs show only `ORDER BY ... LIMIT` scans; no vector index is documented, so treat search as a brute-force scan. | vector embeddings, [VECTOR_COSINE_SIMILARITY](https://docs.snowflake.com/en/sql-reference/functions/vector_cosine_similarity) | high / medium |
| Embedding: **`AI_EMBED(<model>, <text>)`**, the current form of `EMBED_TEXT_768/1024`. `snowflake-arctic-embed-m-v1.5`, `snowflake-arctic-embed-m` and `e5-base-v2` give 768 dimensions; `snowflake-arctic-embed-l-v2.0`, `nv-embed-qa-4` and `voyage-multilingual-2` give 1024. Most have a 512-token context. | [AI_EMBED](https://docs.snowflake.com/en/sql-reference/functions/ai_embed), vector embeddings | high |
| Region: the four arctic-embed models are available natively in **AWS us-west-2**, us-east-1 and ca-central-1; us-west-2 has the widest set. Cross-region inference is an account parameter (`CORTEX_ENABLED_CROSS_REGION`) set by ACCOUNTADMIN; new organisations default to `ANY_REGION`. | [model availability](https://docs.snowflake.com/en/user-guide/snowflake-cortex/model-availability.md), [cross-region](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cross-region-inference) | medium / high |
| Cost: AI functions are billed in AI Credits per million input tokens; an AI Credit is $2.00 with global routing or $2.20 regional. **Per-model rates not confirmed** (the official consumption table PDF did not decode). | [AI cost](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-cost), [pricing](https://docs.snowflake.com/en/user-guide/snowflake-cortex/pricing) | high / open |
| Privileges: account privilege `USE AI FUNCTIONS` (or a per-function one) **and** the database role `SNOWFLAKE.CORTEX_USER` or `SNOWFLAKE.AI_FUNCTIONS_USER`. `USE AI FUNCTIONS` and `CORTEX_USER` go to PUBLIC by default; grant them explicitly anyway. | [AI privileges](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-privileges-and-access) | high |
| Trial accounts: "AI features are disabled by default on self-service trial accounts until you add a credit card" (adding one does not end the trial). | [trial accounts](https://docs.snowflake.com/en/user-guide/admin-trial-account) | high |
| Account: trial is 30 days or until the balance runs out (about $400, from marketing pages). **Standard** edition includes AI functions. Per credit: $2.00 in AWS US West and US East, $2.25 in AWS and Azure Canada. X-Small is 1 credit an hour, billed per second with a 60-second minimum on each start, so a 60-second auto-suspend matches the minimum charge. | [editions](https://docs.snowflake.com/en/user-guide/intro-editions), [pricing guide](https://www.snowflake.com/pricing/pricing-guide/), [warehouses](https://docs.snowflake.com/en/user-guide/warehouses-overview) | high / medium |
| Service users: `TYPE = SERVICE` users cannot use passwords; password sign-in for non-human users was blocked in Aug to Oct 2026. **Key-pair** auth: RSA >= 2048 bits, PKCS#8 PEM, two key slots for rotation. Python connector: `authenticator="SNOWFLAKE_JWT"` with `private_key_file` and `private_key_password`. Account identifier `org-account`. | [MFA rollout](https://docs.snowflake.com/en/user-guide/security-mfa-rollout), [user management](https://docs.snowflake.com/en/user-guide/admin-user-management), [key-pair](https://docs.snowflake.com/en/user-guide/key-pair-auth), [connector](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-connect) | high |

**For the contracts (FND-013):** `situation_embedding VECTOR(FLOAT, 768)` from
`AI_EMBED('snowflake-arctic-embed-m-v1.5', situation_text)`; the numeric
`feature_vector` is `VECTOR(FLOAT, n)` with n fixed by S2. Vectors are written by an
`INSERT ... SELECT` that casts an array, never by binding. Service users authenticate
with key pairs, matching S0's `.env.example`.

## 5. Snowflake Terraform provider

Spec items: Verify 5; section 14.3.

| Finding | Source | Conf. |
| --- | --- | --- |
| Provider **`snowflakedb/snowflake`** (moved from `Snowflake-Labs/snowflake`), latest **2.23.0** (2026-11-05), generally available; Terraform >= 1.1.5. OpenTofu is listed but untested. 2.23.0 sends `warehouse_type = STANDARD` when omitted. | [registry](https://registry.terraform.io/v1/providers/snowflakedb/snowflake), [releases](https://github.com/snowflakedb/terraform-provider-snowflake/releases) | high |
| Stable resources: `snowflake_database`, `snowflake_schema`, `snowflake_warehouse` (`warehouse_size = "XSMALL"`, `auto_suspend = 60`, `auto_resume = "true"` as a string, `initially_suspended`), `snowflake_account_role`, `snowflake_grant_privileges_to_account_role`, `snowflake_grant_account_role`, `snowflake_grant_database_role`, `snowflake_service_user` (`rsa_public_key`, `rsa_public_key_2`, `default_role`, `default_warehouse`). | [provider docs](https://github.com/snowflakedb/terraform-provider-snowflake/tree/main/docs) | high |
| Grants on tables: `on_schema_object { all { object_type_plural = "TABLES", in_schema = ... } }` and `future { ... }`. **There is no "all tables except one"** option. | provider docs | high |
| Provider block: `organization_name`, `account_name`, `user`, `authenticator = "SNOWFLAKE_JWT"`, `private_key` (PEM with real newlines), `private_key_passphrase`, `role`, `warehouse`. | provider docs `index.md` | high |
| Preview (needs `preview_features_enabled`): `snowflake_table`, `snowflake_stage`, `snowflake_file_format`, `snowflake_cortex_search_service` and others. Nothing S4 needs is preview, which also supports keeping tables in SQL migrations. | provider docs | high |
| Local tool: Terraform 1.16.5 is installed on the author's machine (1.17.1 is current). | local | local |

**For S4:** keeping `ASSET_KEY` out of `AGENT_ROLE`'s reach cannot be done with an
"all tables in `REF`" grant. Either move it to its own schema or grant `REF` tables one
by one. This is an open item for the S4 interview (the spec places it in `REF`).

## 6. MCP Python SDK and its HTTP transport

Spec items: Verify 6; section 10.

| Finding | Source | Conf. |
| --- | --- | --- |
| `mcp` **2.3.0** (2026-10-02), Python >= 3.10; 2.0.0 shipped 2026-07-28; the last 1.x is 1.30.0. Current spec revision **2026-07-28**, with two standard transports: stdio and **Streamable HTTP**. HTTP+SSE is absent from the spec's transport list but still in the SDK. | [PyPI](https://pypi.org/pypi/mcp/json), [spec](https://modelcontextprotocol.io/specification/latest.md) | high |
| v2 renamed `FastMCP` to **`MCPServer`**; transport options moved from the constructor into `run(transport="streamable-http", host=..., port=..., json_response=..., stateless_http=...)`. Defaults `127.0.0.1:8000`, path `/mcp`; request bodies capped at 4 MiB by default. | [migration](https://py.sdk.modelcontextprotocol.io/migration/index.md), [run](https://py.sdk.modelcontextprotocol.io/run/index.md) | high |
| Clients on the 2026-07-28 revision are stateless (no session ID), so any replica can answer; `stateless_http=True` affects only 2025-era clients. | [deploy](https://py.sdk.modelcontextprotocol.io/run/deploy/index.md) | high |
| ASGI: `mcp.streamable_http_app()` mounted in Starlette with `mcp.session_manager.run()` in the lifespan; `@mcp.custom_route("/health", methods=["GET"])` serves a Kubernetes liveness probe (custom routes are never authenticated). | [ASGI](https://py.sdk.modelcontextprotocol.io/run/asgi/index.md) | high |
| Structured output: a tool's return annotation becomes its output schema; a Pydantic model is used as is. Scalars are wrapped as `{"result": ...}`. | [structured output](https://py.sdk.modelcontextprotocol.io/servers/structured-output/index.md) | high |
| OpenTelemetry is on by default as middleware; each message gets a server span. | [what's new](https://py.sdk.modelcontextprotocol.io/whats-new/index.md) | high |

The import path differs between official pages (`mcp.server` in the README,
`mcp.server.mcpserver` in the migration guide); only `mcp.server.mcpserver` works in
2.3.0 (section 11).

**For the contracts:** tool payloads are Pydantic models used directly as tool inputs
and return types. S6's server factory uses `MCPServer` over Streamable HTTP with a
`/health` route.

## 7. Trace context from the agent to the MCP servers

Spec item: section 15 ("VERIFY how to pass trace context").

| Finding | Source | Conf. |
| --- | --- | --- |
| LangSmith's documented distributed tracing: the caller sends `langsmith-trace` (and optional `baggage`) headers from `run_tree.to_headers()`; the receiver uses `TracingMiddleware` or `tracing_context(parent=request.headers)`. Only trust these headers from internal callers. The page does not mention MCP. | [distributed tracing](https://docs.langchain.com/langsmith/distributed-tracing) | high |
| MCP standardises W3C trace context in the request's `_meta` (`traceparent`, `tracestate`, `baggage`; SEP-414, final). MCP SDK v2 propagates it in `_meta` when both ends run the SDK. FastMCP 4 also carries `traceparent` in `_meta`. | [SEP-414](https://modelcontextprotocol.io/seps/414-request-meta.md), [what's new](https://py.sdk.modelcontextprotocol.io/whats-new/index.md), [FastMCP telemetry](https://gofastmcp.com/servers/telemetry.md) | high / medium |
| LangSmith accepts OpenTelemetry at `https://api.smith.langchain.com/otel` (`LANGSMITH_OTEL_ENABLED`). A span whose parent never reaches LangSmith is dropped. | [OpenTelemetry](https://docs.langchain.com/langsmith/trace-with-opentelemetry) | high |
| **No official page documents the full chain** agent run, MCP call, server span, all in one LangSmith trace. Not confirmed: whether LangChain runs become the current OTel context that `MCPAdapter` would inject into `_meta`; whether `MCPAdapter` supports per-call headers. | — | open |

**For the contracts:** two routes exist. (a) W3C context in `_meta`, the MCP standard,
with server spans exported to LangSmith over OpenTelemetry; (b) `langsmith-trace` in
`_meta` or headers, read by the server into `tracing_context(parent=...)`. S2 reserves
a place for trace context on every tool request; S6 proves one route end to end and
records which. The local smoke test (section 11) showed route (a) working up to the
server: `traceparent` arrived in `_meta` with the client's trace ID. Static headers
also arrive, so route (b) is available if (a) does not join up in LangSmith.

## 8. TA-Lib

Spec items: Verify 7; section 12.4.

| Finding | Source | Conf. |
| --- | --- | --- |
| `TA-Lib` **0.8.3** (2026-10-28). Binary wheels for CPython 3.11 to 3.14 on Windows x64, manylinux x86_64 and aarch64, musllinux x86_64 and aarch64; the C library is statically linked, so no compiler or separate C install is needed. Supports numpy 2. | [PyPI](https://pypi.org/pypi/TA-Lib/0.8.3/json), [ta-lib-python](https://github.com/TA-Lib/ta-lib-python) | high |
| Windows: plain `pip install TA-Lib` worked in S0 and imports, with 61 pattern functions. | local | local |
| Linux: S0's CI installs the same wheel on Ubuntu. A `python:3.12-slim` image is expected to work the same way (glibc wheel); not run locally because Docker was not running. | S0 CI | high / open |
| All 19 detector names in spec 12.4 exist. Extra parameter `penetration` on `CDLDARKCLOUDCOVER` (default 0.5), `CDLMORNINGSTAR` and `CDLEVENINGSTAR` (0.3). Tweezer top and bottom have no detector (custom code, as the spec says); `CDLMATCHINGLOW` is related but different. | local (`talib.abstract`), [pattern list](https://ta-lib.github.io/ta-lib-python/func_groups/pattern_recognition.html) | local |

Output conventions, from the C sources ([ta-lib `src/ta_func`](https://github.com/TA-Lib/ta-lib/tree/main/src/ta_func), high):

| Detector | Output | Note |
| --- | --- | --- |
| `CDLDOJI`, `CDLDRAGONFLYDOJI`, `CDLGRAVESTONEDOJI` | 100 or 0 | No direction. **Gravestone is +100 although bearish**: meaning comes from the playbook entry, not the sign. |
| `CDLSPINNINGTOP`, `CDLMARUBOZU` | ±100 | Sign is the candle colour. |
| `CDLHAMMER`, `CDLINVERTEDHAMMER`, `CDLPIERCING`, `CDLMORNINGSTAR`, `CDL3WHITESOLDIERS` | 100 or 0 | Bullish only. |
| `CDLHANGINGMAN`, `CDLSHOOTINGSTAR`, `CDLDARKCLOUDCOVER`, `CDLEVENINGSTAR`, `CDL3BLACKCROWS` | -100 or 0 | Bearish only. |
| `CDLENGULFING`, `CDLHARAMI` | ±100 or ±80 | **±80 when the bodies match at one end.** One function gives the bullish and bearish playbook entries, split by sign. |
| `CDL3INSIDE`, `CDLRISEFALL3METHODS` | ±100 | Sign is the direction. |

No detector checks the prior trend: the spec's "must follow a decline/advance" is
context code's job. Gap-dependent: inverted hammer and shooting star (body gap),
morning and evening star (star gaps), piercing line and dark cloud cover (open beyond
the previous low or high). On 15-minute bars these fire mostly at the open, as the
spec's intraday note expects; dataset-builder S4 measures and documents any relaxation.

**For the contracts:** a pattern flag is one of bullish / bearish / none per playbook
entry, mapped from the detector and its sign by a fixed table, not the raw integer.

## 9. Market data providers

Spec items: Verify 8; section 8.4. The author is in Canada. Detail beyond the choice
(history depth, licence terms) belongs to the dataset-builder steps.

| Provider | Finding | Source | Conf. |
| --- | --- | --- | --- |
| **Alpaca** (stocks) | Free plan: **IEX feed only**, history since 2016, most recent 15 minutes restricted, 200 calls a minute. Paid ($99/month, full market): **not sold to Canadian residents** (Alpaca staff, 2026-08-14; Canadian approval targeted for around November 2026, launch not confirmed). Anyone can open a paper-only account, entitled to IEX data. No redistribution. | [market data API](https://docs.alpaca.markets/docs/about-market-data-api), [paper trading](https://docs.alpaca.markets/docs/paper-trading), [Alpaca forum](https://forum.alpaca.markets/t/is-the-market-data-subscription-available-in-canada/19519), [redistribution](https://alpaca.markets/support/redistribute-alpaca-api) | high / medium |
| **Coinbase Exchange** (crypto) | `GET https://api.exchange.coinbase.com/products/{id}/candles`, **no account**, granularity 900 s, at most 300 candles a request, 10 requests a second per IP. Lookback not documented. Coinbase is a registered restricted dealer in Canada. | [candles](https://docs.cdp.coinbase.com/exchange/reference/exchangerestapi_getproductcandles), [rate limits](https://docs.cdp.coinbase.com/exchange/rest-api/rate-limits) | high / medium |
| Kraken (crypto, fallback) | Public OHLC returns **only the latest 720 candles**. Full history is an official quarterly CSV download (currently through 2026-09-30). Registered in Canada. | [OHLC](https://docs.kraken.com/api/docs/rest-api/get-ohlc-data/), [downloadable data](https://support.kraken.com/hc/en-us/articles/360047124832) | high |
| Binance | Withdrew from Canada in 2023; regional status conflicting. Not used. | press, regional terms | medium |
| **Massive** (formerly Polygon.io; options) | Renamed 2025-10-30. Options plans: Basic $0, Starter $29, Developer $79, **Advanced $199 a month (historical quotes)**. **No historical Greeks or IV on any plan.** | [rename](https://massive.com/blog/polygon-is-now-massive), [options plans](https://massive.com/options) | high / medium |
| **Databento** (futures) | Pay as you go per GB; **$125 credit** for new accounts (6 months). CME `GLBX.MDP3` from 2010 includes MES and MNQ. Bars are 1-minute or 1-hour (no 15-minute); bars exist only for intervals with trades. One year of 1-minute MES and MNQ bars is likely well inside the credit; exact cost not confirmed. | [pricing](https://databento.com/pricing), [GLBX.MDP3](https://databento.com/catalog/cme/GLBX.MDP3), [OHLCV](https://databento.com/docs/schemas-and-data-formats/ohlcv) | high / low |

**For the contracts (FND-009):** the provider interface per asset class stays as the
spec says. IEX-only volume is self-consistent (volume is compared with normal for the
time of day on the same feed) and is noted in the dataset's quality report. Futures
need 15-minute bars built from 1-minute bars, with empty intervals handled. Option
Greeks and IV are computed in code.

## 10. LLM provider: DeepSeek

Spec item: developer decision 1. Chosen by the author (FND-007).

| Finding | Source | Conf. |
| --- | --- | --- |
| `deepseek-flash` = DeepSeek-V4.1-Flash-1017; `deepseek-v4-pro` = DeepSeek-V4-Pro-0813. Both: 1M context, 384K max output, tool calls, JSON output, thinking mode on by default. Legacy name `deepseek-v4-flash` is retired (still served). | [models and pricing](https://api-docs.deepseek.com/quick_start/pricing) | high |
| Price per million tokens, off-peak / peak. Flash: input $0.15 / $0.30 (cache hit $0.003 / $0.006), output $0.60 / $1.20. Pro: input $0.66 / $1.32 (cache hit $0.022 / $0.044), output $1.98 / $3.96. Peak is 01:00 to 04:00 and 06:00 to 10:00 UTC on weekdays; all else is off-peak (half price). | same | high |
| Concurrency per account: 2,500 (Flash), 500 (Pro); above that HTTP 429. Waiting requests receive keep-alive lines; a request that has not started inference after 10 minutes is closed. | [rate limits](https://api-docs.deepseek.com/quick_start/rate_limit) | high |
| Strict tool schemas are **beta**, at base URL `https://api.deepseek.com/beta`, with `strict: true` per function: every property required, `additionalProperties: false`; `minLength`, `maxLength`, `minItems`, `maxItems` unsupported. Tool use works in thinking mode from V3.2. | [tool calls](https://api-docs.deepseek.com/guides/tool_calls) | high |
| `langchain-deepseek` **1.1.1** (2026-09-22), from the `langchain-ai/langchain` repo, Python >= 3.10; class `ChatDeepSeek`, env var `DEEPSEEK_API_KEY`. The docs page still shows the older `deepseek-chat` / `deepseek-reasoner` names. | [PyPI](https://pypi.org/project/langchain-deepseek/), [LangChain docs](https://docs.langchain.com/oss/python/integrations/chat/deepseek) | high |
| Data: secondary sources consistently report that DeepSeek processes and stores data in China; whether API inputs are used for training is **not confirmed** from a primary source. | [Kaspersky](https://www.kaspersky.com/blog/deepseek-privacy-and-security/54643/), [VentureBeat](https://venturebeat.com/ai/is-deepseek-really-sending-data-to-china-lets-decode/) | low |

**For the contracts:** the candidate-proposal schema must fit strict mode (no length or
item-count limits in the schema; "up to 5 candidates" is enforced in code). Thinking
mode adds output tokens, which count in the model-cost metric.

## 11. Local checks

Run on 2026-11-10 on the author's machine (Windows 11, Python 3.12.16) in a throwaway
virtual env, before the project env was changed. No paid call was made.

**Resolution.** The new requirement set (section 2's versions plus
`langchain-deepseek==1.1.1`, `typesafe-sdk==0.7.5`) installed with `pip check` clean.
It pulled in `fastmcp` 4.1.7, `mcp-types` 2.3.0, `langchain-openai` 1.7.4 (through
`langchain-deepseek`) and `opentelemetry-api` 1.45.2. `alpaca-py` 0.45.0 resolves
against the same set without conflicts.

**MCP smoke test.** A server built with `MCPServer` (one tool returning a Pydantic
model, one `/health` custom route) ran over Streamable HTTP on localhost, and a client
used `langchain.mcp.MCPAdapter`:

| Check | Result |
| --- | --- |
| Import path | `from mcp.server.mcpserver import MCPServer, Context` works; `from mcp.server import MCPServer` does **not** (the README is wrong for 2.3.0). |
| Health route | `GET /health` returned 200. |
| List and call | `MCPAdapter` listed the tool with its argument schema (`asset_id`, `step_id`) and called it. The Pydantic result came back as a JSON text block in the LangChain tool output, so the agent side parses it back into the schema. Importing `langchain.mcp` warns that it is beta. |
| Static headers | Accepted as `{"mcpServers": {name: {"url": ..., "headers": {...}}}}` and received by the server. Passing a fastmcp `StreamableHttpTransport` object in the config is **rejected** by the adapter's config validation. |
| Trace context | With an OpenTelemetry span active on the client, the server received `traceparent` in the request's `_meta`, carrying **the client's trace ID** (`00-7587c996...`). Without an active span, no `traceparent` is sent. |

**DeepSeek.** With a dummy key, `init_chat_model("deepseek:deepseek-flash")` returned
`langchain_deepseek.ChatDeepSeek` with base URL `https://api.deepseek.com/v1`;
`with_structured_output` and `bind_tools` both construct for a candidate-proposal
schema. Strict tool schemas need the beta base URL (section 10), so it is a config
value, not the package default.

**Jev SDK.** `typesafe_sdk` 0.7.5 builds the four `decide` questions from spec 11.1
(`Choice` x2, a 5-level `Score`, `Noul`), and `TypeSafeClient(api_key=..., model=
"jev-1.14.0", base_url=...)` constructs. A `Score` serialises as
`{"type": "score", "instructions": ..., "criteria": [...]}`, matching the API docs.

**What this settles.** The MCP stack in FND-011 works end to end locally. Trace context
reaches the servers through the MCP standard route; what is still open is LangSmith's
side (whether LangChain runs become the active OpenTelemetry span, and whether server
spans exported to LangSmith join the agent's trace): foundation S6.

## Open items

Each item is owned by the step that first needs it.

| Item | Why it is open | Owner |
| --- | --- | --- |
| Jev rate limits and early-access caps | Shown only in the developer console | jev-decision S1 |
| Jev access | Author is creating a TypeSafe key; OpenRouter is the fallback | jev-decision S1 |
| DeepSeek thinking mode with tool calls through LangChain | Needs a paid call | agent S4 (paid test) |
| LangSmith price per extra trace; hourly event limit on fast replays | Not published / needs a real run | agent S5 |
| Agent-to-server trace link in one LangSmith trace | No official end-to-end recipe | foundation S6 |
| Keeping `ASSET_KEY` from `AGENT_ROLE` | No "all tables except one" grant | foundation S4 interview |
| Embedding cost per model; trial account needs a card for AI functions | Official rate table unreadable; account not created | foundation S4 |
| Bulk insert of vectors; `write_pandas` with VECTOR | Not documented | memory S5 |
| Coinbase 15-minute history depth; Alpaca storage terms | Not documented | dataset-builder S1 |
| Detector behaviour on 15-minute bars; gap-rule relaxations | Needs real data | dataset-builder S4 |
| Databento cost for MES and MNQ | Needs an account (`get_cost`) | dataset-builder S7 |
| Options data source and spend | Decided at that step, ceiling $199 | dataset-builder S8 |
| TA-Lib in a slim container image | Docker not running during S1 | platform S1 |
| LangGraph run state resume | No Snowflake checkpointer; spec's last-completed-step design stands | agent S1 |
| `editorial-ui` frontend specification | Out of S1's scope | web-app S2 |
