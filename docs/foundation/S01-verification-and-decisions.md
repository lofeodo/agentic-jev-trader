# S01. Verification and developer decisions

**Status:** todo

**Summary:** Every VERIFY item that shapes a shared contract checked against official documentation, and the developer decisions from the spec settled and logged.

## Goal

Work through spec section 22. Check against current official docs: the Jev API (request format, Python SDK, question limits, rate limits, pricing); LangGraph, LangSmith and LangChain MCP adapter versions and usage; LangSmith free-tier limits against the traces a backtest produces; the Snowflake vector type, similarity functions and embedding functions in the account's region; the Snowflake Terraform provider; the MCP Python SDK HTTP transport; passing trace context from the agent to MCP servers; TA-Lib installation on Windows and in a container. Record each finding with its source and date. Collect the developer's decisions: LLM provider and model, data providers and budget, changes to the section 6 assumptions, and the assets of the first dataset.

**Done when:** Every item has a recorded answer or an explicit 'still open, owned by step X', and the choices made under the spec's technology rule are logged with the reason.

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

- All four developer decisions in spec section 22 need the author.
- Deep provider detail (history depth, rate limits, licence terms) can stay with the dataset-builder steps; only the choice of provider and budget is needed here.
- What the `editorial-ui` skill specifies for the frontend is checked in web-app S2, not here.

## Decisions

None yet. New entries go in `docs/DECISIONS.md` under the `FND` heading.
