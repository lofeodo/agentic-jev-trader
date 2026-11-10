# Configuration

All secrets and per-machine settings come from environment variables, read from a `.env`
file at the repo root on a developer machine and from Kubernetes Secrets in the cluster.
`.env` is never committed; [`.env.example`](../.env.example) lists every variable with an
empty value.

**Status:** the names below are provisional. Foundation S2 defines one config model and
confirms or renames them; S1 and S4 settle how the Snowflake service users authenticate.
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
| `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY` | agent job, Jev fallback | Provider and model are one setting each (chosen in S1). |
| `JEV_API_KEY`, `JEV_API_URL` | jev-decision server | Jev credentials and endpoint. |
| `LANGSMITH_API_KEY` | agent job, MCP servers | Tracing is a no-op when empty. |
| `LANGSMITH_PROJECT` | same | LangSmith project name. |
| `LANGSMITH_TRACING` | same | `true` to send traces. |
| `STOCK_DATA_API_KEY`, `CRYPTO_DATA_API_KEY` | dataset build job | Market data provider keys (providers chosen in S1). |

## Where each role's credentials go

Each service gets only its own role's credentials, matching the role table in spec
section 14.1. In particular the agent job and the MCP servers never receive builder,
app or admin credentials, which is what keeps `REF.ASSET_KEY` out of the agent's reach.
