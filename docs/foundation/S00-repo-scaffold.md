# S00. Repo scaffold

**Status:** todo

**Summary:** Repo layout, a conda env with pinned dependencies, pytest, a CI workflow that runs an empty suite, the project CLAUDE.md and the docs skeleton.

## Goal

Create the folder layout from spec section 20, the `agentic-jev-trader` conda env, a pinned `requirements.txt`, `.env.example` listing every variable, pytest configuration with a marker for tests that call paid APIs (skipped by default), a GitHub Actions workflow, a project `CLAUDE.md` and a glanceable README. Pin every dependency the spec already names so later features rarely touch `requirements.txt`.

**Done when:** CI runs the empty test suite green, and the documented env setup commands work unchanged in Windows cmd and in bash.

Spec: [project breakdown](../project-breakdown.md). Feature index: [ROADMAP.md](ROADMAP.md).

## Detailed plan

Not written yet. It is filled in when the step starts, in plan mode, and opens with the
behaviour agreed in the planning interview.

## What was done

Nothing yet.

## Deviations from plan

None yet.

## Open issues

To settle in the planning interview:

- Python version for the env and the container images.
- Where spec section 20 and the global working rules disagree: `ARCHITECTURE.md` at the root versus `docs/architecture.md`, and `agent/prompts/` versus a top-level `prompts/`. Default: follow the global rules.
- The spec's own command examples use cmd-only backslash paths; docs here use forward slashes.
- A README is written in this step: offer the `readme-writing` skill before starting it.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `FND` heading.
