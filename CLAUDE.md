# CLAUDE.md

## Model recommendation on skill invocation (temporary)

Temporary while I learn which model fits which phase; remove this section once I no longer need it.

When I invoke one of the skills below, start your first reply with one line recommending the model and effort for it, e.g. `Model: Opus, high effort`. If the current model or effort differs, say so and suggest switching with `/model`. Then carry on with the skill; don't wait for me to switch.

| Skill | Model / effort |
|---|---|
| `/wayfinder` | Fable, high |
| `/grill-with-docs`, `/grill-me`, `/to-spec`, `/to-tickets` | Opus, high (Fable for big or novel designs) |
| `/diagnosing-bugs` | Opus high, or Fable for hard ones |
| `/code-review` | Opus, high |
| `/implement`, `/tdd` | Opus, medium (high if a ticket keeps going red) |
| `/implement-spec` | Opus, medium |
| `/retro`, `/improve-codebase-architecture`, `/prototype` | Opus, medium–high |
| `/pr`, `/handoff`, `/wait-what`, `/wizard` | Sonnet, medium |
| `/research` | Sonnet, medium |

Rule of thumb: more thinking where decisions get made and mistakes compound; less where a spec or ticket already holds the decisions. Switch at phase boundaries, not mid-phase.

## Plain language

I'm new to finance and trading. This applies to everything I read: chat, issues, comments, and docs.

- Explain each finance, trading, or statistics term in everyday words where it first appears in a message or issue, with a small example in dollars. Terms from `GLOSSARY.md` get the same treatment.
- Lead with what happens to the account, then name the term for it.
- When a question needs background, give the explainer first, then ask.

## Design lens

- **Emulate a successful day trader** (someone who opens and closes trades within the same day). The agent is meant to work the way one does. For each design choice, ask how such a trader would do it, and recommend from there.
- **Reliability first, for now.** Prefer a standard tool used as it comes over our own adjustments to it.
- **The spec is the source.** Version 1 is specified in the issue [Spec: version 1 of the trading agent with memory](https://github.com/lofeodo/agentic-jev-trader/issues/82) and its comments: ten appendices, then the record of the decisions made while it was assembled. What the spec leaves open is listed at the end of each appendix. `docs/project-breakdown.md` is the original brief, superseded and kept for history: it carries no authority.

## Walkthroughs

Two pages are how I read what the models are sent: every message and every reply, word for word on made-up data, with a plain-language note beside each.

- `docs/llm-prompt-walkthrough.html`: the LLM's prompt.
- `docs/jev-reading-walkthrough.html`: what Jev (the decision model) reads and is asked.

A change to what a model is sent updates its page in the same pull request, so page and text always match:

- **the LLM:** system prompt, tool descriptions, message layouts, the limit and re-ask messages;
- **Jev:** the sections of its background, the wording of a question or an option, which questions a request holds.

The pages share one made-up story and one way of writing a past episode: a change to how an episode is written updates both.

## Snowflake setup

`infra/README.md` holds the commands (Terraform, the numbered SQL files, the live check). `terraform apply` changes the developer's account: ask before each one. Private keys and Terraform's state live outside the repo, in `SNOWFLAKE_LOCAL_DIR`.

## Review gate

Per the `review-gate` skill, a PR always gets the `requires-human-review` label when it:

- places orders (an order is an instruction to buy or sell, such as "buy $1,000 of this stock");
- changes risk limits (a risk limit is a cap on the account that code enforces, such as never risking more than $100 of a $10,000 account on one trade);
- touches API keys.

## Agent skills

### Issue tracker

Issues live in GitHub Issues for lofeodo/agentic-jev-trader (gh CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
