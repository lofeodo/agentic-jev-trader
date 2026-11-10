# Configuration

All secrets and per-machine settings come from environment variables, read from a `.env`
file at the repo root on a developer machine and from Kubernetes Secrets in the cluster.
`.env` is never committed; [`.env.example`](../.env.example) lists every variable with an
empty value.

**Status:** the names below are provisional. Foundation S2 defines one config model and
confirms or renames them. Foundation S1 chose the providers and confirmed key-pair
sign-in for the Snowflake service users (FND-007 to FND-013); S4 creates the users.
Non-secret run settings (risk limits, buckets, k, minimum sample, prompt version) are not
environment variables: they belong to the config model and the `agent-config` ConfigMap.

## Variables

| Variable | Used by | Meaning |
| --- | --- | --- |
| `SNOWFLAKE_ACCOUNT` | everything that reads or writes Snowflake | Account identifier (`<orgname>-<accountname>`). |
| `SNOWFLAKE_DATABASE` | same | Database name, `TRADING_AGENT`. |
| `SNOWFLAKE_WAREHOUSE` | same | The extra-small warehouse created by Terraform. |
| `SNOWFLAKE_AGENT_USER`, `SNOWFLAKE_AGENT_PRIVATE_KEY_PATH` | agent job, MCP servers | Service user for `AGENT_ROLE` and its private key file. |
| `SNOWFLAKE_BUILDER_USER`, `SNOWFLAKE_BUILDER_PRIVATE_KEY_PATH` | dataset build job | Service user for `BUILDER_ROLE`. |
| `SNOWFLAKE_APP_USER`, `SNOWFLAKE_APP_PRIVATE_KEY_PATH` | API | Service user for `APP_ROLE`. |
| `SNOWFLAKE_ADMIN_USER`, `SNOWFLAKE_ADMIN_PRIVATE_KEY_PATH` | Terraform, migration runner | Administrator; never given to a running service. |
| `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY` | agent job, Jev fallback | Default `deepseek` / `deepseek-flash` (FND-007), combined as `init_chat_model("deepseek:deepseek-flash")`; `deepseek-v4-pro` is the step up. The key is a DeepSeek API key. |
| `JEV_API_KEY`, `JEV_API_URL`, `JEV_MODEL` | jev-decision server | TypeSafe key, `https://api.typesafe.ai`, `jev-1.14.0` (FND-008). OpenRouter fallback: `https://openrouter.ai/api` with an OpenRouter key. |
| `LANGSMITH_API_KEY` | agent job, MCP servers | LangSmith key (free Developer plan, FND-012). |
| `LANGSMITH_PROJECT` | same | LangSmith project name. |
| `LANGSMITH_TRACING` | same | `true` to send traces; nothing is sent without it, even with a key. How much is traced is the tracing level in the config model (S2). |
| `STOCK_DATA_API_KEY`, `STOCK_DATA_API_SECRET` | dataset build job | Alpaca key ID and secret from a free paper-only account (FND-009). Crypto bars come from Coinbase's public API, which needs no key. |

## Where each role's credentials go

Each service gets only its own role's credentials, matching the role table in spec
section 14.1. In particular the agent job and the MCP servers never receive builder,
app or admin credentials, which is what keeps `REF.ASSET_KEY` out of the agent's reach.
