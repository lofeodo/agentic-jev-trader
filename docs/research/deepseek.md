# DeepSeek: price, training cutoff, tool-calling fit (issue #39)

Read on 2026-11-12 from official DeepSeek pages and the official LangChain docs. Prices are USD per 1M tokens, text only. Where the official pages are silent, this note says "not found". Nothing here comes from memory or third-party blogs. Format follows `docs/research/llm-candidates.md` on the `research/llm-candidates` branch (issue #14).

## Sources (all read 2026-11-12)

- Models and pricing: https://api-docs.deepseek.com/quick_start/pricing
- Rate limit: https://api-docs.deepseek.com/quick_start/rate_limit
- Tool calls (strict mode, beta): https://api-docs.deepseek.com/guides/tool_calls
- JSON output: https://api-docs.deepseek.com/guides/json_mode
- Thinking mode: https://api-docs.deepseek.com/guides/thinking_mode
- Context caching: https://api-docs.deepseek.com/guides/kv_cache
- Chat completion API reference: https://api-docs.deepseek.com/api/create-chat-completion
- Error codes: https://api-docs.deepseek.com/quick_start/error_codes
- Change log: https://api-docs.deepseek.com/updates
- Release note 2026-10-17: https://api-docs.deepseek.com/news/news261017
- Model card (official `deepseek-ai` org): https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017
- Terms of service: https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html
- Privacy policy: https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html
- LangChain DeepSeek chat page: https://docs.langchain.com/oss/python/integrations/chat/deepseek
- LangChain DeepSeek provider page: https://docs.langchain.com/oss/python/integrations/providers/deepseek

## Current models

The pricing page lists two current model IDs. Both have a 1M-token context and up to 384K output.

| Model ID | Version served | Input, cache miss (peak / off-peak) | Input, cache hit (peak / off-peak) | Output (peak / off-peak) | Context | Tools | JSON output | Vision | Concurrency |
|---|---|---|---|---|---|---|---|---|---|
| `deepseek-flash` | DeepSeek-V4.1-Flash-1017 | 0.30 / 0.15 | 0.006 / 0.003 | 1.20 / 0.60 | 1M | Yes | Yes (`json_object`) | Yes | 2,500 |
| `deepseek-v4-pro` | DeepSeek-V4-Pro-0813 | 1.32 / 0.66 | 0.044 / 0.022 | 3.96 / 1.98 | 1M | Yes | Yes (`json_object`) | No | 500 |

Notes:

- Off-peak is half of peak. Peak is 01:00-04:00 and 06:00-10:00 UTC, Monday to Friday, except Chinese public holidays. Every other hour is off-peak, including all of every weekend. In eastern Canada (UTC-5 in winter, UTC-4 in summer) the winter peak hours are 8pm-11pm (Sun-Thu) and 1am-5am (Mon-Fri). Peak/off-peak pricing started 2026-08-16 (change log).
- The legacy names `deepseek-v4-flash` and `deepseek-v4-flash-vision-exp` still work and are billed at Flash price. The pricing page says to use `deepseek-flash`. The change log says `deepseek-chat` and `deepseek-reasoner` were to be discontinued on 2026-07-24. Whether that has happened: not found.
- Prices "may vary" and DeepSeek reserves the right to change them (pricing page). The change log shows a price cut on 2026-09-10.
- The page says `deepseek-flash` points at the newest Flash version (upgraded 2026-10-17 with "pricing and calling method unchanged"). The ID is an alias that moves. For a reproducible evaluation, that matters: the model behind the name can change. Whether DeepSeek offers a pinned, dated ID for the API: not found. (The weights are open and MIT-licensed on Hugging Face, per the model card.)
- Cached input: caching is on by default, based on shared prefixes, best effort, and caches are cleared after hours to days (KV cache page). The minimum cacheable size: not found. The usage field reports `prompt_cache_hit_tokens` and `prompt_cache_miss_tokens`.
- Batch API or batch discount: not found on the pages read.

## Training cutoff

- Not found. The pricing page, the 2026-10-17 release note, the change log and the Hugging Face model card do not state a training data or knowledge cutoff for `deepseek-flash` or `deepseek-v4-pro`.
- The model card shows only a 2026 citation year, which is a publication year and not a cutoff.
- What is known: V4-Pro reached general availability 2026-08-13, V4.1-Flash launched 2026-09-10 and was upgraded 2026-10-17. The cutoff must be earlier than those dates, but the real value would have to be measured (for example by asking the model about dated events), not assumed.
- Why it matters here: if the simulation replays market data from before the cutoff, the model may "remember" what happened next. The cutoff is unknown, so DeepSeek cannot be ruled in or out on this point from official sources.

## Tool calling and structured output fit

- Tool calling: both models list "Tool Calls: Yes" (pricing page). Only `type: "function"` tools are supported. Tool names must be unique. A maximum number of tools: not found.
- Strict mode (beta): set `base_url="https://api.deepseek.com/beta"` and `"strict": true` on every function. Output then follows the JSON Schema. Works in thinking and non-thinking modes. Schema limits: every property must be in `required`, `additionalProperties` must be `false`, no `minLength`/`maxLength`, no `minItems`/`maxItems`. This is a beta feature, so it is a risk for a reproducible harness.
- Thinking mode is on by default (effort `high`). Tool use in thinking mode is supported. Rule that matters for a loop: when `tools` are present, `reasoning_content` from the model must be passed back in every later request, or the API returns 400. A LangGraph loop must preserve it. Whether `langchain-deepseek` does this automatically: not found on the LangChain pages.
- `tool_choice`: `none`, `auto`, `required`, or a named function. `required` and named choices return 400 in thinking mode, so thinking must be disabled to force a tool.
- Thinking mode ignores `temperature` (no error, no effect). Thinking can be disabled with `{"thinking": {"type": "disabled"}}`.
- The Chat Completions API does not support inserting tool calls and results into history mid-conversation. The Anthropic-format and Responses APIs do.
- Structured output: only `response_format: {"type": "json_object"}` is documented. The prompt must contain the word "json" and an example. If the output is not valid JSON, the API may return blank content with `finish_reason: "stop"`, so code must retry. `json_schema` response format: not found (the API reference lists only `text` and `json_object`). Strict tool calls are the only schema-enforced path found.
- Reasoning tokens: whether thinking tokens are billed as output tokens: not found on the pages read. The default `max_tokens` is 64K in thinking mode (8K otherwise).

## LangChain and LangGraph

- Package: `langchain-deepseek` (`pip install -qU langchain-deepseek`), class `ChatDeepSeek`, env var `DEEPSEEK_API_KEY`. The class is marked "beta" on the LangChain page.
- The LangChain chat page shows tool calling and structured output as supported, but its examples and caveats are written for the old names: it says tool calling works "only with `deepseek-chat`" and that `deepseek-reasoner` "does not support tool calling or structured output". Those names are legacy per DeepSeek. The page does not mention `deepseek-flash` or `deepseek-v4-pro`. So the LangChain docs are out of date, and support for the current IDs is not confirmed by LangChain.
- The LangChain pages do not mention LangGraph, MCP or `langchain[mcp]` for DeepSeek. Whether it works in a LangGraph 1.2 tool loop: not found in official docs. Any `BaseChatModel` with `bind_tools` generally fits LangGraph, but that is not stated for DeepSeek, and I did not run it.
- Alternative the docs allow: DeepSeek exposes an OpenAI-format endpoint (`https://api.deepseek.com`) and an Anthropic-format endpoint (`https://api.deepseek.com/anthropic`). Using `langchain-openai` against the OpenAI-format base URL was not documented by LangChain, so it is untested.

## Rate limits

- DeepSeek limits concurrent requests, not requests per minute: 2,500 for `deepseek-flash`, 500 for `deepseek-v4-pro`, per account. Above the limit you get HTTP 429. Higher limits can be requested through a form at no extra cost (rate limit page).
- Tokens per minute or per day limits: not found. A serial simulation will not come near 500 concurrent requests.

## Access from Canada, payment, data

- Whether the API can be used from Canada: not found. No official page read lists supported or blocked countries. The terms (section 1.4) say DeepSeek makes "no warranty" the Services are available in certain jurisdictions.
- Payment methods and whether a Canadian card or CAD works: not found. The terms say recharge methods follow "the information displayed on our product pages and the platform website" and that prepaying may be needed. Error 402 means "Insufficient Balance", fixed by topping up. The platform site itself (platform.deepseek.com) returned 403 to my fetch, and the FAQ page returned no content.
- Where requests are processed: the privacy policy says DeepSeek will "directly collect, process and store your Personal Data in People's Republic of China", and data may also be stored on a server outside your country. The terms do not state a processing location.
- Keeping and training: the privacy policy says data is used to "train and improve our technology, such as our machine learning models", and users can opt out of using personal data for training. Account data, including input data, is kept "for as long as you have an account". The policy does not say whether API inputs are covered or give API-specific retention. The terms (4.2) let the customer use outputs for training other models, and assign output rights to the customer.
- Governing law: the laws of mainland China, with disputes in the Hangzhou court (terms 10.1-10.2).
- Why it matters: the prompts here contain only public historical market records, not personal data, so the data risk is low. It is still a point to weigh.

## Cost per evaluation

Workload per full evaluation: 4 calls, 17,000 input tokens and 1,000 output tokens in total. 3-month run: 800 / 2,300 (middle) / 4,600 evaluations. Standard rates, no batch, no thinking overhead, no caching unless stated. Per evaluation: input tokens x input price + output tokens x output price.

| Model | Per eval | 800 evals | 2,300 evals (middle) | 4,600 evals |
|---|---|---|---|---|
| `deepseek-flash`, peak | $0.0063 | $5.04 | $14.49 | $28.98 |
| `deepseek-flash`, off-peak | $0.0032 | $2.52 | $7.25 | $14.49 |
| `deepseek-v4-pro`, peak | $0.0264 | $21.12 | $60.72 | $121.44 |
| `deepseek-v4-pro`, off-peak | $0.0132 | $10.56 | $30.36 | $60.72 |
| `claude-haiku-5-5` (under 100K prompt) | $0.0022 | $1.76 | $5.06 | $10.12 |
| `gpt-6-luna` | $0.0022 | $1.76 | $5.06 | $10.12 |
| `gemini-3.5-flash-lite` | $0.0076 | $6.08 | $17.48 | $34.96 |

Rates used for the comparison rows are from `docs/research/llm-candidates.md` (read 2026-11-11): Haiku 5.5 and Luna 0.10 in / 0.50 out, Flash-Lite 0.30 / 2.50. I did not re-read those pages.

With caching (an assumption, not a measured rate): if 70% of input tokens (11,900 of 17,000) are cache hits, `deepseek-flash` costs about $0.0028 per eval at peak (about $6.44 for 2,300 evals) and about $0.0014 off-peak (about $3.22 for 2,300 evals). The 70% figure is my guess from the repeated context in a loop. Real hit rates are "best effort" per DeepSeek.

Other cost notes:

- Thinking is on by default. If thinking tokens are billed as output (not confirmed), output could be several times 1,000 tokens, and output is 4x the input price. Disable thinking, or measure on a pilot run.
- `deepseek-flash` at peak costs the same as Flash-Lite on input (0.30) and about half on output (1.20 vs 2.50), but about 3x the price of Haiku 5.5 and Luna on the 17,000/1,000 workload at peak. Off-peak, `deepseek-flash` is still above Haiku 5.5 and Luna (about $0.0032 vs $0.0022).
- All the small models cost a few dollars to tens of dollars per run. Price is unlikely to decide the choice.

## Recommendation

- Model ID to consider: `deepseek-flash` (the small, low-cost model). `deepseek-v4-pro` costs about 4x more and has no vision, and nothing read says it is better at tool calling.
- Run it with thinking disabled, or low effort, and strict tool calls only if the beta is acceptable.

## Unverified or not found

- Training cutoff for both models (not stated anywhere read).
- Whether the API is usable from Canada, and which payment methods work from Canada (no official page read says).
- Whether `langchain-deepseek` supports `deepseek-flash` and `deepseek-v4-pro`, handles `reasoning_content` pass-back, and works in a LangGraph 1.2 loop with `langchain[mcp]`. The LangChain page still documents `deepseek-chat` and `deepseek-reasoner`. I did not run it.
- Whether `deepseek-chat` and `deepseek-reasoner` are still accepted after 2026-07-24.
- Pinned (dated) API model IDs for reproducibility.
- Whether reasoning tokens are billed as output.
- Minimum cache size, and typical cache hit rate.
- `json_schema` response format (not documented), maximum number of tools, tokens-per-minute limits, batch pricing.
- Official data retention and training terms specific to API inputs. The privacy policy states general rules only.
- The platform site (403) and FAQ (empty) could not be read.
- Pages were read through a fetch tool that summarises pages, so figures were extracted, not copied from raw HTML. Prices came from a single read of the pricing page.
- The Haiku/Luna/Flash-Lite comparison rates were not re-checked today.
