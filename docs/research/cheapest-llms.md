# Cheapest tool-calling LLMs beyond Anthropic, OpenAI, Google and DeepSeek (issue #40)

Read on 2026-11-12 from official provider pages and the official LangChain docs. Prices are USD per 1M tokens, text only. Where an official page is silent or could not be read, this note says "not found" and says what was tried. Nothing here is from memory. Format follows `docs/research/deepseek.md` on the `research/deepseek` branch (issue #39).

How the pages were read: most pricing pages draw their tables with JavaScript, and the summarising fetch tool returned empty tables for several of them (Kimi, Alibaba, AWS). For those I downloaded the raw page or the provider's own `.md` / JSON source and read the table data from it. Where that was not possible, the row is labelled. Secondary sources (a router's or third party's listing of a provider's price) are labelled "secondary".

## Sources (all read 2026-11-12)

Moonshot (Kimi)
- Pricing (table data read from raw page): https://platform.kimi.ai/docs/pricing/chat
- Model list: https://platform.kimi.ai/docs/models.md
- Thinking models: https://platform.kimi.ai/docs/guide/use-thinking-models.md
- Kimi K3 guide (access requirements): https://platform.kimi.ai/docs/guide/kimi-k3-quickstart.md
- Recharge and rate limits (table data read from raw page): https://platform.kimi.ai/docs/pricing/limits

Alibaba Cloud Model Studio (Qwen, international / Singapore)
- Model pricing: https://www.alibabacloud.com/help/en/model-studio/model-pricing
- Rate limits: https://www.alibabacloud.com/help/en/model-studio/rate-limit
- Deep thinking (default thinking mode per model): https://www.alibabacloud.com/help/en/model-studio/deep-thinking
- Product terms (Model Studio clauses): https://www.alibabacloud.com/help/en/legal/latest/alibaba-cloud-international-website-product-terms-of-service-v-3-8-0

Z.ai (Zhipu, GLM)
- Pricing: https://docs.z.ai/guides/overview/pricing
- GLM-5.3-Flash / FlashX: https://docs.z.ai/guides/vlm/glm-5.3-flash.md
- GLM-4.7 family: https://docs.z.ai/guides/llm/glm-4.7.md
- Thinking mode: https://docs.z.ai/guides/capabilities/thinking-mode.md
- Privacy policy: https://docs.z.ai/legal-agreement/privacy-policy.md
- Terms of use and Additional Terms for API Services: https://docs.z.ai/legal-agreement/terms-of-use.md

MiniMax
- Pay-as-you-go pricing (table data read from raw page): https://platform.minimax.io/docs/guides/pricing-paygo
- Model invocation: https://platform.minimax.io/docs/guides/text-generation.md
- Tool use and interleaved thinking: https://platform.minimax.io/docs/guides/text-m3-function-call.md
- Rate limits: https://platform.minimax.io/docs/guides/rate-limits.md

Mistral
- API pricing: https://docs.mistral.ai/inference/pricing.md
- Ministral 3 3B model card: https://docs.mistral.ai/models/ministral-3-3b-25-12.md
- Zero data retention: https://docs.mistral.ai/admin/monitor-comply/zero-data-retention.md
- Commercial terms: https://legal.mistral.ai/terms/commercial-terms-of-service

xAI
- Models and pricing (price data read from raw page JSON): https://docs.x.ai/developers/models

Amazon Nova (Bedrock)
- AWS Price List, official bulk file for the `AmazonBedrock` offer, published 2026-11-11: https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock/current/index.json
- Nova Micro model card: https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-micro.html
- Bedrock data protection: https://docs.aws.amazon.com/bedrock/latest/userguide/data-protection.html
- (The rendered pricing pages https://aws.amazon.com/bedrock/pricing/ and https://aws.amazon.com/nova/pricing/ load prices by script and showed no numbers.)

Hosts and routers
- Groq models: https://console.groq.com/docs/models.md ; rate limits: https://console.groq.com/docs/rate-limits.md ; your data: https://console.groq.com/docs/your-data.md
- Cerebras: https://inference-docs.cerebras.ai/models/overview.md ; https://inference-docs.cerebras.ai/models/openai-oss.md ; https://inference-docs.cerebras.ai/models/qwen-3.8-27b.md
- Together serverless models: https://docs.together.ai/docs/serverless-models.md
- Fireworks serverless pricing: https://docs.fireworks.ai/serverless/pricing.md
- DeepInfra model list (the public JSON that feeds its site): https://api.deepinfra.com/models/list ; data privacy: https://deepinfra.com/docs/data
- OpenRouter model list API: https://openrouter.ai/api/v1/models ; limits: https://openrouter.ai/docs/api-reference/limits.md ; data collection: https://openrouter.ai/docs/guides/privacy/data-collection.md

Big three re-check
- Anthropic pricing: https://platform.claude.com/docs/en/about-claude/pricing.md
- OpenAI pricing: https://developers.openai.com/api/docs/pricing
- Google Gemini pricing: https://ai.google.dev/gemini-api/docs/pricing ; deprecations: https://ai.google.dev/gemini-api/docs/deprecations

LangChain (official docs, `docs.langchain.com/oss/python/integrations/chat/`): `groq`, `bedrock`, `fireworks`, `together`, `mistralai`, `xai`, `openrouter`, `qwen`, `moonshot`, `cerebras`, `amazon_nova`, and the index page `index.md`.

## Cost table

Workload per full evaluation: 17,000 input tokens and 1,000 output tokens in total across 4 calls. No caching, no batch discount, no thinking overhead, standard (not priority) rates.

Arithmetic, shown once: cost per evaluation = 17,000 x input price / 1,000,000 + 1,000 x output price / 1,000,000. Run cost = cost per evaluation x number of evaluations.
Example, `claude-haiku-5-5` (0.10 in, 0.50 out): 17,000 x 0.10 / 1,000,000 = $0.00170, plus 1,000 x 0.50 / 1,000,000 = $0.00050, total $0.00220 per evaluation. At 2,300 evaluations: 0.0022 x 2,300 = $5.06. This matches the sanity anchor.
Example, `qwen3.7-flash` (0.03 in, 0.13 out): 17,000 x 0.03 / 1,000,000 = $0.00051, plus 1,000 x 0.13 / 1,000,000 = $0.00013, total $0.00064. At 2,300 evaluations: $1.47.

Ranked cheapest first. Rows marked "tiny" are models of about 1B parameters or less; tool calling is listed on the provider's tag, but a model that small is unlikely to select records reliably, and none was tested. Rows marked "unverified tools" could not be confirmed as tool-capable on an official page. All rows exclude free options (see the next section).

| Rank | Model (provider) | In | Out | Per eval | 800 evals | 2,300 evals | 4,600 evals | Price source |
|---|---|---|---|---|---|---|---|---|
| 1 | Llama 3.2 1B Instruct (DeepInfra), tiny | 0.005 | 0.01 | $0.00010 | $0.08 | $0.22 | $0.44 | DeepInfra model list JSON |
| 2 | Qwen3.5 0.8B (DeepInfra), tiny | 0.01 | 0.05 | $0.00022 | $0.18 | $0.51 | $1.01 | DeepInfra model list JSON |
| 3 | Llama 3.1 8B Instruct Turbo (DeepInfra) | 0.02 | 0.04 | $0.00038 | $0.30 | $0.87 | $1.75 | DeepInfra model list JSON |
| 4 | Mistral Nemo (DeepInfra) | 0.029 | 0.03 | $0.00052 | $0.42 | $1.20 | $2.41 | DeepInfra model list JSON |
| 5 | `qwen3.7-flash`, prompts up to 32K (Alibaba) | 0.03 | 0.13 | $0.00064 | $0.51 | $1.47 | $2.94 | Alibaba pricing page |
| 6 | gpt-oss-20b (DeepInfra) | 0.03 | 0.14 | $0.00065 | $0.52 | $1.49 | $2.99 | DeepInfra model list JSON |
| 7 | Amazon Nova Micro, US East (Bedrock) | 0.035 | 0.14 | $0.00073 | $0.59 | $1.69 | $3.38 | AWS Price List |
| 8 | gpt-oss-120b (DeepInfra) | 0.037 | 0.17 | $0.00080 | $0.64 | $1.84 | $3.68 | DeepInfra model list JSON |
| 9 | Nemotron 3.5 Lightning 30B A3B (Fireworks), unverified tools | 0.05 | 0.20 | $0.00105 | $0.84 | $2.42 | $4.83 | Fireworks pricing page |
| 10 | Amazon Nova Lite, US East (Bedrock) | 0.06 | 0.24 | $0.00126 | $1.01 | $2.90 | $5.80 | AWS Price List |
| 11 | Amazon Nova Lite, Canada Central (Bedrock) | 0.064 | 0.256 | $0.00134 | $1.08 | $3.09 | $6.18 | AWS Price List |
| 12 | gpt-oss-20b (Groq) | 0.075 | 0.30 | $0.00158 | $1.26 | $3.62 | $7.25 | Groq models page |
| 13 | `GLM-4.7-FlashX` (Z.ai) | 0.07 | 0.40 | $0.00159 | $1.27 | $3.66 | $7.31 | Z.ai pricing page |
| 14 | `GLM-4-32B-0414-128K` (Z.ai), unverified tools | 0.10 | 0.10 | $0.00180 | $1.44 | $4.14 | $8.28 | Z.ai pricing page |
| 15 | `ministral-3b-2512` (Mistral) | 0.10 | 0.10 | $0.00180 | $1.44 | $4.14 | $8.28 | Mistral pricing page |
| 16 | `gemini-2.5-flash-lite` (Google), see big-three section | 0.10 | 0.40 | $0.00210 | $1.68 | $4.83 | $9.66 | Google pricing page |
| 17 | `claude-haiku-5-5` (Anthropic) | 0.10 | 0.50 | $0.00220 | $1.76 | $5.06 | $10.12 | Anthropic pricing page |
| 18 | `gpt-6-luna` (OpenAI) | 0.10 | 0.50 | $0.00220 | $1.76 | $5.06 | $10.12 | OpenAI pricing page |
| 19 | `ministral-8b-2512` (Mistral) | 0.15 | 0.15 | $0.00270 | $2.16 | $6.21 | $12.42 | Mistral pricing page |
| 20 | `qwen3.8-flash` (Alibaba) | 0.15 | 0.47 | $0.00302 | $2.42 | $6.95 | $13.89 | Alibaba pricing page |
| 21 | `GLM-5.3-Flash` (Z.ai) | 0.15 | 0.50 | $0.00305 | $2.44 | $7.02 | $14.03 | Z.ai pricing page |
| 22 | Qwen3.5 9B (Together) | 0.17 | 0.25 | $0.00314 | $2.51 | $7.22 | $14.44 | Together models page |
| 23 | `MiniMax-M3.1-Flash` (MiniMax) | 0.15 | 0.60 | $0.00315 | $2.52 | $7.25 | $14.49 | MiniMax pricing page |
| 24 | `deepseek-flash`, off-peak (DeepSeek) | 0.15 | 0.60 | $0.00315 | $2.52 | $7.25 | $14.49 | `deepseek.md` |
| 25 | gpt-oss-120b (Fireworks) | 0.15 | 0.60 | $0.00315 | $2.52 | $7.25 | $14.49 | Fireworks pricing page |
| 26 | `mistral-small-2603` (Mistral) | 0.15 | 0.60 | $0.00315 | $2.52 | $7.25 | $14.49 | Mistral pricing page |
| 27 | `deepseek-flash`, peak (DeepSeek) | 0.30 | 1.20 | $0.00630 | $5.04 | $14.49 | $28.98 | `deepseek.md` |
| 28 | gpt-oss-120b (Cerebras) | 0.35 | 0.75 | $0.00670 | $5.36 | $15.41 | $30.82 | Cerebras model page |
| 29 | `gemini-3.5-flash-lite` (Google) | 0.30 | 2.50 | $0.00760 | $6.08 | $17.48 | $34.96 | Google pricing page |
| 30 | `grok-build-0.1` (xAI), unverified tools | 1.00 | 2.00 | $0.01900 | $15.20 | $43.70 | $87.40 | xAI models page |
| 31 | `kimi-k3.1-pro` (Moonshot) | 2.00 | 10.00 | $0.04400 | $35.20 | $101.20 | $202.40 | Kimi pricing page |
| 32 | `kimi-k3` (Moonshot) | 3.00 | 15.00 | $0.06600 | $52.80 | $151.80 | $303.60 | Kimi pricing page |

Rates for rows 17, 18, 24, 27 and 29 come from the earlier research notes and were re-checked today on the Anthropic, OpenAI and Google pages (same numbers). DeepSeek was not re-read.

What the table leaves out, and why it matters:

- Thinking tokens. Models that always think (Kimi K3 and K3.1 Pro, GLM-5.3-Flash, MiniMax at default effort, Qwen3.7/3.8 Flash by default) bill the thinking as output. If a call thinks for 2,000 tokens, output grows well beyond the 1,000 assumed. Output is 4x to 5x the price of input on most rows, so this can double the cost of the thinking models. Whether Alibaba bills thinking tokens as output: not found on the pages read. Not measured for any model.
- Caching. Not applied. Cached-input rates exist on most providers (listed below) and would lower the input part a lot, since the loop repeats context.
- Batch. Alibaba (50% on the flash models), Mistral (50%), Amazon Bedrock (about 50%), Kimi (60% of standard price) and OpenAI (Flex/Batch 50%) offer batch rates. They suit a backtest that is not real-time. Not applied above.

## Free options

| Option | What it is | Tool calling | Catch |
|---|---|---|---|
| Z.ai `GLM-4.7-Flash` | Free input, output and cached input (Z.ai pricing page) | Z.ai lists function calling on the GLM-4.7 family page; I did not confirm it for this exact model | Rate limit for free models: not found. API terms say API content is not used to improve services unless you agree. |
| Z.ai `GLM-4.5-Flash` | Free (pricing page) | Not confirmed | Same |
| Alibaba free quota | 1M tokens, valid 90 days, on `qwen3.8-flash` and the `qwen3.7-flash` alias only; the dated `qwen3.7-flash-2026-07-15` has none (pricing page) | Not confirmed per model (see the `qwen3.7-flash` section) | 1M tokens is about 59 full evaluations. Singapore deployment only. |
| Google AI Studio free tier | `gemini-2.5-flash-lite` and Gemma 4 are "free of charge" (Google pricing page) | Yes for Gemini | "Used to improve our products: Yes" on the free tier. Free-tier rate limits: not found on the pricing page. |
| Groq free plan | `openai/gpt-oss-20b`: 30 requests per minute, 1K per day, 8K tokens per minute, 200K per day (Groq rate-limits page) | Yes | 8K tokens per minute fits about 2 evaluations per minute; 200K tokens per day is about 11 evaluations per day. Too slow for a 800-evaluation run. |
| OpenRouter `:free` models | 15 tool-capable free listings today (model list API), for example `google/gemma-4-31b-it:free`, `nvidia/nemotron-3.5-lightning:free`, `thinkingmachines/inkling-2-small:free`, plus the `openrouter/free` auto-router | Listed as tools-capable in the model list API (secondary, router's own list) | Limits: 20 requests per minute, and 50 requests per day if you have bought under $10 of credits, 1,000 per day at $10 or more (OpenRouter limits page). 50 per day is 12 evaluations; 1,000 per day is 250. Free listings come and go (one expires 2026-11-13, another 2026-12-31). Upstream provider data terms for free models: not found. |
| Together `Prism-ML/Ternary-Bonsai-27B` | Free input and output (Together models page) | "Function calling: Yes" on the page | Rate limits: not found. Single listing, looks experimental. |

OpenRouter free models are usable for a small pilot (tens of evaluations a day) but not for a 800 to 4,600 evaluation run, and the model behind a free listing can disappear. The auto-router `openrouter/free` also changes the model between calls, which breaks a comparable evaluation.

## The five cheapest practical models: details

"Practical" here means not a tiny (1B-class) model, tool calling confirmed or plausible, and an official price. In order: Llama 3.1 8B Turbo (DeepInfra), `qwen3.7-flash` (Alibaba), gpt-oss-20b (DeepInfra), Amazon Nova Micro, Nemotron 3.5 Lightning (Fireworks). Several more models sit just behind them and are described in the provider sections below.

### 1. Llama 3.1 8B Instruct Turbo (DeepInfra), $0.02 in / $0.04 out

- Context 131,072 tokens, tags `tools`, `json`, `non-reasoning`, `flex`, fp8 quantisation (DeepInfra model list JSON, a first-party feed but not a pricing page). Cached-input price: none listed. The `deprecated` field is empty for this model.
- OpenRouter's router listing shows `meta-llama/llama-3.1-8b-instruct` at the same $0.02 / $0.04 (secondary).
- Pinned ID? The ID is the Hugging Face name, not dated. Whether DeepInfra swaps the serving build behind it: not found.
- LangChain: no dedicated DeepInfra chat page in the official LangChain docs (the `chat/deepinfra` page returned 404). DeepInfra offers an OpenAI-compatible endpoint, so `langchain-openai` `ChatOpenAI` with `base_url` works in principle. DeepInfra's docs have a LangChain integration page (listed in its sidebar), not read. LangChain's own warning: `ChatOpenAI` only targets the official OpenAI spec and does not extract or preserve non-standard fields such as `reasoning_content`. Fine for a non-thinking model like this one.
- Data: "input data is not stored to disk", "we do not train on your data", "we do not log the content of your requests" (DeepInfra data privacy page). Exceptions apply only to Google and Anthropic models. Bulk/batch APIs may store data briefly.
- Where requests are processed: not found.
- Rate limits on free and lowest paid tier: not found (the rate-limits page could not be read; the URL I tried returned only the site shell).
- Canada signup and payment: not found.
- Quality: a plain 8B model. Whether it picks records reliably in a 4-call loop is unknown and would need a pilot.

### 2. `qwen3.7-flash` (Alibaba Model Studio, international / Singapore), $0.03 in / $0.13 out

- Price depends on prompt size per request: up to 32K tokens $0.03 / $0.13, 32K to 256K $0.10 / $0.40, 256K to 1M $0.20 / $0.80 (pricing page). The workload (17,000 tokens over 4 calls) stays in the first tier.
- Batch: 50% off. Context cache discount exists; the page says it cannot stack with batch. The cached-token rate is not on the page. Free quota 1M tokens, 90 days, on the alias only.
- Context window up to 1M. Hybrid thinking, "thinking mode enabled by default" for the Qwen3.7 Flash series (deep-thinking page). Whether thinking is billed as output: not found. How to switch it off: the page describes it as hybrid, but I did not confirm the exact parameter name.
- Pinned ID: the alias `qwen3.7-flash` currently equals `qwen3.7-flash-2026-07-15` (a dated, pinned ID, no free quota). Use the dated ID for a reproducible run.
- Rate limit: 15,000 requests per minute and 5,000,000 tokens per minute for `qwen3.7-flash` on the international deployment (rate-limit page, static limits). Far above need.
- Tool calling: the function-calling page exists and the model family is on it; I did not confirm a model-by-model row for `qwen3.7-flash`. Treat as likely, not verified.
- LangChain: `langchain-qwq`, class `ChatQwen`, marked "beta" (official LangChain Qwen page). Tool calling and structured output are ticked.
- Data: Product Terms say Alibaba Cloud will not use Member Content "to develop or improve the models on the Service" unless you separately consent. Content "will be transferred to, stored, and processed in the country where Alibaba Cloud, its affiliates, or its sub-contractors maintain facilities", which may differ from your location. The pricing page labels this deployment "Singapore", but the terms do not tie processing to Singapore. Governed by Singapore law for the Singapore entity (that came through a search-engine summary, not read on the page itself).
- Canada signup and payment: not found.

### 3. gpt-oss-20b (DeepInfra), $0.03 in / $0.14 out (Groq: $0.075 / $0.30)

- DeepInfra: context 131,072, tags `tools`, `reasoning`, `json`, `structured-output`, bf16. It is a reasoning model, so it will emit thinking tokens (billed as output).
- Groq: `openai/gpt-oss-20b`, 131,072 context, 65,536 max completion, about 1,000 tokens per second, Developer plan 250K tokens per minute and 1K requests per minute (Groq models page). Groq's page says the model supports tool use and structured output.
- Open-weight OpenAI model; same weights on both hosts. Pinned ID: not dated.
- LangChain for Groq: `langchain-groq`, `ChatGroq`, "beta" (official page).
- Data (Groq): "By default, Groq does not retain customer data for inference requests"; may log inputs and outputs up to 30 days for troubleshooting or abuse; batch files kept 30 days; retained data is in Google Cloud buckets in the United States (Groq your-data page). Whether Groq trains on data: not found in the page text I searched.
- Canada signup and payment on either host: not found.

### 4. Amazon Nova Micro (Bedrock), $0.035 in / $0.14 out, cached input $0.00875

- Source: AWS Price List for the `AmazonBedrock` offer, published 2026-11-11, US East (N. Virginia), on-demand: input $0.000035 per 1K tokens, output $0.00014 per 1K, cache read $0.00000875 per 1K. Batch inference is half price ($0.0175 / $0.07). The rendered AWS pricing pages show no numbers (script-loaded).
- No Canada (Central) price row for Nova Micro in the price list. The model card says in-region support in us-east-1 and a few others; other regions via geo cross-region inference (IDs `us.amazon.nova-micro-v1:0`). Nova Lite does have a Canada (Central) row at $0.064 / $0.256. So from eastern Canada, Micro would route through the US.
- Model card: context 128K, knowledge cutoff Oct 2024, "Client-side tool calling" and "Structured outputs" listed, lifecycle "Active". The card also shows "EOL no sooner than Dec 05, 2025" and "Legacy period: at least 6 months". Those are old dates and Nova Micro is a first-generation model, so retirement risk is real and I did not find a current end-of-life date.
- Text only. Model ID `amazon.nova-micro-v1:0` is versioned.
- LangChain: `langchain-aws`, class `ChatBedrockConverse` (and `ChatBedrock`, marked "beta"; the Converse row's status was cut off in my read). There is also `langchain-amazon-nova`, class `ChatAmazonNova`, "beta", but that targets Amazon's separate Nova API (`nova.amazon.com`), whose prices I did not look up.
- Data: the Bedrock data-protection page describes model-provider isolation (model providers have no access to deployment accounts). The sentence stating that prompts are not used to train models: not found in the text I retrieved.
- Canada: an AWS account is not geo-blocked for Canada in any text I read, and Canada (Central) is a priced region; payment methods: not found.
- Rate limits: not found (Bedrock quotas page not read).
- Quality: a very small text model. Pilot needed.

### 5. NVIDIA Nemotron 3.5 Lightning 30B A3B (Fireworks), $0.05 in / $0.01 cached / $0.20 out

- Source: Fireworks serverless pricing page (Standard tier). Priority tier is $0.0625 / $0.0125 / $0.25.
- Tool calling, context size, rate limits, data terms, Canada access and thinking behaviour for this model: not found (I read only the pricing page).
- LangChain: `langchain-fireworks`, `ChatFireworks`, "beta" (official page).
- A second Fireworks row, "Rune 26B-A4B", is priced $0.042 input, $0.0084 cached and "$0.00" output on the page. I did not look into it.

## Provider by provider

For each provider: its cheapest current model that I could confirm with tools (or noted if not), plus the rest of the requested checks.

### Moonshot AI (Kimi)

The Kimi model list holds three current models: `kimi-k3.1-pro`, `kimi-k3.1-pro-highspeed`, `kimi-k3`. Everything older is "Deprecated", or "no longer available to newly registered users" from 2026-10-31 with retirement planned for late December 2026 (`kimi-k2.7-code`, `kimi-k2.7-code-highspeed`, `kimi-k2.6`, model list and pricing pages). So a new account cannot use the cheap K2 models.

| Model | Input | Cached input | Output | Context |
|---|---|---|---|---|
| `kimi-k3.1-pro` | 2.00 | 0.20 | 10.00 | 1,048,576 |
| `kimi-k3.1-pro-highspeed` | 4.00 | 0.20 | 20.00 | 1,048,576 |
| `kimi-k3` | 3.00 | 0.30 | 15.00 | 1,048,576 |
| `kimi-k2.6` (not for new users) | 0.95 | 0.16 | 4.00 | 262,144 |

(The same table has two more columns, 2.00/4.00 for `kimi-k3.1-pro` and 3.00/6.00 for `kimi-k3`, which I read as cache-write prices for 5 minute and 1 hour retention; the column headers were not in the data I extracted, so that reading is an inference.)

- Batch API: 60% of the standard price for `kimi-k3.1-pro` and `kimi-k3`.
- Thinking: `kimi-k3.1-pro` "always reasons"; the `thinking` parameter is not supported; `reasoning_effort` accepts low, high, max, default max. `kimi-k3` also has thinking always on. Reasoning tokens count toward `max_tokens`. In tool loops you must pass the full assistant message, including `reasoning_content`, back each turn.
- Tool calling: yes, `tool_choice` and dynamic tool loading documented. Structured output / JSON mode: documented.
- Free tier: none found. Flagship models "unlock after a successful top-up (minimum $1)"; a $5 cumulative top-up earns a $5 voucher.
- Rate limits by cumulative recharge (limits page, tier table): Tier0 ($1): concurrency 1, 3 requests per minute, 500,000 tokens per minute, 1,500,000 tokens per day. Tier1 ($10): 3 concurrent, 100 RPM, 2M TPM, unlimited per day. The column order (concurrency, RPM, TPM, TPD) is read from the page's concept list. At Tier0, 3 requests per minute makes a 4-call evaluation take about 80 seconds, so a top-up of $10 or more is needed for a run.
- LangChain: no Moonshot package on the official LangChain docs. The chat integrations index lists `ChatMoonshot` from a community package, `langchain-moonshot` (github.com/ArcadiaLin/langchain-moonshot), not LangChain-maintained. Using `ChatOpenAI` with Moonshot's OpenAI-compatible base URL (`https://api.moonshot.ai/v1`) loses `reasoning_content`, per the LangChain note quoted above, which Kimi requires you to pass back. So Kimi in a LangGraph tool loop needs the community class or custom handling.
- Pinned ID: `kimi-k3`, `kimi-k3.1-pro` are not dated. Alias or pinned: not found.
- Terms, retention, training, processing location, Canada access: not found. The pages I tried (pricing, model list, quickstarts) do not cover them; I did not locate a terms or privacy page. Prices are "exclusive of applicable taxes", calculated at checkout by your jurisdiction.
- Verdict: the cheapest current Kimi is `kimi-k3.1-pro` at about $0.044 per evaluation, 20 times Haiku. Not a candidate on price.

### Alibaba (Qwen)

Cheapest current text models, Singapore / International (pricing page), per 1M tokens:

| Model ID | Input | Output | Batch | Notes |
|---|---|---|---|---|
| `qwen3.7-flash` (alias for `qwen3.7-flash-2026-07-15`), up to 32K | 0.03 | 0.13 | 50% | 1M context; tiers above 32K |
| `qwen-flash` (alias for `qwen-flash-2025-07-28`), up to 256K | 0.05 | 0.40 | 50% | Thinking not on by default (deep-thinking page) |
| `qwen3.5-flash` | 0.10 | 0.40 | 50% | |
| `qwen3.8-flash` | 0.15 | 0.47 | not listed | 1M free tokens |
| `qwen3.7-plus`, up to 256K | 0.4 | 1.6 | not listed | "Limited-time 20% off" label on the alias |
| `qwen3-coder-flash`, up to 32K | 0.3 | 1.5 | | |

The Model Studio pricing page also lists third-party models (MiniMax, and the rate-limit page names `kimi-k3` and `deepseek-v4-pro-0813`). I did not read those rows.
- Free quota: Singapore only, 90 days, 1M tokens, on a few models.
- Rate limits: `qwen3.7-flash` and `qwen3.6-flash` 15,000 RPM, 5,000,000 TPM (static); `qwen3.8-flash` uses dynamic rate limiting that scales with monthly spend (rate-limit page, last updated 2026-11-12).
- LangChain: `langchain-qwq`, `ChatQwen`, beta.
- Data and Canada: see the Qwen section above.

### Z.ai (Zhipu, GLM)

Pricing page, per 1M tokens, text models: `GLM-5.3-Flash` 0.15 in / 0.03 cached / 0.50 out; `GLM-5.3-FlashX` 0.37 / 0.075 / 1.25; `GLM-4.7-FlashX` 0.07 / 0.01 / 0.40; `GLM-4-32B-0414-128K` 0.1 / - / 0.1; `GLM-4.7-Flash` and `GLM-4.5-Flash` free; `GLM-4.6V-FlashX` 0.04 / 0.004 / 0.40 (vision model). "Cached input storage" is "Limited-time Free".

- `GLM-5.3-Flash`: 1M context, 128K max output, 320B total / 18B active parameters. Function calling, context caching, structured output supported (model page). Thinking is forced on: "`thinking.type` only supports `enabled`; thinking cannot be disabled", and `reasoning_effort: max` is recommended. That makes it a poor fit for a cheap loop, because thinking tokens are billed as output.
- `GLM-4.7` family (includes `GLM-4.7-FlashX` and `GLM-4.7-Flash`): 200K context, 128K output, thinking on by default but can be disabled per request (thinking-mode page, "Turn-level Thinking"). Interleaved thinking: on by default on the Coding Plan endpoint, off by default on the standard API.
- `GLM-4-32B-0414-128K`: only the price is on the page (0.1 / 0.1). Tool calling: not found.
- Rate limits: the rate-limit page is script-rendered and returned no numbers: not found.
- LangChain: Z.ai has its own "LangChain Integration" page in its docs; the official LangChain docs have no `zhipuai` chat page at the URL I tried (404). Not read further. Package status: not found.
- Processing location: "We generally provide the Services from Singapore" (privacy policy; the operator is a Singapore company).
- Training and retention: the general privacy policy says input data is kept as long as you have an account and may be used to improve models. For API customers, the terms say: "For enterprises and developers using API Services, we will not use your User Content for developing or improving Services unless you explicitly agree to such use."
- Pinned ID: not found (names such as `glm-5.3-flash` are not dated).
- Canada signup and payment: not found. Subscription terms say you give a payment method; payments are non-refundable.

### MiniMax

`MiniMax-M3.1-Flash`: 0.15 in / 0.015 cached read / 0.60 out. `MiniMax-M3`: 0.30 / 0.06 / 1.20 up to 512K input, shown after "Permanent 50% off". Priority tier is 1.5x.
- Context 1,000,000. Tool use with interleaved thinking is documented; the model "thinks on demand", and tool turns must carry the full assistant message including `thinking` / `reasoning_content`. `effort` accepts low to max, default `max`.
- Rate limit: 200 requests per minute, 10,000,000 tokens per minute (rate-limits page), one row for both M3.1-Flash and M3. Free-tier limits: not stated separately.
- Model ID not dated. LangChain: no MiniMax chat page found in the official docs; MiniMax documents OpenAI and Anthropic SDK endpoints. Because of the `reasoning_content` issue, `ChatOpenAI` is a weak fit.
- Privacy policy and terms: both pages are script-rendered and returned no text: not found. Processing location, training, Canada access: not found.

### Mistral

Cheapest: `ministral-3b-2512` at 0.1 in / 0.1 out; `ministral-8b-2512` 0.15 / 0.15; `ministral-14b-2512` 0.2 / 0.2; `mistral-small-2603` (Small 4) 0.15 / 0.6; Large 4 0.7 / 2.1 (pricing page). Batch 50% off per the main pricing page.
- Ministral 3 3B card: context 256k, features `function-calling`, `structured-outputs`, `batching`, Apache 2.0, GA. Aliases `ministral-3b-2512` (dated, pinned) and `ministral-3b-latest` (moving). Performance rating on the model card: 1/5, speed 4/5.
- LangChain: `langchain-mistralai`, `ChatMistralAI`, "beta".
- Training: commercial terms section 4.2: no training on Customer Data or Outputs except opt-in, feedback, order form, or Labs/Preview models. Zero data retention is available on paid plans for chat completions. Processing location, free API tier, rate limits and Canada access: not found (the usage-limits page points to a console page I cannot open; the commercial terms are with Mistral AI of Paris, France).

### xAI (Grok)

Cheapest current: `grok-build-0.1` at 1.00 in / 0.20 cached / 2.00 out, 256k context (prices double above 200k tokens). Everything else is 1.25 and up: `grok-4.3` 1.25 / 0.20 / 2.50; `grok-4.20-0309-*` 1.25 / 0.20 / 2.50; `grok-4.5`, `grok-4.6`, `grok-4.7` at 2.00 / 6.00. There is no small "mini" tier today. The model data lists per-model limits: `grok-build-0.1` 1,800 requests per minute and 10M tokens per minute (raw model data on the models page, the tier these apply to is not stated). Tool calling for `grok-build-0.1`, thinking behaviour, data terms, Canada: not found. LangChain: `langchain-xai`, `ChatXAI`, "beta". Not a price candidate: 9 times Haiku.

### Amazon Nova

See the Nova Micro section above. Other Nova prices from the AWS Price List, US East on-demand: Nova Lite $0.06 in / $0.24 out; Nova 2.0 Lite $0.33 in / $2.75 out on-demand (and $0.30 / $2.50 for the cheaper routing option listed without a feature label; I did not work out which label means what). Canada (Central): Nova Lite $0.064 / $0.256; Nova 2.0 Lite $0.352 / $2.97.

### Meta Llama and open-weight models on hosts

Meta's own API: not looked at. The Llama 3.1 and 3.3 models on Groq are "ContactSales" only (Groq models page). Hosts, cheapest tool-capable open-weight models found:

- DeepInfra (cheapest overall): see ranks 1 to 8 in the table.
- Together serverless: `Qwen/Qwen3.5-9B` 0.17 / 0.25; `nvidia/NVIDIA-Nemotron-3.5-Super-VL` 0.15 / 0.50; `openai/gpt-oss-120b` 0.15 / 0.60; `MiniMaxAI/MiniMax-M3.1-Flash` 0.15 / 0.60; `Qwen/Qwen3.8-Flash` 0.15 / 0.47; `zai-org/GLM-5.3-Flash` 0.15 / 0.50 (same as the originals). All list "Function calling: Yes" except two tiny/experimental models. Together also has "US-only" variants at about 25% more. Rate limits, data terms, Canada: not found. LangChain: `langchain-together`, `ChatTogether`, beta.
- Fireworks: see Nemotron above. Others: `openai/gpt-oss-120b` 0.15 / 0.015 / 0.60. LangChain: `langchain-fireworks`, beta.
- Groq: `openai/gpt-oss-20b` 0.075 / 0.30; `openai/gpt-oss-120b` 0.15 / 0.60; `qwen/qwen3.8-27b` 0.80 / 4.00.
- Cerebras: only two shared models: `gpt-oss-120b` at 0.35 / 0.75 and `qwen-3.8-27b` at 0.99 / 1.49 (model pages). Free trial and pay-as-you-go tiers exist; the free-tier context is 64K to 65K. LangChain: `langchain-cerebras`, `ChatCerebras`, beta. Not cheap.

### OpenRouter

Used as a secondary view. Its model list (473 entries today) shows a few tool-capable models cheaper than the above that I did not check against their owner's page: `inclusionai/ling-3.0-tiny` 0.015 / 0.045 (about $0.0003 per evaluation), `inclusionai/ling-3.0-flash` 0.021 / 0.063. Also `amazon/nova-micro-v1` 0.035 / 0.14 and `qwen/qwen3.7-flash` 0.03 / 0.13, matching the official prices above, which is a useful cross-check. OpenRouter's own fee terms were not read.
- LangChain: `langchain-openrouter`, `ChatOpenRouter`, "beta" (official page).
- Data: "OpenRouter does not store your prompts or responses" unless you opt in. Anonymous sampling for categorisation, and CSAM screening retention. What each upstream provider does with prompts is separate and was not read.
- Canada signup and payment: not found.

### Other providers noticed

- DeepInfra is the cheapest host found, by a wide margin on small models.
- `inclusionai` Ling 3.0 models (OpenRouter listing only), `liquid` LFM models (free on OpenRouter): not checked on owner pages.

## Anthropic, OpenAI, Google re-check (pricing pages only)

- Anthropic: `Claude Haiku 5.5` is the cheapest listed, $0.10 / $0.50 for prompts up to 100K tokens (cache hit $0.01, 5-minute cache write $0.125). Over 100K tokens: $0.50 input. Haiku 4.5 is $1 / $5. Nothing cheaper. Same numbers as the earlier note.
- OpenAI: the pricing page's flagship table lists `gpt-6-astra` $10 / $50, `gpt-6.1-sol` $2 / $10, `gpt-6.1-terra` $1 / $5, `gpt-6-luna` $0.10 / $0.50 (cached $0.01). Flex/Batch halves it: `gpt-6-luna` $0.05 / $0.25 (about $0.0011 per evaluation, $2.53 at 2,300). No smaller model on that page. (OpenRouter's list still shows `gpt-5-nano` at $0.05 / $0.40, with an expiry date of 2026-12-11; it is not on OpenAI's pricing page today.)
- Google: new since the earlier note, the pricing page now lists Gemini 4 Carbon, Argon and Hydrogen (Hydrogen: $1.50 / $7.50, batch $0.75 / $3.75) and Gemini 3.8 Flash and 3.6 Flash. `gemini-3.5-flash-lite` is unchanged at $0.30 / $2.50. One cheaper entry: `gemini-2.5-flash-lite` at $0.10 input (text) / $0.40 output, cached $0.01, about $0.0021 per evaluation. The deprecations page says `gemini-2.5-flash-lite` "is not deprecated and remains available through the API until further notice" with no shutdown date announced, but also says "Access to the 2.5 models is limited to users who have actively used them in the past". So a new account may not be able to call it. Gemma 4 is free tier only. Thinking tokens are billed as output on Gemini.

## LangChain summary

| Provider | Package | Class | Status on the official page |
|---|---|---|---|
| Alibaba Qwen | `langchain-qwq` | `ChatQwen` | beta |
| Amazon Bedrock | `langchain-aws` | `ChatBedrockConverse`, `ChatBedrock` | `ChatBedrock` beta; Converse not confirmed |
| Amazon Nova API (not Bedrock) | `langchain-amazon-nova` | `ChatAmazonNova` | beta |
| Groq | `langchain-groq` | `ChatGroq` | beta |
| Fireworks | `langchain-fireworks` | `ChatFireworks` | beta |
| Together | `langchain-together` | `ChatTogether` | beta |
| Mistral | `langchain-mistralai` | `ChatMistralAI` | beta |
| xAI | `langchain-xai` | `ChatXAI` | beta |
| Cerebras | `langchain-cerebras` | `ChatCerebras` | beta |
| OpenRouter | `langchain-openrouter` | `ChatOpenRouter` | beta |
| Moonshot | community `langchain-moonshot` | `ChatMoonshot` | community, not LangChain-maintained |
| DeepInfra, Z.ai, MiniMax | none found on the official integrations index | `ChatOpenAI` with a `base_url` is the usual route | `ChatOpenAI` drops `reasoning_content`, so it is unsafe for thinking models (Kimi, GLM-5.3, MiniMax) that need it passed back |

Every official provider page ticks tool calling and structured output. "Beta" is the label LangChain puts on every integration page I read, so it does not separate the providers. Whether any of these works in a LangGraph 1.2 tool loop: not found in official docs; I did not run any of them.

## Not found, or from a secondary source

Not found (tried the named pages):
- Kimi: terms, privacy, training, processing location, Canada access, free tier, dated model IDs.
- MiniMax: privacy policy and terms (script-rendered, empty), Canada access, LangChain class.
- Z.ai: rate-limit numbers (script-rendered page), tool calling for `GLM-4-32B-0414-128K` and for the free GLM-4.7-Flash specifically, Canada access, dated IDs.
- Alibaba: whether thinking tokens are billed as output, exact switch-off parameter for thinking, a per-model tool-calling row for `qwen3.7-flash`, Canada access, cached-token rate.
- Mistral: processing location, free API tier, rate-limit numbers, Canada access.
- xAI: tool calling for `grok-build-0.1`, data terms, Canada access.
- Amazon: the sentence on not training with prompts, Canada in-region support for Nova Micro, rate limits, Nova API (`nova.amazon.com`) prices, a current end-of-life date for Nova Micro.
- Groq: whether Groq trains on data; Canada access.
- Fireworks, Together, Cerebras: tool support for the Fireworks Nemotron row, rate limits, data terms, processing location, Canada access.
- DeepInfra: rate limits, processing location, Canada access, whether the serving build behind an ID can change, and what the `deprecated` field in its model list means (set on some models, empty on the ones I ranked).
- OpenRouter: upstream data terms for free models; Canada access.
- Meta: Meta's own Llama API, not looked at.
- Whether the LangChain classes work in a LangGraph 1.2 loop: not run.
- No model was tested for tool-selection quality. Price alone does not show a model can do the job.

Secondary sources (labelled where used):
- DeepInfra model list JSON: first-party but not a pricing page, so price and tool tags are read from the feed that drives their site.
- OpenRouter model list: used only as a cross-check and for the free list and the `ling-3.0` rows.
- Search-engine summary: the claim that the Alibaba terms are governed by Singapore law, and the Kimi `kimi-k3` $3 / $15 first read (later confirmed from the raw Kimi pricing page).
- The summarising fetch tool returned summaries, not raw HTML, for Alibaba (qwen3.8-flash, cross-checked against the raw page), Z.ai (cross-checked), MiniMax (cross-checked), xAI (cross-checked against raw JSON), Mistral and Together (read as markdown).
- Earlier-note rates for DeepSeek were not re-read today.

## Recommendation

- On price alone, the practical floor is about $0.0004 to $0.0008 per evaluation ($0.9 to $1.8 for 2,300 evaluations): Llama 3.1 8B Turbo, `qwen3.7-flash`, gpt-oss-20b and Nova Micro. That is 3 to 6 times cheaper than `claude-haiku-5-5`, saving $3 to $4 on a mid-size run. The absolute saving is small.
- Of these, `qwen3.7-flash` (dated ID `qwen3.7-flash-2026-07-15`) is the one with a dated pinned ID, an official no-training clause in the terms, high rate limits, and a LangChain class. Its catch is default thinking (output cost) and unknown Canada payment. gpt-oss-20b on Groq is the next simplest (OpenAI-compatible, `ChatGroq`, no retention by default, US storage) at about $0.0016.
- The Kimi and GLM-5.3 lines are not cheap and force thinking; the xAI line is not cheap.
- The decision should come from a small pilot on the real loop (how often each model picks the right records), because the dollar differences are a few dollars per run.
