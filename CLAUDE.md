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

## Agent skills

### Issue tracker

Issues live in GitHub Issues for lofeodo/agentic-jev-trader (gh CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
