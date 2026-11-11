# Snowflake: vector search, embeddings, cost, Terraform provider (issue #11)

Read on 2026-11-11. All facts below come from official Snowflake docs, the Snowflake Service Consumption Table PDF (effective 2026-11-09), and the official provider repo. Items I could not verify are in the last section.

## Answer in brief

- Recommend **AWS, region `ca-central-1` ("Canada (Central)")** for the trial account. It is the only Canadian region where Cortex embeddings run natively.
- **Cross-region inference is not needed** for embeddings there if you use `snowflake-arctic-embed-m-v1.5`, `snowflake-arctic-embed-m`, or `snowflake-arctic-embed-l-v2.0`. `e5-base-v2` and `voyage-multilingual-2` are not native in that region.
- Vector search is exact (brute force) with `VECTOR` plus similarity functions; there is no ANN index in the docs. For tens of thousands of rows that is fine.
- An XS warehouse is 1 credit per hour. Keeping it awake for hours costs on the order of $9 to $28 per run (4 to 8 hours); embedding calls are negligible next to that.
- Terraform: `snowflakedb/snowflake`, v2.23.0 (2026-11-05). Every resource the brief needs is Stable.
- Service user auth: key-pair for a local kind cluster.

## 1. Vector type and similarity functions

- Type is `VECTOR(<type>, <dimension>)`; element types `INT` and `FLOAT` (both 32-bit); max dimension 4096. Source: https://docs.snowflake.com/en/sql-reference/data-types-vector (read 2026-11-11).
- Limitations: no VARIANT storage, no clustering keys, no Snowpipe, no Iceberg tables, no search optimization service, no Snowflake Scripting, no server-side bind variables (cast in the query), no direct load/unload (use ARRAY then cast). Hybrid tables accept vectors but not as keys. Same page.
- Similarity functions: `VECTOR_COSINE_SIMILARITY`, `VECTOR_INNER_PRODUCT`, `VECTOR_L1_DISTANCE`, `VECTOR_L2_DISTANCE`. Snowpark Python lacks cosine similarity (use SQL). Source: https://docs.snowflake.com/en/user-guide/snowflake-cortex/vector-embeddings (read 2026-11-11); function page https://docs.snowflake.com/en/sql-reference/functions/vector_cosine_similarity.
- Search pattern is `ORDER BY <similarity> ... LIMIT k` (same vector-embeddings page). Neither page mentions an approximate nearest neighbor index. Similarity functions carry no token cost (same page).
- Python connector supports VECTOR from 3.6, Snowpark Python from 1.11 (same page).
- Alternative, not needed here: Cortex Search service (managed hybrid search) https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-search/cortex-search-overview.

## 2. Embedding functions

- Current function is `AI_EMBED(model, text)`; legacy `SNOWFLAKE.CORTEX.EMBED_TEXT_768` and `EMBED_TEXT_1024` still documented. Source: https://docs.snowflake.com/en/sql-reference/functions/ai_embed and the vector-embeddings page above.
- Text models and dimensions: arctic-embed-m-v1.5, arctic-embed-m, e5-base-v2 are 768-dim; arctic-embed-l-v2.0, voyage-multilingual-2, nv-embed-qa-4 are 1024-dim (context 512 tokens, voyage 32,000). Source: vector-embeddings page.
- Needs a role with database role `SNOWFLAKE.CORTEX_USER` or `SNOWFLAKE.CORTEX_EMBED_USER`. Source: ai_embed page.
- Billing: only input tokens are counted for AI_EMBED. Warehouse time still bills while the query runs; Snowflake recommends a warehouse no larger than MEDIUM for these functions. Source: https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-cost (read 2026-11-11).

## 3. Region and cloud availability (eastern Canada)

- Snowflake regions in Canada: AWS `ca-central-1` "Canada (Central)" and Azure `canadacentral` "Canada Central (Toronto)". No GCP Canada region listed. Source: https://docs.snowflake.com/en/user-guide/intro-regions (read 2026-11-11).
- Function availability: AI_EMBED is listed with a check for AWS CA Central 1 in the "extended regions" table. Azure Canada Central does not appear in the Cortex function tables at all. Source: https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-regional-availability (read 2026-11-11). In that same table AI_EXTRACT is marked "Cross-region only" in some columns while AI_EMBED is not, so AI_EMBED is served without cross-region there.
- Model availability: on https://docs.snowflake.com/en/user-guide/snowflake-cortex/model-availability (markdown version, read 2026-11-11), the section "Snowflake > North America: These models run natively in North American regions, without cross-region inference" lists `snowflake-arctic-embed-l-v2.0-8k`, `-l-v2.0`, `-m-v1.5`, and `-m` as available in AWS CA Central 1. In the Microsoft table, `e5-base-v2` has no mark for CA Central 1 (`multilingual-e5-large` does). In the Voyage AI "North America native" table, `voyage-multilingual-2` has no CA Central column.
- Cross-region inference: controlled by account parameter `CORTEX_ENABLED_CROSS_REGION` (ACCOUNTADMIN only; `DISABLED` keeps processing in the home region). Organizations created after 2026-03-09 default to `ANY_REGION`. Credits are consumed in the requesting region; no egress charge. Source: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cross-region-inference (read 2026-11-11). Check the effective value with `SHOW PARAMETERS LIKE 'CORTEX_ENABLED_CROSS_REGION' IN ACCOUNT;` and consider `DISABLED` to keep all processing in Canada.
- Doc inconsistency: the AI_EMBED function page's own region table lists only 8 regions and no Canada, while the regional-availability page lists CA Central 1. Treat the live account as the arbiter: run a one-row `AI_EMBED` test right after sign-up.

## 4. Trial account

- 30 days from sign-up or until the free balance is used, whichever first; only an email is needed; choose cloud, region and edition at sign-up. Source: https://docs.snowflake.com/en/user-guide/admin-trial-account (read 2026-11-11).
- **AI features are disabled by default on self-service trials until a credit card is added**; adding one does not end the trial. Same page.
- Not available in trials: external network access, hybrid tables, outbound private connectivity, Openflow, Duo MFA. Same page.
- At trial end the account is suspended and unused balance expires; upgrade needs a card. Same page.
- The docs do not state the free credit amount (see unverified).

## 5. Cost estimate

Rates from the Snowflake Service Consumption Table, effective 2026-11-09: https://www.snowflake.com/legal-files/CreditConsumptionTable.pdf (read 2026-11-11).

- Standard warehouse XS = 1 credit/hour (Table 1(a)). Gen 2 XS on AWS = 1.35 (Table 1(b)); do not use Gen 2. A resumed warehouse bills at least one minute.
- Credit price, AWS Canada Central on demand: Enterprise $3.50, Business Critical $4.50; Standard appears to be $2.25 (see unverified). Azure Canada Central (Toronto) has no Standard price, Enterprise $3.90. Prices in USD.
- AI credit on-demand price: $2.00 global, $2.20 regional (Table 2(b)).
- Embedding rate: roughly 0.03 to 0.09 AI credits per million input tokens for arctic-embed-m / e5 / voyage-multilingual-2 (see unverified for the extraction problem).

Estimates, XS warehouse:

| Scenario | Credits | Standard ($2.25) | Enterprise ($3.50) |
|---|---|---|---|
| Run kept awake 4 h | 4 | $9 | $14 |
| Run kept awake 8 h | 8 | $18 | $28 |
| Always on (24 h) | 24 | $54 per day | $84 per day |

- Auto-suspend at 60 s does not help while four MCP servers poll more often than every 60 s: the warehouse is billed for the full awake time. Billing stops only between runs (the first 60 s after each resume is the minimum).
- Embeddings: 50,000 episodes at about 200 tokens is about 10M tokens, so roughly 0.3 to 0.9 AI credits (about $1 or less at $2.00 to $2.20). One embedding per agent decision is negligible. Embedding backfill also needs warehouse time while it runs.
- Storage: well under 1 GB, so cents per month (about $23 per TB per month for AWS Canada on demand, Table 3, approximate reading).
- Design consequence (my inference): batch writes and cache reads in the MCP servers, or hold reads in memory during a run, to shorten awake time. Hybrid tables (the low-latency option) are unavailable in trials.

## 6. Terraform provider

- Official provider: `snowflakedb/snowflake`, https://registry.terraform.io/providers/snowflakedb/snowflake. Repo: https://github.com/snowflakedb/terraform-provider-snowflake. Latest release v2.23.0, 2026-11-05 (prior: v2.22.1 2026-10-29, v2.22.0 2026-10-13), via `gh api repos/snowflakedb/terraform-provider-snowflake/releases` on 2026-11-11.
- Support policy: GA; official support starts at v2.0.0 for stable resources only; preview resources are off by default and enabled via `preview_features_enabled`. Source: https://github.com/snowflakedb/terraform-provider-snowflake/blob/main/docs/index.md.
- Resource docs carry a `subcategory`. Checked in `docs/resources/*.md` on main on 2026-11-11, all **Stable**: `database`, `schema`, `warehouse`, `account_role`, `database_role`, `grant_privileges_to_account_role`, `grant_account_role`, `grant_ownership`, `service_user`, `authentication_policy`, `network_policy`, `user_authentication_policy_attachment`, `user_programmatic_access_token`, `resource_monitor`. **Preview**: `user_public_keys` (not needed: `service_user` takes `rsa_public_key` / write-only `rsa_public_key_wo`, Terraform 1.11+).
- Caveats from the `service_user` doc: password-policy and network-policy attachment resources are being reworked; use the `network_policy` attribute on the user.
- Not checked: whether `grant_privileges_to_account_role` covers future grants and the read-everything-except-one-table pattern the brief's role matrix needs; verify when writing the module.

## 7. Authentication for service users

- Users with `TYPE=SERVICE` cannot log in with a password; Snowflake is rolling out disallowance of passwords for service users, and `LEGACY_SERVICE` is a temporary type being deprecated. Sources: https://docs.snowflake.com/en/user-guide/admin-user-management and https://docs.snowflake.com/en/user-guide/security-mfa-rollout (read 2026-11-11).
- Supported methods for service users: key-pair, programmatic access tokens (PAT), workload identity federation (WIF), OAuth. Sources: https://docs.snowflake.com/en/user-guide/key-pair-auth, https://docs.snowflake.com/en/user-guide/programmatic-access-tokens, https://docs.snowflake.com/en/user-guide/workload-identity-federation.
- Snowflake recommends encrypted private keys (AES-256-CBC) and rotation (key-pair-auth page). PATs require the service user to be under a network policy by default (PAT page). WIF is for workloads running on a cloud provider identity (WIF page).
- Provider auth: `authenticator = "SNOWFLAKE_JWT"` with a private key is supported; also PAT, OAuth, WIF. Source: provider `docs/index.md` and `docs/guides/authentication_methods.md`.
- Recommendation (my inference): the agent, MCP servers, and Terraform all run outside any cloud identity (kind on a laptop), so WIF does not apply and PAT needs a stable IP for the network policy. Use **key-pair authentication** with one key per service user (three roles), stored in K8s Secrets and a gitignored local file for Terraform.

## Unverified

- Trial credit amount: not in the docs I read; the signup page did not render it. Check at sign-up.
- Exact embedding rate per million tokens and exact AWS Canada Standard credit price: the PDF text extraction garbled the table columns. Figures above are my best read; the cost conclusion does not depend on them. Confirm in the PDF.
- Whether the trial's AI-features gate affects arctic embedding calls before a card is added: docs say AI features are disabled; assume yes.
- Whether the Canada embedding availability applies to trial accounts: not stated.
