# LangSmith: free tier, experiments, tracing into MCP servers (issue #10)

All pages read 2026-11-11. The repo had no research-notes folder, so this lives in `docs/research/`.

## 1. Free tier (Developer plan) and paid pricing

| Item | Value | Source |
|---|---|---|
| Developer price / seats | $0, 1 seat max | https://www.langchain.com/langsmith-pricing |
| Included traces | 5k base traces / month | same |
| Plus | $39 per seat / month, unlimited seats, 10k base traces / month included, then pay as you go | same |
| Retention | Base 14 days; extended 180 days (older docs and third parties say 400; the live pages say 180) | https://www.langchain.com/langsmith-pricing , https://docs.langchain.com/langsmith/billing |
| Cap behavior (Developer, no card on file) | 5,000 traces/month, then HTTP 429; also 50,000 events/hour and 500 MB/hour ingest. A run create or update is 1 event, so create+update = 2. | https://docs.langchain.com/langsmith/usage-and-billing , https://docs.langchain.com/langsmith/billing |
| Adding a card | Billing page: removes the 5,000 cap, excess billed. Usage page: says only that hourly limits rise to 250k events / 2.5 GB. | same two pages |
| Unit price | "1 LSU = $1". The page gives no LSUs-per-trace figure. | https://www.langchain.com/langsmith-pricing |
| Extended upgrade | A base trace can be upgraded to extended by online evaluators, automation rules, or API feedback with `extend_trace_retention=true`. Billed in the period of the upgrade. | https://docs.langchain.com/langsmith/administration-overview |

### Per trace or per span?
Billing counts **traces**, not spans/runs. "LangSmith Traces (Base Charge)" counts all traces; the extended metric counts extended traces only (https://docs.langchain.com/langsmith/usage-and-billing). A trace is "a single execution of your application... can include many individual steps" (https://www.langchain.com/langsmith-pricing); a run is the span equivalent and a trace holds at most 25,000 runs (https://docs.langchain.com/langsmith/observability-concepts). Runs affect only the event rate limits. Evaluator and playground executions are also traces per the pricing page's trace definition.

### Overage price: NOT verified from an official page
The live pricing page and docs give no per-1k rate. Third-party sources (search snippets only, not fetched in full) report $2.50 per 1k base traces (long-standing) or about $5 per 1k (0.005 LSU at $1/LSU) after a 2026 move to LSUs. Estimates below show both. Check the usage calculator on https://www.langchain.com/langsmith-pricing (needs a browser) before relying on either.

## 2. Datasets and experiments

- `client.create_dataset(dataset_name=...)` then `client.create_examples(dataset_id=..., examples=[{"inputs":..., "outputs":...}])`. `client.evaluate(target, data="<dataset name>", evaluators=[...], experiment_prefix="...", max_concurrency=N)` records an experiment, shown on the Datasets & Experiments page. Source: https://docs.langchain.com/langsmith/evaluation-quickstart
- An experiment is one application version run over a dataset; it stores outputs, evaluator scores and execution traces per example. Datasets auto-version on change; versions can be tagged and pinned in CI. Source: https://docs.langchain.com/langsmith/evaluation-concepts
- `num_repetitions` on `evaluate`/`aevaluate` runs each example N times; each repetition is a separate run, scores are averaged with a std dev shown. This fits the brief's "3 seeds, report spread". Source: https://docs.langchain.com/langsmith/repetition
- Each experiment execution is a traced run, so it counts toward the trace allowance (inferred from the trace definition; no page states it in so many words).
- A full backtest is not a natural dataset example. The brief's 17.2 variant comparison is better logged as ordinary traces with `variant`/`run_id` metadata, plus a small dataset for the 16.3 behavior cases.

## 3. Trace context into MCP servers

Mechanism (official, HTTP-based): LangSmith distributed tracing uses a `langsmith-trace` header plus optional `baggage` (metadata/tags). Client: `get_current_run_tree().to_headers()`. Server options: `TracingMiddleware` (FastAPI/Starlette, langsmith>=0.1.133), `with ls.tracing_context(parent=request.headers):`, or `langsmith_extra={"parent": headers}`. Security: accept these headers only from trusted internal callers. Source: https://docs.langchain.com/langsmith/distributed-tracing

MCP-specific: the LangSmith docs contain **no MCP guidance** (that page and my searches found none). Facts that matter:
- MCP over HTTP: the agent's MCP client must put the headers on its HTTP requests (depends on the client library letting you set per-call headers; not verified for langchain-mcp-adapters). On the server, if it is a Starlette/FastAPI ASGI app, `TracingMiddleware` sets context per HTTP request; whether it carries into the tool handler needs a spike.
- MCP spec route: SEP-414 (status Final) documents `traceparent`, `tracestate`, `baggage` in the request's `_meta` for OpenTelemetry context. Source: https://modelcontextprotocol.io/seps/414
- Putting the `langsmith-trace` value in `_meta` and wrapping the tool handler in `tracing_context(parent=...)` is plausible, but I found no source confirming it. Unverified.
- OTel route: LangSmith ingests OTLP at `https://api.smith.langchain.com/otel`. To attach OTel spans to an existing LangSmith run, set attributes `langsmith.trace.id`, `langsmith.span.parent_id`, `langsmith.span.id`, `langsmith.span.dotted_order` to the parent run's values; a child whose parent never reaches LangSmith is silently dropped. Source: https://docs.langchain.com/langsmith/trace-with-opentelemetry
- Billing is per trace, so child runs created in MCP servers cost nothing extra if they attach to the agent's trace. A failed propagation silently creates extra root traces, which inflates the count.

Recommended spike: one agent call to one MCP tool over HTTP; confirm the tool's `@traceable` function shows as a child run.

## 4. Trace-volume estimate (brief section 15)

Assumptions: 4 stocks (26 steps per trading day, about 63 trading days per 3 months) plus 1 crypto asset (96 steps/day, 91 calendar days). Shared 15-minute clock, so there are 96 clock steps per day (crypto steps every slot). Tier 1 = one trace per clock step (grouped across assets). Tier 2 = one trace per asset per step reaching it; the Tier 2 rate p is unknown, so 10% and 100% are shown. The 5-day run is 5 trading days and 5 crypto days.

Asset-steps (upper bound for Tier 2 traces):
- 5-day: stocks 4 x 26 x 5 = 520; crypto 96 x 5 = 480; total 1,000.
- 3-month: stocks 4 x 26 x 63 = 6,552; crypto 96 x 91 = 8,736; total 15,288.

Tier 1 traces: 5-day 96 x 5 = 480; 3-month 96 x 91 = 8,736.

| Run | Tier 1 | Tier 2 at 10% | Tier 2 at 100% | Total (10% / worst) |
|---|---|---|---|---|
| 5-day | 480 | 100 | 1,000 | 580 / 1,480 |
| 3-month | 8,736 | 1,529 | 15,288 | 10,265 / 24,024 |
| 2 variants x 3 runs x 3-month (6 runs) | 52,416 | 9,174 | 91,728 | 61,590 / 144,144 |

Only `memory_off` and `memory_on` use an LLM; `buy_hold` and `pattern_rules` need no LLM traces.

Against the free tier (5,000 base traces per month, 429 after, no card): a 5-day run fits. One 3-month run does not, even with zero Tier 2 (Tier 1 alone is 8,736). The full comparison is 12x to 29x the free cap.

Cost beyond free at the unverified rates ($2.50 or $5 per 1k), counting traces above the included amount, ignoring extended upgrades:
- 3-month run, worst 24,024: (24,024 - 5,000) = 19,024 over, about $48 to $95. At 10%, 10,265: 5,265 over, about $13 to $26.
- Full comparison, worst 144,144: 139,144 over, about $348 to $696. At 10%, 61,590: 56,590 over, about $141 to $283.
- On Plus ($39 per seat, 10k included) the included amount is 10k instead of 5k.

Levers: Tier 1 is the bulk (8,736 of 10,265 at 10%), so log Tier 1 to Snowflake and trace only Tier 2 and behavior tests in LangSmith, or sample Tier 1; use short windows for tuning. (An SDK sampling-rate setting may exist; not verified here.)

## 5. Contradictions and complications for the brief
- Base traces expire after 14 days. The brief saves the LangSmith trace ID on the episode in Snowflake so any trade can be followed back; after 14 days those IDs dangle unless the trace is upgraded to extended (180 days, extra fee).
- Tier 1 trace volume dominates, which the brief's "reduce Tier 1 if needed" note anticipates but does not size.
- Hourly limit of 50,000 events with no card: a simulation running much faster than real time with many nested runs (2 events each) can hit it even under the monthly cap.

## Not verified
- Official per-trace overage price, and whether adding a card removes the monthly cap (the two official pages word it differently).
- Whether a LangSmith trace header passed through HTTP headers or MCP `_meta` works with the chosen MCP client and server libraries.
- Whether experiment runs are billed like application traces.
