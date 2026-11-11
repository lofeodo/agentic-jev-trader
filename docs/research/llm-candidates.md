# LLM candidates: price, training cutoff, tool-calling fit (issue #14)

Read on 2026-11-11 from live official pages. Prices are USD per 1M tokens, standard (synchronous) tier, text only. No convention for research notes existed in the repo, so this lives in `docs/research/`.

## Sources

- Anthropic models overview: https://platform.claude.com/docs/en/models/overview
- Anthropic pricing: https://platform.claude.com/docs/en/about-claude/pricing
- Anthropic `claude-api` skill (model IDs, API behaviours, cached 2026-11-03)
- OpenAI models: https://developers.openai.com/api/docs/models (per-model pages: `/models/gpt-6-astra`, `gpt-6.1-sol`, `gpt-6.1-terra`, `gpt-6-luna`)
- OpenAI pricing: https://developers.openai.com/api/docs/pricing
- Google pricing: https://aistudio.google.com/docs/pricing (redirect from ai.google.dev/gemini-api/docs/pricing)
- Google model pages: https://aistudio.google.com/docs/models/gemini-4-carbon (also `gemini-4-argon`, `gemini-3.8-flash`, `gemini-3.5-flash-lite`)
- Google cutoffs (DeepMind model cards): https://deepmind.google/models/model-cards/gemini-4-carbon/ , `/gemini-4-argon/`, `/gemini-3-8-flash/`, `/gemini-3-5-flash-lite/`
- LangChain: https://docs.langchain.com/oss/python/integrations/chat/anthropic , `/chat/openai` , `/providers/google`

## Comparison table

Cached = cached/cache-read input price. Batch = discount vs standard on both input and output (Anthropic and OpenAI: 50%; Google: 50%, per the Batch table). Context is total window; structured output and tool calling are both listed as supported on every row unless noted. "Months after cutoff" is measured to 2026-11-11.

| Provider / tier | Model ID | Input | Output | Cached input | Batch | Training cutoff (months after) | Context | LangChain package |
|---|---|---|---|---|---|---|---|---|
| Anthropic flagship | `claude-fable-5-2` | 8.00 | 40.00 | 0.20 (cache write 10.00 / 5 min) | -50% | Jun 2026 (about 4.5-5) | 1M | `langchain-anthropic` |
| Anthropic flagship (default) | `claude-opus-5-5` | 4.00 | 20.00 | 0.20 (write 5.00) | -50% | Jun 2026 (about 4.5-5) | 1M | `langchain-anthropic` |
| Anthropic mid | `claude-sonnet-5-5` | 2.00 | 10.00 | 0.10 (write 2.50) | -50% | Jun 2026 (about 4.5-5) | 1M | `langchain-anthropic` |
| Anthropic small | `claude-haiku-5-5` | 0.10 (0.50 over 100K prompt) | 0.50 (2.50 over 100K) | 0.01 (write 0.125) | -50% | Jun 2026 (about 4.5-5) | 1M | `langchain-anthropic` |
| OpenAI flagship | `gpt-6-astra` | 10.00 | 50.00 | 1.00 | -50% | Apr 30 2026 (about 6.4) | 1.05M | `langchain-openai` |
| OpenAI flagship (lower cost) | `gpt-6.1-sol` | 2.00 | 10.00 | 0.10 (write 2.50) | -50% | Apr 30 2026 (about 6.4) | 1.05M | `langchain-openai` |
| OpenAI mid | `gpt-6.1-terra` | 1.00 | 5.00 | 0.05 | -50% | Jun 1 2026 (about 5.3) | 1.05M | `langchain-openai` |
| OpenAI small | `gpt-6-luna` | 0.10 | 0.50 | 0.01 | -50% | May 18 2026 (about 5.8) | 1.05M | `langchain-openai` |
| Google flagship | `gemini-4-carbon` | 2.00 (4.00 from Dec 1 2026) | 10.00 (20.00) | 0.10 implicit only (0.20) | -50% | Mar 2026 (about 7.4) | 1M | `langchain-google-genai` |
| Google flagship (efficient) | `gemini-4-argon` | 2.00 (4.00 from Dec 1 2026) | 10.00 (20.00) | 0.10 implicit only (0.20) | -50% | Mar 2026 (about 7.4) | 1M | `langchain-google-genai` |
| Google mid | `gemini-3.8-flash` | 0.75 (1.50 from Jan 1 2027) | 3.75 (7.50) | 0.075 plus 0.50/M tokens/hr storage | -50% | Mar 2026 (about 7.4) | 1M | `langchain-google-genai` |
| Google small | `gemini-3.5-flash-lite` | 0.30 | 2.50 | 0.03 plus 1.00/M tokens/hr storage | -50% | Mar 2026 (about 7.4) | 1M | `langchain-google-genai` |

Notes on specific cells:

- Anthropic cutoff is given only as "Jun 2026" for both "reliable knowledge" and "training data" (models overview). The day is not stated, so the months-after range spans Jun 1 to Jun 30.
- Anthropic cache-read prices: the overview says 5% of base on Opus 5.5 and Sonnet 5.5, 10% on Haiku 5.5, 2.5% on Fable 5.2. Pricing table gives the dollar figures above.
- Anthropic Haiku 5.5 has the 100K-prompt tier; the other Anthropic models are flat across the full 1M window (pricing page).
- OpenAI long context (>272K input) costs about double; irrelevant at 6K-20K tokens.
- Google cutoffs: model cards state "March 2026" for Gemini 4 (Argon and Carbon), 3.8 Flash and 3.5 Flash-Lite, with some domains possibly limited to January 2025 on the Gemini 3 family cards.
- Google Gemini 4 and 3.8 Flash prices on the pricing page rise on Dec 1 2026 and Jan 1 2027 (doubling). Those dates fall inside a likely build window, so budget for the higher figure.
- Gemini 4 models: explicit context caching is not supported, only implicit caching (model pages). Flash tiers support explicit caching with an hourly storage fee.
- Google also lists `gemini-3.1-pro-preview` ($2 / $12) and `gemini-3.1-flash-lite`, `gemini-3-flash-preview`; preview models were left out as unsuitable for a reproducible evaluation.
- The OpenAI pricing page also lists older and duplicate rows (`gpt-6-sol`, `gpt-5.6-*`, `gpt-5.5`, `gpt-5.4*`); the models page treats only Astra, Sol 6.1, Terra 6.1 and Luna 6 as current, so the table uses those.

## Tool calling and structured output fit

- Anthropic: tool calling and structured outputs supported (models overview says all current models support tool use; structured outputs via `output_config.format` per the `claude-api` skill). Gotchas from the skill: on Claude Opus 5.5, Sonnet 5.5 and Fable 5.2, forced `tool_choice` (`any` or a named tool) returns a 400, and thinking cannot be disabled on Opus 5.5 and Fable 5.2 (Sonnet 5.5 uses `between_tools`). LangChain's `with_structured_output(..., method="json_schema")` or `ProviderStrategy` is the path that avoids forced tool choice (LangChain Anthropic page; I did not run it, so the interaction is unverified). Temperature, top_p and top_k are rejected on these models.
- OpenAI: all four models list function calling and structured outputs. Terra requires the Responses API for tool calling; Luna on Chat Completions only works with tools when `reasoning.effort` is `none`, otherwise Responses API. In `langchain-openai` set `use_responses_api=True` (needs 0.3.9 or later).
- Google: function calling, structured outputs and thinking (low/medium/high) listed on all four model pages checked. Known quirk from the page: `minimal` thinking level errors on 3.8 Flash.
- LangChain packages: `langchain-anthropic`, `langchain-openai`, `langchain-google-genai` (package names read from the LangChain docs; Google page does not itself show tool-calling support, I took that from the Google model pages).

## Cost per evaluation

Two readings of the ticket's "about 6,000 input and 800 output tokens plus two tool calls":

- A: the ticket's totals taken literally, one call of 6,000 in and 800 out.
- B: a three-call loop (two tool round trips), where each call resends the context. Assumed sizes: calls of 6,000 / 6,650 / 7,300 input and 150 / 150 / 800 output, so 19,950 in and 1,100 out. These sizes are my assumption, not from a source.

Standard rates, no caching, no batch, no thinking overhead.

| Model | A per eval | A x1,000 | A x10,000 | B per eval | B x1,000 | B x10,000 |
|---|---|---|---|---|---|---|
| `claude-fable-5-2` | $0.0800 | $80 | $800 | $0.2036 | $204 | $2,036 |
| `claude-opus-5-5` | $0.0400 | $40 | $400 | $0.1018 | $102 | $1,018 |
| `claude-sonnet-5-5` | $0.0200 | $20 | $200 | $0.0509 | $51 | $509 |
| `claude-haiku-5-5` | $0.0010 | $1 | $10 | $0.0025 | $3 | $25 |
| `gpt-6-astra` | $0.1000 | $100 | $1,000 | $0.2545 | $254 | $2,545 |
| `gpt-6.1-sol` | $0.0200 | $20 | $200 | $0.0509 | $51 | $509 |
| `gpt-6.1-terra` | $0.0100 | $10 | $100 | $0.0255 | $25 | $254 |
| `gpt-6-luna` | $0.0010 | $1 | $10 | $0.0025 | $3 | $25 |
| `gemini-4-carbon` / `gemini-4-argon` | $0.0200 | $20 | $200 | $0.0509 | $51 | $509 |
| `gemini-3.8-flash` | $0.0075 | $8 | $75 | $0.0191 | $19 | $191 |
| `gemini-3.5-flash-lite` | $0.0038 | $4 | $38 | $0.0087 | $9 | $87 |

Adjustments not in the table:

- Batch halves every figure, but a step-by-step agent loop that depends on earlier results cannot be batched within a run; it only suits offline replays.
- Caching: in B, about 14K of the 20K input tokens are repeats within one evaluation, so caching can cut input cost sharply. Cache reads are 1-10% of base input, but Anthropic cache writes cost 1.25x (5 minute) base input, and the 6K prefix must clear each provider's minimum cacheable size (Anthropic's is model dependent, 512 to 4,096 tokens per the skill).
- Reasoning tokens are billed as output. Opus 5.5 and Fable 5.2 always think, and the GPT-6 and Gemini 4 models offer reasoning effort. Real output may be several times 800 tokens, so output-heavy rows (all of them, since output is 5x input price) are the most likely to be understated. Measure on a pilot run before committing.
- Gemini 4 prices double on Dec 1 2026 (A becomes $0.04, B about $0.10 per eval on both Gemini 4 models).

## Unverified or conflicting

- Google model pages and pricing page do not give API-level model IDs on the model cards; IDs come from the models and pricing pages.
- Carbon availability is inconsistent: the DeepMind card lists the Gemini API and paid AI Studio tiers, while a third-party search summary said select cyber defenders only. I did not confirm API access for a normal key.
- Anthropic cutoff day not published on the pages read; Anthropic's Transparency Hub was not read.
- Whether the Anthropic forced-tool-choice 400 breaks `ChatAnthropic.with_structured_output` default behaviour was not tested.
- I read Anthropic/Google data via a fetch tool that summarises pages, so figures were extracted, not copied from raw HTML; the Anthropic figures were cross-checked against the `claude-api` skill and agree.
- OpenAI structured-output support is stated per model page for the four chosen models only.
