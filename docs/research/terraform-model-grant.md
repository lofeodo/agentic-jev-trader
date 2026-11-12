# Snowflake: can Terraform grant the embedding model permission to a role (issue #47)

Read on 2026-11-12. Sources are Snowflake docs and the provider's GitHub repo (snowflakedb/terraform-provider-snowflake, latest release v2.23.0, published 2026-11-05). "Source says" and "Inference" are kept apart. Nothing here was run against a live account.

## Answer in brief

- Yes. The provider has a Stable resource, `snowflake_grant_application_role`, that grants an application role to an account role. Snowflake's per-model roles (`CORTEX-MODEL-ROLE-...`) are application roles of the `SNOWFLAKE` application, so this resource should fit. No `snowflake_execute` workaround appears to be needed. (Inference: the docs do not show this resource used on a `SNOWFLAKE` system application role; test it with `terraform plan/apply` first.)
- Arguments: `application_role_name = "\"SNOWFLAKE\".\"CORTEX-MODEL-ROLE-SNOWFLAKE-ARCTIC-EMBED-M-V1.5\""` and `parent_account_role_name = snowflake_account_role.<x>.name`.
- The database role `SNOWFLAKE.CORTEX_USER` (or `CORTEX_EMBED_USER`) is separate and still needed. `snowflake_grant_database_role` (Stable) grants it.

## Q-main. Terraform resource for the model grant

- `snowflake_grant_application_role`: docs page says `subcategory: "Stable"`. Required: `application_role_name`. Optional (exactly one of): `parent_account_role_name` (account role) or `application_name`. Example in docs grants `"my_application"."app_role_1"` to an account role. Source: https://github.com/snowflakedb/terraform-provider-snowflake/blob/main/docs/resources/grant_application_role.md (read 2026-11-12).
- The resource runs the SQL `GRANT APPLICATION ROLE <name> TO ROLE <role>`. Its identifier is validated as a two-part database-object identifier (`"db"."name"`), which matches `"SNOWFLAKE"."CORTEX-MODEL-ROLE-..."`. Source: https://github.com/snowflakedb/terraform-provider-snowflake/blob/main/pkg/resources/grant_application_role.go (read 2026-11-12).
- Fallback, if the apply fails on the hyphenated name: `snowflake_execute` (Stable) with `execute = "GRANT APPLICATION ROLE SNOWFLAKE.\"CORTEX-MODEL-ROLE-SNOWFLAKE-ARCTIC-EMBED-M-V1.5\" TO ROLE <ROLE>"` and a matching `revert = "REVOKE APPLICATION ROLE ... FROM ROLE <ROLE>"`. The docs warn it runs ANY SQL, and not to use `USE ROLE`; use provider aliases for a different role. Source: https://github.com/snowflakedb/terraform-provider-snowflake/blob/main/docs/resources/execute.md (read 2026-11-12).
- Who must run it. Source says: the grant needs the application owner, or a role that holds the application role WITH GRANT OPTION; MANAGE GRANTS is not enough. ACCOUNTADMIN can grant Snowflake's application roles because it holds them with grant option. Source: https://docs.snowflake.com/en/sql-reference/sql/grant-application-role (read 2026-11-12). Inference: the Terraform provider must connect as ACCOUNTADMIN (or a role granted these roles with grant option) for this resource; SECURITYADMIN alone would likely fail.
- Open provider issue #5355 asks for `WITH GRANT OPTION` support on the grant resources (open as of 2026-10-30). Not needed for this use. Source: https://github.com/snowflakedb/terraform-provider-snowflake/issues/5355.
- No resource for the refresh procedure exists; see Q1.

## Q1. Is `CORTEX_BASE_MODELS_REFRESH` needed?

Source says (https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-privileges-and-access, read 2026-11-12):
- `SNOWFLAKE.MODELS` is refreshed daily by a Snowflake-managed task, `SNOWFLAKE.MODELS.CORTEX_BASE_MODELS_REFRESH_TASK`. The refresh creates the model objects and the matching application roles. It cannot be modified or scheduled by you and costs no compute.
- ACCOUNTADMIN can call `CALL SNOWFLAKE.MODELS.CORTEX_BASE_MODELS_REFRESH();` on demand, mainly for newly released models. Running it again is safe and creates no duplicates.
- Intermittent `FAILED` on the task is expected.

Inference: no periodic manual run is needed. A one-time manual call is only useful when the per-model role does not exist yet (for example, just after account creation, as happened here). Once the role exists, the daily task keeps it current. Terraform cannot call it except via `snowflake_execute`; a manual step is simpler. Ordering caveat: the grant resource will fail with "does not exist" if applied before the role exists.

## Q2. Per-model role versus `CORTEX-MODEL-ROLE-ALL`

Source says: access works via application roles named `CORTEX-MODEL-ROLE-<MODEL>`, plus `CORTEX-MODEL-ROLE-ALL` covering all current and future models. Exact statements, as documented (same page):

```sql
GRANT APPLICATION ROLE SNOWFLAKE."CORTEX-MODEL-ROLE-LLAMA3.1-70B" TO ROLE MY_ROLE;
GRANT APPLICATION ROLE SNOWFLAKE."CORTEX-MODEL-ROLE-ALL" TO ROLE MY_ROLE;
```

For this model (the name comes from the error on the account, per the ticket; not on the docs page):

```sql
GRANT APPLICATION ROLE SNOWFLAKE."CORTEX-MODEL-ROLE-SNOWFLAKE-ARCTIC-EMBED-M-V1.5" TO ROLE <ROLE>;
GRANT APPLICATION ROLE SNOWFLAKE."CORTEX-MODEL-ROLE-ALL" TO ROLE <ROLE>;
```

Inference: for a role that uses one model, the per-model role is preferable (least privilege; the role cannot call other, costlier models, and new models do not silently become available). The ALL role is simpler but open-ended.

Other source-stated facts: access is granted if either Model RBAC or the old allowlist permits it. ACCOUNTADMIN always has all models (so a test as ACCOUNTADMIN proves nothing; test as the real role with `USE SECONDARY ROLES NONE`). Accounts with allowlist `'All'` (the new default) get a bootstrap grant of `CORTEX-MODEL-ROLE-ALL` to `SNOWFLAKE.PUBLIC`, so every role may already have access; it can only be removed with `SNOWFLAKE.LOCAL.REVOKE_FROM_PUBLIC_APPLICATION_ROLE`. Inference: on this account the explicit grant may be redundant until the bootstrap grant is revoked or the allowlist set to `'None'`, but explicit grants make the setup correct when that happens. The allowlist can only be set to `'None'` from August 2026 and will be removed later in 2026.

## Q3. Database role still required? Can Terraform grant it?

- Source says: AI_EMBED needs a role with database role `SNOWFLAKE.CORTEX_USER` or `SNOWFLAKE.CORTEX_EMBED_USER`. Source: https://docs.snowflake.com/en/sql-reference/functions/ai_embed (read 2026-11-12). That page does not mention Model RBAC.
- Source says: model access is separate from feature access; callers still need the Cortex privileges. `CORTEX_USER` is granted to PUBLIC by default; `CORTEX_EMBED_USER` is not, and covers AI_EMBED, EMBED_TEXT_768/1024 and managed-embedding Cortex Search. Source: the privileges page above.
- Inference: so the ordinary role normally already has `CORTEX_USER` via PUBLIC, but grant `CORTEX_EMBED_USER` explicitly (narrowest) so setup does not depend on PUBLIC.
- Terraform: `snowflake_grant_database_role` (docs `subcategory: "Stable"`), arguments `database_role_name = "\"SNOWFLAKE\".\"CORTEX_EMBED_USER\""` and `parent_role_name = snowflake_account_role.<x>.name`. Source: https://github.com/snowflakedb/terraform-provider-snowflake/blob/main/docs/resources/grant_database_role.md (read 2026-11-12). The docs example uses a provider-managed database role; usage on `SNOWFLAKE.CORTEX_USER` is evidenced by issue #5323, where a user granted exactly that on v2.18.0. A read bug ("Root object was present, but now absent") was fixed in v2.20.0 (BCR-2371 handling); the issue was closed. Source: https://github.com/snowflakedb/terraform-provider-snowflake/issues/5323 (read 2026-11-12). Use v2.23.0, which includes the fix.

## Sketch (untested)

```hcl
resource "snowflake_account_role" "embed" { name = "EMBED_ROLE" }

resource "snowflake_grant_database_role" "embed_user" {
  database_role_name = "\"SNOWFLAKE\".\"CORTEX_EMBED_USER\""
  parent_role_name   = snowflake_account_role.embed.name
}

resource "snowflake_grant_application_role" "embed_model" {
  application_role_name    = "\"SNOWFLAKE\".\"CORTEX-MODEL-ROLE-SNOWFLAKE-ARCTIC-EMBED-M-V1.5\""
  parent_account_role_name = snowflake_account_role.embed.name
}
```

## Could not verify

- No live test: whether `snowflake_grant_application_role` succeeds on the `SNOWFLAKE` system application and on a name with hyphens and dots; no doc or issue shows it. No issue was found in the provider repo for this resource with Cortex model roles.
- The exact role name `CORTEX-MODEL-ROLE-SNOWFLAKE-ARCTIC-EMBED-M-V1.5` comes from the account's error message, not from a doc page.
- Whether `CORTEX_EMBED_USER` is strictly required when the role already has `CORTEX_USER` via PUBLIC (docs say either one).
- The Terraform Registry web pages could not be read (JavaScript site); the same docs were read from the provider repo's `docs/resources` on `main`. The `main` docs may differ slightly from the v2.23.0 tag.
- Whether the bootstrap `SNOWFLAKE.PUBLIC` grant is active on this trial account (check with `SHOW GRANTS TO APPLICATION ROLE SNOWFLAKE.PUBLIC;`).
- Whether the Terraform provider's connecting role (not ACCOUNTADMIN) can be given the grant option on these roles.
