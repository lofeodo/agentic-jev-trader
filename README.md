# agentic-jev-trader

A trading agent with memory, tested on a historical market simulation. Every 15 minutes
of replayed market time it may act or do nothing, records every decision, and uses
those records plus a playbook of candle patterns to trade better over time. The main
measure is net profit after all costs on a period it never saw during development, and
whether memory makes it more profitable. No real orders are ever placed.

Built with LangGraph, four custom MCP servers, the Jev decision model, Snowflake,
Kubernetes (kind), Terraform and LangSmith.

**Status:** under construction. The repo scaffold is in place; nothing runs yet. See
the [roadmap](docs/ROADMAP.md).

## Set up

Requires conda. From the repo root, in `cmd` or a bash shell:

```text
conda create -n agentic-jev-trader python=3.12 -y
conda run -n agentic-jev-trader python -m pip install -r requirements.txt
conda run -n agentic-jev-trader python -m pytest
```

Copy `.env.example` to `.env` for the keys later steps need.

## Documentation

- [Roadmap](docs/ROADMAP.md): features, steps and progress
- [Specification](docs/project-breakdown.md)
- [Architecture](docs/architecture.md)
- [Development](docs/development.md): environment, tests, lint, CI, branches
- [Configuration](docs/configuration.md): environment variables
- [Decisions](docs/DECISIONS.md)
