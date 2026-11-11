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
