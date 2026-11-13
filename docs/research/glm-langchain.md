# GLM-5.3-Flash through LangChain: which integration, and what comes through it

Issue: #66. Read on 2026-11-13. Official docs and official source repos only; no paid API was called. Where a claim comes from reading source code rather than a doc page, it says so. "Not documented" means the official pages are silent; the last section lists what one live call would settle.

Plain-language terms used below:
- **LangChain chat model**: a Python object with one common interface (`invoke`, `bind_tools`) that hides which company's API is behind it.
- **OpenAI-compatible API**: an API that accepts the same request shape as OpenAI's. Z.ai offers one, so OpenAI's client code can talk to it if you change the address (`base_url`).
- **`usage_metadata`**: LangChain's standard token counts on a reply. **`response_metadata`**: the provider's raw extras, unstandardised.
- **Thinking (reasoning) tokens**: tokens the model spends "thinking" before answering; billed as output.
- **Cached tokens**: the unchanged opening part of a prompt, re-read from a cache at a lower price.

## Short answers

1. **Package and class.** Use `ChatOpenAI` from `langchain-openai` (latest 1.8.0, released 2026-11-13) with `base_url="https://api.z.ai/api/paas/v4/"`. This is the route Z.ai's own LangChain page documents. `ChatZhipuAI` exists in `langchain-community` but is the wrong choice (points at the China site by default, no standard token counts, repo archived). No Z.ai-published LangChain package was found. Confirmed from docs/source.
2. **Tool calling.** Standard `bind_tools` / `AIMessage.tool_calls` works through `ChatOpenAI` (it is plain Chat Completions). Z.ai documents function calling and `tool_choice` of `auto` only. Your earlier direct test showed tools work; the LangChain path itself was not run. Inferred from docs and source.
3. **`reasoning_effort`.** Yes: `ChatOpenAI(reasoning_effort="low")`. It is a plain string sent as-is in the request, so `max` is not blocked. Confirmed from source; Z.ai accepting it is confirmed by Z.ai's docs and your test.
4. **Token details.** Yes, in `usage_metadata`: `output_token_details["reasoning"]` and `input_token_details["cache_read"]`, read from Z.ai's `completion_tokens_details.reasoning_tokens` and `prompt_tokens_details.cached_tokens`. Confirmed from source plus Z.ai's field names. Gap: LangChain drops Z.ai's `reasoning_content` text (the thinking itself), which does not matter for token counting.
5. **Prompt caching.** Yes, automatic ("implicit"), nothing to switch on. Cache hits are billed at a discount; reported in `usage.prompt_tokens_details.cached_tokens`. Confirmed from docs. The docs say "usually 50%"; the price list from the earlier research shows 0.03 vs 0.15 for GLM-5.3-Flash (20%).
6. **`init_chat_model`.** Yes. `init_chat_model("anthropic:claude-haiku-5-5")` and `init_chat_model("openai:glm-5.3-flash", base_url=..., api_key=...)`. The Z.ai side needs the `openai` provider plus `base_url` and an explicit `api_key`. Confirmed from source; there is no built-in `zai` provider.
7. **Error `1302`.** Z.ai documents it as HTTP **429**, "Rate limit reached for requests". Through `ChatOpenAI` it surfaces as `openai.RateLimitError`. The OpenAI client retries 429 by default (2 retries, 0.5 s then 1 s waits, capped at 8 s), so a short burst of over-limit calls can be absorbed, but a sustained excess fails after 2 retries. Confirmed from docs and source; the body of a real `1302` reply was not seen.

## Detail and sources

### 1. Which package

- Z.ai's LangChain guide uses `from langchain_openai import ChatOpenAI` with `openai_api_base="https://api.z.ai/api/paas/v4/"` and the key in `ZAI_API_KEY`. Its examples use `glm-5.3`, and some use older LangChain patterns (`LLMChain`, `langchain.schema`), so copy only the constructor. https://docs.z.ai/guides/develop/langchain/introduction (read 2026-11-13). Chat-completions endpoint: `POST https://api.z.ai/api/paas/v4/chat/completions`, https://docs.z.ai/api-reference/llm/chat-completion (read 2026-11-13).
- `langchain-openai` 1.8.0, requires Python >=3.11 (so 3.12 is fine), uploaded 2026-11-13: https://pypi.org/pypi/langchain-openai/json (read 2026-11-13). Source: https://github.com/langchain-ai/langchain/blob/master/libs/partners/openai/langchain_openai/chat_models/base.py (read 2026-11-13).
- **Caveat, from the source's own header:** "`ChatOpenAI` targets official OpenAI API specifications only. Non-standard response fields added by third-party providers (e.g., `reasoning_content`, `reasoning_details`) are **not** extracted or preserved", and it advises a provider-specific package for providers like OpenRouter, vLLM, DeepSeek. The same is stated on https://docs.langchain.com/oss/python/integrations/chat/openai (read 2026-11-13). No Z.ai-specific package is named. For this project it costs little: you only need the token counts and tool calls, and Z.ai's `clear_thinking` defaults to `true`, meaning old-turn reasoning is not required back in later turns (https://docs.z.ai/api-reference/llm/chat-completion). If you ever set `clear_thinking=false`, Z.ai says the old reasoning must be sent back "full, unmodified, and correctly ordered", and `ChatOpenAI` cannot do that.
- `ChatZhipuAI` (source: https://github.com/langchain-ai/langchain-community/blob/main/libs/community/langchain_community/chat_models/zhipuai.py, read 2026-11-13): `langchain-community` 0.4.2 (https://pypi.org/pypi/langchain-community/json), but the repo "was archived by the owner on Jun 19, 2026" (https://github.com/langchain-ai/langchain-community, read 2026-11-13). The default URL is `https://open.bigmodel.cn/api/paas/v4/chat/completions` (China site, not api.z.ai); it makes its own HTTP calls (so no built-in `max_retries`), defaults to `glm-4`, and the file has no `usage_metadata` or `reasoning_effort` handling (searched). No LangChain docs page for it exists (404 at /integrations/chat/zhipuai).
- `langchain-zhipuai` 0.0.1 on PyPI is by an individual author, not Zhipu or Z.ai, so excluded. https://pypi.org/pypi/langchain-zhipuai/json.
- `zai-sdk` (0.2.3, https://pypi.org/pypi/zai-sdk/json) is Z.ai's own Python client, not a LangChain integration. No `langchain-zai` package exists on PyPI (404).
- The LangChain providers list showed no Z.ai/Zhipu entry (only gateways such as OptiQ and HopBase that resell GLM): https://docs.langchain.com/oss/python/integrations/providers/all_providers (first 100,000 of 113,097 characters read; the unread tail is where "Z" entries would sit, so treat this as "not seen", not "absent").

Recommendation: `ChatOpenAI` with a custom base URL. It is the standard class, it is what Z.ai documents, and it is actively maintained. A subclass to keep `reasoning_content` is not needed.

### 2. Tool calling

- `ChatOpenAI.bind_tools` and `AIMessage.tool_calls` are standard LangChain; the class sends ordinary Chat Completions requests unless it switches to OpenAI's Responses API (it does so only for built-in OpenAI tools or Responses-only arguments such as `reasoning`; see `_use_responses_api` in the source file above). Do not pass `reasoning=`, `include=` or `use_responses_api`, or it will switch to an endpoint Z.ai does not document (inferred).
- Z.ai side: `tools` up to 128 function items; **`tool_choice` supports only `auto`**; response `tool_calls` carry `id`, `type`, `function.name`, `function.arguments`; `finish_reason` can be `tool_calls`. The reference page describes response `arguments` as an object but request-side as a JSON string, an inconsistency in their doc. https://docs.z.ai/api-reference/llm/chat-completion (read 2026-11-13). So avoid `bind_tools(..., tool_choice="required")` or a named tool: not supported by Z.ai (inferred that LangChain passes it through and Z.ai rejects it).
- `tool_stream` (streamed tool arguments) is off by default; the reference lists "GLM-5.3, 5.2, 5.1, 5, 4.7, 4.6 series" as supporting it; whether Flash is included is not stated. Not needed with `invoke`.

### 3. `reasoning_effort`

- Source: `reasoning_effort: str | None = None` is a field on `ChatOpenAI`, documented "For use with the Chat Completions API" and listing OpenAI's values, but typed as a free string and sent unchanged in the request body (`_default_params`). Only the Responses-API path rewrites it to `reasoning.effort`. So `ChatOpenAI(reasoning_effort="max")` sends `"reasoning_effort": "max"` at the top level. The LangChain docs say it "requires `langchain-openai>=1.4.1`", fine at 1.8.0.
- Z.ai side: default `max`; "takes effect when `thinking` is enabled"; for GLM-5.3 and GLM-5.3-Flash only `low`, `high`, `max` are supported; `thinking` can only be `enabled` for them. https://docs.z.ai/api-reference/llm/chat-completion and https://docs.z.ai/guides/capabilities/thinking-mode (both read 2026-11-13).
- Fallback if the constructor argument ever misbehaves: `extra_body={"reasoning_effort": "low"}` (the source documents `extra_body` as the place for provider-specific fields); Z.ai's own thinking guide sends its extra fields via `extra_body` with the OpenAI SDK. Not needed per the source reading; a live call confirms it.

### 4. Usage numbers

- Source function `_create_usage_metadata` maps `prompt_tokens_details.cached_tokens` to `usage_metadata["input_token_details"]["cache_read"]` and `completion_tokens_details.reasoning_tokens` to `usage_metadata["output_token_details"]["reasoning"]`. `output_tokens` is the provider's `completion_tokens`, which for Z.ai presumably already includes thinking tokens (inferred, not documented; it is the OpenAI convention). A key is omitted when the provider does not send it.
- Z.ai's reference page documents `usage.prompt_tokens_details.cached_tokens` ("Number of tokens served from cache") but says `completion_tokens_details` is "not defined in this documentation". `reasoning_tokens` is therefore known only from your own test call, not from the docs.
- Streaming: `stream_usage` defaults off for non-OpenAI base URLs and "many non-OpenAI endpoints don't support streaming token usage" (https://docs.langchain.com/oss/python/integrations/chat/openai). Whether Z.ai sends usage in a stream: not documented. Use non-streaming `invoke` for the benchmark.

### 5. Prompt caching

- Automatic: "Implicit caching that intelligently identifies repeated context content without manual configuration"; triggered by repeated content such as the same system prompt or history; works with "all mainstream models, including GLM-5, GLM-4.7, GLM-4.6 series"; no flag. Cache lifetime: not documented. GLM-5.3-Flash is not named explicitly on the page; the examples use `glm-5.3`. https://docs.z.ai/guides/capabilities/cache (read 2026-11-13).
- Pricing: cache hits "usually 50% of standard price" per that page. The price list read 2026-11-12 by the earlier research shows GLM-5.3-Flash at $0.15 input, $0.03 cached input, $0.50 output per million tokens (cached = 20% of input), with cached-input storage "Limited-time Free". The two Z.ai pages disagree on the ratio; use the price list for cost maths. Source: `origin/research/glm-flash`, `docs/research/glm-flash.md` (citing https://docs.z.ai/guides/overview/pricing.md).
- Reporting: `usage.prompt_tokens_details.cached_tokens` (see item 4). Whether `prompt_tokens` includes the cached portion: the example shows `prompt_tokens: 1200` with `cached_tokens: 800`, implying included (inferred).

### 6. `init_chat_model`

- Source of `init_chat_model` (langchain 1.5.0): https://github.com/langchain-ai/langchain/blob/master/libs/langchain_v1/langchain/chat_models/base.py (read 2026-11-13). `"provider:model"` strings are parsed, or `model_provider=` is passed separately. The built-in provider table includes `anthropic` (ChatAnthropic) and `openai` (ChatOpenAI), with no `zai`/`zhipu` entry. Extra keyword arguments go to the class constructor; the docstring lists `base_url`, `max_retries`, `timeout` as common ones.
- So:
  - Anthropic: `init_chat_model("anthropic:claude-haiku-5-5")`
  - Z.ai: `init_chat_model("openai:glm-5.3-flash", base_url="https://api.z.ai/api/paas/v4/", api_key=<Z.ai key>, reasoning_effort="low")`
  - Because the Z.ai side needs different extra arguments, the one config setting should hold a provider/model string plus a per-provider settings block (base URL, which env variable holds the key, `reasoning_effort`); the code passes that block as keyword arguments. `reasoning_effort` is not a valid ChatAnthropic argument, so the extras must be per provider (inferred design note).
  - Always pass `api_key` explicitly; otherwise `ChatOpenAI` reads `OPENAI_API_KEY`, and `OPENAI_BASE_URL` can silently override the address (docs.langchain.com chat/openai page).
  - The model name is lower-case `glm-5.3-flash`, as in your test; Z.ai's docs write `GLM-5.3-Flash`.

### 7. Error `1302`

- Z.ai: code `1302`, **HTTP 429**, message "Rate limit reached for requests"; no retry interval or backoff guidance. `1305` (429, "service may be temporarily overloaded, please try again later") is the platform-wide overload case. https://docs.z.ai/api-reference/api-code (read 2026-11-13). The docs list no concurrency-specific code; that 1302 means "too many at once" comes from your test and the earlier bigmodel.cn reading.
- Client: `ChatOpenAI` uses the `openai` Python SDK (3.50.0 on PyPI). A 429 raises `openai.RateLimitError` (subclass of `APIStatusError`, `status_code` 429) once retries are used up. Source: https://github.com/openai/openai-python/blob/main/src/openai/_exceptions.py, `_base_client.py`, `_constants.py` (read 2026-11-13).
- Retry: the SDK retries 408, 409, 429 and >=500 (`_should_retry`). `DEFAULT_MAX_RETRIES = 2`, backoff 0.5 s doubling up to 8 s. `ChatOpenAI(max_retries=None)` falls back to that default; set `max_retries` to change it. It honours a `Retry-After` header if sent (your test saw no rate-limit headers, so the fixed backoff applies) and an `x-should-retry` header. Roughly 1.5 s of total waiting may not outlast a 4-slot limit held by long thinking calls, so the practical fix is to keep the loop to 4 or fewer calls in flight (for example a semaphore) rather than rely on retries (inferred).
- Whether Z.ai's real 1302 reply also carries `x-should-retry` or `Retry-After`: not documented.

## What one live call would settle

A single non-streaming `invoke` with one tool bound and `reasoning_effort="low"`, on `ChatOpenAI` pointed at Z.ai; print `response.usage_metadata`, `response.tool_calls` and `response.response_metadata`:
- that `reasoning_effort` as a constructor argument is accepted (item 3);
- that `output_token_details.reasoning` is present and whether `output_tokens` includes it (item 4);
- that tool calls parse into `tool_calls` (item 2);
- a repeat call with the same long prefix, to see `input_token_details.cache_read` (item 5);
- the exception, `status_code`, body and headers of a deliberate burst of 5 parallel calls (item 7);
- streaming usage, only if streaming is wanted.
