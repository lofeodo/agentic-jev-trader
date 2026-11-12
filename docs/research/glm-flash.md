# GLM Flash: free tier limits, tool calling, and cost per run

Issue: #42. Read on 2026-11-12. Primary sources only (Z.ai and bigmodel.cn docs). Anything marked "inferred" is my reading, not a quote.

## Sources (all read 2026-11-12)

- Pricing: https://docs.z.ai/guides/overview/pricing.md (the `.md` form shows the collapsed "Other Pricing" section)
- Docs index: https://docs.z.ai/llms.txt
- GLM-4.7 family page: https://docs.z.ai/guides/llm/glm-4.7.md
- Function calling: https://docs.z.ai/guides/capabilities/function-calling.md
- Structured output: https://docs.z.ai/guides/capabilities/struct-output.md
- Thinking mode: https://docs.z.ai/guides/capabilities/thinking-mode.md
- Chat completion API reference: https://docs.z.ai/api-reference/llm/chat-completion.md
- Rate limits (Z.ai): https://docs.z.ai/api-reference/rate-limit.md, which redirects to https://z.ai/manage-apikey/rate-limits, which requires login (not read)
- Rate limits (bigmodel.cn, Chinese docs): https://docs.bigmodel.cn/cn/api/rate-limit.md
- bigmodel.cn model overview: https://docs.bigmodel.cn/cn/guide/start/model-overview.md
- Z.ai FAQ: https://docs.z.ai/help/faq.md
- LangChain integration (Z.ai's own page): https://docs.z.ai/guides/develop/langchain/introduction.md
- Migration guide: https://docs.z.ai/guides/overview/migrate-to-glm-new.md
- Privacy policy (incl. DPA): https://docs.z.ai/legal-agreement/privacy-policy.md
- Terms of use (incl. API additional terms): https://docs.z.ai/legal-agreement/terms-of-use.md
- Official LangChain docs: guessed pages for a Zhipu/Z.ai integration returned 404 (https://docs.langchain.com/oss/python/integrations/chat/zhipuai and .../providers/zhipu).

Note: several pages were read through a summarising fetch tool, not raw text. The pricing and rate-limit (bigmodel.cn) pages were read as raw text in a browser.

## Answers to the seven items

### 1. Price list (USD per million tokens)

Confirmed today; the earlier numbers are correct.

| Model | Input | Cached input | Output | Notes |
|---|---|---|---|---|
| `GLM-4.7-Flash` | Free | Free | Free | text, 200K context, 128K max output |
| `GLM-4.5-Flash` | Free | Free | Free | text, 128K context, 96K max output (bigmodel.cn) |
| `GLM-4.7-FlashX` | 0.07 | 0.01 | 0.40 | listed under "Other Pricing" |
| `GLM-5.3-Flash` | 0.15 | 0.03 | 0.50 | thinking forced on |
| `GLM-5.3-FlashX` | 0.37 | 0.075 | 1.25 | thinking forced on |
| `GLM-5.3-FlashX-Legal` | 0.37 | 0.075 | 1.25 | new since the earlier research; not studied |
| `GLM-4.6V-Flash` (vision) | Free | Free | Free | vision, not relevant |
| `GLM-4.6V-FlashX` (vision) | 0.04 | 0.004 | 0.40 | vision, not relevant |

"Cached input storage" is "Limited-time Free" for paid models.

### 2. Rate limits for the free Flash models

- The Z.ai FAQ only says "You can check the rate limits from here: https://z.ai/manage-apikey/rate-limits". That page needs a login. Numbers for `GLM-4.7-Flash` / `GLM-4.5-Flash`: **not found**.
- The bigmodel.cn rate-limit doc (Chinese; same company, different site) describes the scheme. Limits are on **concurrency**, meaning requests being processed at the same moment. Each model has its own cap, and the cap depends on the account's user-rights level. It does not state a per-minute or per-day cap. Error 1302 means the account hit its limit; 1305 means the whole platform is overloaded for that model. Higher limits can be requested by form (reviewed within 10 working days). That api.z.ai uses the same scheme is inferred.
- Fit for a run (inferred): 9,200 calls in 4 to 8 hours is one call every 3 to 6 seconds. A loop that sends one call at a time uses a concurrency of 1. If the free cap is at least 1, the number of calls is not the problem. Whether it is at least 1, and whether the free model gets throttled at busy times (error 1305), is unknown.

### 3. Tool calling, structured output, thinking off on the free Flash models

- Tool calling: the GLM-4.7 family page lists "Powerful tool invocation capabilities" for the series. It does not name Flash in that list. The function-calling page names only `glm-5.3` and has no supported-model list. **Not documented for `GLM-4.7-Flash` or `GLM-4.5-Flash` specifically.** `tool_choice` supports only `auto`.
- Structured output: the page says "such as `glm-5`, `glm-4.7`, `glm-4.6`, etc.". The Flash models are not named. The API reference lets text models set `response_format` to `json_object`. **Not documented for the free Flash models.**
- Thinking off: the thinking-mode page says the GLM-4.7 series can disable it with `"thinking": {"type": "disabled"}`, default enabled. It does not name `GLM-4.7-Flash` separately. Inferred: it follows the series. `GLM-5.3` and `GLM-5.3-Flash` cannot disable thinking.
- The chat-completion API reference model list (text: glm-5.3 ... glm-4.6) does not include `glm-4.7-flash` or `glm-4.5-flash`, so the exact ID strings are not confirmed by the API reference. (Inferred from the pricing table names: `glm-4.7-flash`.)

### 4. Canada access and payment method

- Canada: **not found**. The terms (X.3) have you confirm you are not in Iran, North Korea, Cuba, Crimea, Donetsk or Zaporizhzhia. Canada is not on that list. No other country list was found.
- Payment method for free models: **not found**. The FAQ mentions credit-card top-ups without 3DS only. Age: services are "not directed to" under-18s (privacy policy section 9).
- I did not sign up.

### 5. Data terms for free models

- No page separates free from paid models. Terms section VII.2 mentions free quota only in general.
- Training: Additional Terms 3(b): "We will not use End User Content to develop or improve Services, unless you explicitly agree to such use." Terms IV.7 says the same for API developers. Whether it covers the free models is **not stated** (silence is not permission).
- Retention: DPA 4(b): "The Company do not store any of the content the Customer or its End Users provide or generate while using our Services." Other customer data is kept temporarily and deleted after the terms end.
- Location: "generally processed in Singapore" (privacy policy section 8, DPA 3(a)). Governing law is Singapore.
- The privacy policy itself says it applies to individual users; the DPA covers API use.

### 6. Fixed version or moving name; LangChain class

- Names on the pricing page have no date (`GLM-4.7-Flash`). No pinned or dated ID found. Terms III.1 lets Z.ai add, upgrade, modify or suspend services; XII.2 gives at least 30 days notice for termination. No model deprecation policy found. **Fixed version: not found; treat as a moving name (inferred).**
- LangChain: Z.ai's own docs use `ChatOpenAI` from `langchain_openai` with `openai_api_base="https://api.z.ai/api/paas/v4/"` (examples use `glm-5.3`). The official LangChain docs have no Z.ai page at the URLs I tried (404). Earlier research noted `ChatOpenAI` drops `reasoning_content`; with thinking disabled on the 4.7 models that should matter less (inferred, untested).

### 7. Independent measurement of multi-step tool calling

**None found from a primary source.** The Z.ai pages read contain no benchmark for `GLM-4.7-Flash` tool use. I did not search beyond Z.ai pages.

## Which model is "GLM Flash" on the price/capability chart (inferred)

Most plausibly `GLM-4.7-Flash` (free, so $0 on a price axis, and the newest free text model), or possibly `GLM-4.5-Flash`. A paid Flash model would not look "by far the cheapest". Inferred, not confirmed: I have not seen the chart.

## Cost table

Per full evaluation: 17,000 input + 1,000 output tokens, no caching, no thinking tokens (thinking-forced models will cost more).

| Model | Per evaluation | 800 | 2,300 | 4,600 |
|---|---|---|---|---|
| `GLM-4.7-Flash` / `GLM-4.5-Flash` | $0 | $0 | $0 | $0 |
| `GLM-4.7-FlashX` | $0.00159 | $1.27 | $3.66 | $7.31 |
| `GLM-5.3-Flash` | $0.00305 | $2.44 | $7.02 | $14.03 |
| `GLM-5.3-FlashX` | $0.00754 | $6.03 | $17.34 | $34.68 |
| `claude-haiku-5-5` (chosen) | $0.0022 | $1.76 | $5.06 | $10.12 |

## Not verified

- Actual free-model rate-limit numbers (page needs login; I did not sign up).
- Tool calling and structured output for `GLM-4.7-Flash` / `GLM-4.5-Flash` by name.
- Canada access; whether a free model needs a card.
- Whether the data terms cover the free models.
- A dated or pinned model ID; deprecation policy.
- Any benchmark of the free models on multi-step tool calling; nobody has tested them on this agent's job.
- Real thinking-token output of any thinking model (costs above exclude it).
- The chart the developer saw.
