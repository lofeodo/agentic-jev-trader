# Jev API: format, SDK, limits, pricing, access

Issue: #8 (map #7). All pages read on 2026-11-11 from the official TypeSafe AI docs (https://docs.typesafe.ai) and homepage. Third-party write-ups (OpenRouter, AI/ML API, blogs) exist but were not used for facts. Where the official docs are silent, this says "not found".

## Request and response format

Source: https://docs.typesafe.ai/api/system-one.md

- `POST https://api.typesafe.ai/v1/systemone`, header `Authorization: Bearer <API_KEY>`. JSON, or multipart (only needed for images).
- Body: `model` (required, name or alias), `state` (required: string, object or array), `questions` (required, object of 1 or more named questions), `assets` (optional, images).
- Question types: `noul` (yes/no), `choice`, `score`, `box` (image bounding box, Jev 1.14 only). `instructions` is a string, object, array or null.
- `choice`: `criteria` required, 1 to 255 entries (name to description). `score`: `criteria` required, ordered array of 1 to 10 levels (the score page, https://docs.typesafe.ai/primitives/score.md, says at least 2 levels for a real scale). Level value = array position starting at 0.
- Response: `model` (may differ from the alias sent), `answers` keyed by your question names, `usage` (`input_tokens` billable, `output_tokens` currently free).
  - noul: `noul` (0 to 1 probability of yes).
  - choice: `choice` (top option), `confidence` (0 to 1), `probabilities` per option (sum about 1).
  - score: `score` (probability-weighted average of level numbers, fractional), `confidence`, `legend`, `probabilities` per level.
- Errors (https://docs.typesafe.ai/api/errors.md): 400 rule broken or context exceeded (`max_tokens_exceeded`), 401 bad key, 413 body over 32 MiB, 415 bad Content-Encoding, 422 validation, 429 rate limit, 529 overloaded. Retry 429/529 with exponential backoff.
- Request rules: body at most 32 MiB; UTF-8 JSON; nesting at most 64 levels in each of state, instructions, criteria; only finite numbers; send identifiers and exact large quantities as strings; gzip or zstd accepted.
- OpenAPI spec: https://api.typesafe.ai/openapi.json (listed in the docs index; not fetched).

## Python SDK

Sources: https://docs.typesafe.ai/sdk/python.md, https://docs.typesafe.ai/sdk/python/usage.md, https://docs.typesafe.ai/introduction/quickstart.md

- Package `typesafe-sdk` (`pip install typesafe-sdk`), import `typesafe_sdk`. Python 3.10+ (quickstart). Extras: `http2`, `pil`, `zstd`. Version number not stated in the docs.
- Clients: `TypeSafeClient` (sync) and `AsyncTypeSafeClient`, both context managers. Key read from env var `TYPESAFE_API_KEY`. `TypeSafeClient(model="jev-latest")` sets the model.
- Call: `client.system_one(state=..., questions={"name": Noul(...) | Choice(instructions=..., criteria={...}) | Score(instructions=..., criteria=[...])})`. Response accessors: `response.nouls[name].noul`, `.choices[name].choice`, `.scores[name].score`. Typed responses via a `SystemOneResponse` subclass or plain Pydantic model; `result.request_id` exists.
- Retries: `RetryPolicy(max_retries=3, backoff_max=0.2, timeout=1.0)` on the client or per call. Default values not found in the pages read (they link to a retries reference page not fetched).
- Exceptions: `TypeSafeError` (invalid API key at client creation), `TypeSafeAPIError` (has `status`, `request_id`).
- A JavaScript SDK (`@typesafe-ai/sdk`) and plain curl also work. Not needed here.

## Limits

Sources: https://docs.typesafe.ai/models.md, https://docs.typesafe.ai/primitives/choice.md, https://docs.typesafe.ai/primitives/score.md, https://docs.typesafe.ai/patterns.md

- Choice: up to 255 options ("adding options costs a few tokens each"). Confirms the brief.
- Score: up to 10 levels. Confirms the brief.
- Noul: yes/no, probability of yes. Confirms the brief.
- Questions per request: no maximum stated. Questions are evaluated in parallel and adding questions "usually has little effect on response time"; extra questions still cost tokens.
- Context: 64k tokens per request and 32k tokens per question. The state counts once against each of these limits (https://docs.typesafe.ai/model-jaggedness.md), so state plus one question's criteria must fit 32k. Header `TypeSafe-Danger-Zone-Long-Context: true` raises both to 262k, but long-context requests are "slower and less accurate". Over the limit returns 400 `max_tokens_exceeded`.
- Models: `jev-1.14.0` (available from 2026-10-14; Choice, Score, Noul, Box), `jev-1.13.0` (Choice, Score, Noul). `jev-latest` and `jev-preview` both point to 1.14.0. A moving alias is a reproducibility risk, so a backtest should pin an explicit version (my inference; no statement about determinism or alias stability was found).
- Rate limits: per organization, in tokens and requests per second; 429 when exceeded; SDKs retry and honor `retry-after`. Numeric thresholds not found; higher limits on custom/enterprise plans.
- Deprecation policy and retirement dates: not found. A model changelog page is listed in the docs index; the URL I guessed (`/model-changelog.md`) returned 404, so it was not read.

## Pricing

- $42 per billion input tokens ($0.042 per million); output tokens free; long context costs the same per token. Jev 1.13 and 1.14 same price. Sources: https://docs.typesafe.ai/models.md, https://typesafe.ai (homepage).
- Not found: whether the state is billed once per request or once per question; minimum charges; free credits; plans or tiers; invoicing. The quickstart and legal pages do not mention cost or credits.
- Rough scale (my estimate, not from docs): 10,000 calls of 5,000 input tokens is 50M tokens, about $2.10. Even if the state were billed once per question (4 questions), about $8.40. Jev cost is negligible next to LLM cost.

## Latency

- No latency guarantee or baseline in the docs pages. The homepage benchmark chart shows 0.114 s for Jev on its own sample workload (https://typesafe.ai; vendor marketing figure, and the page's headline multiples do not match its own chart). Long context is slower. Plan to measure ourselves.

## Access and account

- API keys: created in the console at https://console.typesafe.ai/keys (login required); Playground at https://console.typesafe.ai/playground. The quickstart (https://docs.typesafe.ai/introduction/quickstart.md) does not mention a waitlist, signup steps, or cost. The homepage says "Try ... Jev, in early access" and gives no signup route beyond a contact page. Whether a waitlist or approval is required: not found in official pages (third-party posts mention a waitlist; unverified). Account creation was not attempted (instruction: no signups).
- Legal (https://docs.typesafe.ai/legal.md): the Privacy Policy commits not to train models on user data; zero data retention is enterprise-only. No statement on financial or trading use, SLA, or early-access terms.

## Behaviour that matters for the brief

Source: https://docs.typesafe.ai/model-jaggedness.md and the choice/score pages.

- "Jev is not a calculator": it struggles with numeric precision, does not count reliably, and its score levels are weak in numerical calibration. Do not read exact magnitudes from scores.
- In a Choice, "Jev leans toward the option that comes first": option order can change the answer.
- State is not treated as hostile; text in the state can steer answers (relevant for LLM-written candidate reasons and episode text going into state).
- Confidence is derived from the spread of the probabilities, not from correctness. Probability calibration is not evidenced in the pages read (the AI primer page says decision models are trained for calibrated probabilities; it was not fetched).
- Score levels are 0-based, and the model does not see level numbers.
- Not found: Jev's training-data cutoff, which matters for historical simulation (a model might know the outcomes of past dates).

## Check of brief sections 10.4 and 11

- Question types and limits (255 options, 2 to 10 levels, yes/no): confirmed.
- Official Python SDK and pricing: confirmed.
- `decide` with four questions in one call: allowed, no cap on questions stated.
- Size formula sum(p_i * b_i): feasible (choice returns per-option probabilities), but option-order bias and "not a calculator" mean bucket labels should be written as words/descriptions, and the order of buckets (and of candidates in `trade`) should be varied or tested, e.g. shuffled with a seed, since the first option is favoured. Probabilities are not shown to be calibrated for this domain, so treat the size as a model-driven average.
- `conviction` score of 5 levels: the result is 0 to 4, not 1 to 5. The code must map it.
- Secret name `jev-api-key`: the SDK reads `TYPESAFE_API_KEY`; set that env var in the pod or pass the key explicitly.
- Per-question 32k token limit: the state (patterns, playbook, track record, episodes, open positions with journals) must stay well below it.
- Reproducibility: use a pinned model name such as `jev-1.14.0` instead of `jev-latest` for evaluation runs, and record the `model` field returned.
