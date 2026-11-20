# The project's Snowflake setup: two databases with the same schemas, one warehouse,
# five roles, five service users with key-pair login, and the grants between them.
# Spec: issue #82, appendix 6 sections 10-12 and appendix 10 section 4.
# Tables are not made here: the numbered SQL files in infra/migrations make them.

provider "snowflake" {
  organization_name      = var.organization_name
  account_name           = var.account_name
  user                   = var.admin_user
  role                   = "ACCOUNTADMIN" # the embedding model grant needs it; MANAGE GRANTS is not enough
  authenticator          = "SNOWFLAKE_JWT"
  private_key            = file(var.admin_private_key_path)
  private_key_passphrase = var.private_key_passphrase
}

locals {
  # TRADING_AGENT_TEST holds the same tables, for the hand-run tests in tests/snowflake.
  databases = ["TRADING_AGENT", "TRADING_AGENT_TEST"]

  # METADATA holds schemachange's history table.
  schemas = ["REF", "KEYS", "RAW", "FEATURES", "SIM", "MEMORY", "METADATA"]

  warehouse = "TRADING_AGENT_WH"

  # Who reads and writes what (appendix 6 section 10). Access is per schema; the same
  # grants are given on both databases. `usage_only` opens the schema but no table in it:
  # the memory server reads one table of SIM (the sims table, for a sim's settings), and
  # the API writes single tables (REF.DATASETS and the sims table). Those per-table grants
  # go in the numbered SQL file that creates the table, as the migrations role owns it.
  logins = {
    builder = {
      comment    = "Dataset builder. The only role allowed to call the embedding model."
      read       = ["REF", "KEYS", "RAW", "FEATURES"]
      write      = ["REF", "KEYS", "RAW", "FEATURES"]
      usage_only = []
    }
    sim = {
      comment    = "The job that runs a sim. Never reads KEYS."
      read       = ["REF", "RAW", "FEATURES", "SIM", "MEMORY"]
      write      = ["SIM", "MEMORY"]
      usage_only = []
    }
    memory = {
      comment    = "The memory MCP server. Reads only."
      read       = ["REF", "FEATURES", "MEMORY"]
      write      = []
      usage_only = ["SIM"]
    }
    api = {
      comment    = "The API. Reads everything, KEYS included."
      read       = ["REF", "KEYS", "RAW", "FEATURES", "SIM", "MEMORY"]
      write      = []
      usage_only = []
    }
    migrations = {
      comment    = "schemachange. Creates and changes the tables, and owns them."
      read       = []
      write      = []
      usage_only = []
    }
  }

  write_privileges     = ["INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  migration_privileges = ["USAGE", "CREATE TABLE", "CREATE VIEW", "CREATE SEQUENCE"]

  db_schemas = { for pair in setproduct(local.databases, local.schemas) : "${pair[0]}.${pair[1]}" => {
    database = pair[0]
    schema   = pair[1]
  } }

  login_databases = { for pair in setproduct(keys(local.logins), local.databases) : "${pair[0]}.${pair[1]}" => {
    login    = pair[0]
    database = pair[1]
  } }

  # One entry per (login, database, schema) the login may enter.
  schema_access = merge([
    for login, access in local.logins : {
      for pair in setproduct(local.databases, distinct(concat(access.read, access.write, access.usage_only))) :
      "${login}.${pair[0]}.${pair[1]}" => {
        login      = login
        schema_key = "${pair[0]}.${pair[1]}"
        privileges = concat(
          contains(access.read, pair[1]) ? ["SELECT"] : [],
          contains(access.write, pair[1]) ? local.write_privileges : [],
        )
      }
    }
  ]...)

  # Tables get SELECT and the write privileges; views only SELECT.
  future_tables = { for k, v in local.schema_access : k => v if length(v.privileges) > 0 }
  future_views  = { for k, v in local.schema_access : k => v if contains(v.privileges, "SELECT") }

  # The service user of each login logs in with its own key pair, made by
  # `python infra/snowflake_admin.py keys`. Snowflake wants the public key on one line.
  public_keys = { for login in keys(local.logins) : login =>
    replace(file("${var.public_keys_dir}/${login}.pub"), "/-----[A-Z ]+-----|\\s/", "")
  }
}

# --- Databases, schemas, warehouse ---------------------------------------------------

resource "snowflake_database" "this" {
  for_each                       = toset(local.databases)
  name                           = each.key
  comment                        = each.key == "TRADING_AGENT" ? "agentic-jev-trader" : "agentic-jev-trader: hand-run Snowflake tests"
  drop_public_schema_on_creation = true
}

resource "snowflake_schema" "this" {
  for_each = local.db_schemas
  database = snowflake_database.this[each.value.database].name
  name     = each.value.schema
}

resource "snowflake_warehouse" "this" {
  name                = local.warehouse
  warehouse_size      = "XSMALL"
  auto_suspend        = 60
  auto_resume         = "true"
  initially_suspended = true
  comment             = "agentic-jev-trader"
}

# --- Roles and service users ----------------------------------------------------------

resource "snowflake_account_role" "login" {
  for_each = local.logins
  name     = "TRADING_AGENT_${upper(each.key)}"
  comment  = each.value.comment
}

# Snowflake's advice: every custom role sits under SYSADMIN, so admins can manage its objects.
resource "snowflake_grant_account_role" "under_sysadmin" {
  for_each         = local.logins
  role_name        = snowflake_account_role.login[each.key].name
  parent_role_name = "SYSADMIN"
}

resource "snowflake_service_user" "login" {
  for_each                       = local.logins
  name                           = "TRADING_AGENT_${upper(each.key)}_SVC"
  comment                        = each.value.comment
  rsa_public_key                 = local.public_keys[each.key]
  default_role                   = snowflake_account_role.login[each.key].name
  default_warehouse              = snowflake_warehouse.this.name
  default_secondary_roles_option = "NONE" # each login acts as its own role only
}

resource "snowflake_grant_account_role" "to_user" {
  for_each  = local.logins
  role_name = snowflake_account_role.login[each.key].name
  user_name = snowflake_service_user.login[each.key].name
}

# --- Grants ---------------------------------------------------------------------------

resource "snowflake_grant_privileges_to_account_role" "warehouse_usage" {
  for_each          = local.logins
  account_role_name = snowflake_account_role.login[each.key].name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.this.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "database_usage" {
  for_each          = local.login_databases
  account_role_name = snowflake_account_role.login[each.value.login].name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.this[each.value.database].name
  }
}

resource "snowflake_grant_privileges_to_account_role" "schema_usage" {
  for_each          = local.schema_access
  account_role_name = snowflake_account_role.login[each.value.login].name
  privileges        = ["USAGE"]
  on_schema {
    schema_name = snowflake_schema.this[each.value.schema_key].fully_qualified_name
  }
}

# Future grants: a table that schemachange creates later is readable (and writable)
# by the right roles the moment it exists.
resource "snowflake_grant_privileges_to_account_role" "future_tables" {
  for_each          = local.future_tables
  account_role_name = snowflake_account_role.login[each.value.login].name
  privileges        = each.value.privileges
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_schema          = snowflake_schema.this[each.value.schema_key].fully_qualified_name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "future_views" {
  for_each          = local.future_views
  account_role_name = snowflake_account_role.login[each.value.login].name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_schema          = snowflake_schema.this[each.value.schema_key].fully_qualified_name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "migrations_schema" {
  for_each          = local.db_schemas
  account_role_name = snowflake_account_role.login["migrations"].name
  privileges        = local.migration_privileges
  on_schema {
    schema_name = snowflake_schema.this[each.key].fully_qualified_name
  }
}

# --- The embedding model, for the dataset builder only --------------------------------
# Two gates: the database role CORTEX_EMBED_USER (feature access) and the per-model
# application role (model access). The per-model role is used rather than the
# all-models one, so new models do not become available silently.

locals {
  embedding_model_role = "CORTEX-MODEL-ROLE-SNOWFLAKE-ARCTIC-EMBED-M-V1.5"
}

resource "snowflake_grant_database_role" "builder_cortex_embed_user" {
  database_role_name = "\"SNOWFLAKE\".\"CORTEX_EMBED_USER\""
  parent_role_name   = snowflake_account_role.login["builder"].name
}

resource "snowflake_grant_application_role" "builder_embedding_model" {
  count                    = var.embedding_grant_method == "application_role" ? 1 : 0
  application_role_name    = "\"SNOWFLAKE\".\"${local.embedding_model_role}\""
  parent_account_role_name = snowflake_account_role.login["builder"].name
}

# Fallback, if the resource above fails on a Snowflake system role:
# set embedding_grant_method = "execute".
resource "snowflake_execute" "builder_embedding_model" {
  count   = var.embedding_grant_method == "execute" ? 1 : 0
  execute = "GRANT APPLICATION ROLE SNOWFLAKE.\"${local.embedding_model_role}\" TO ROLE ${snowflake_account_role.login["builder"].name}"
  revert  = "REVOKE APPLICATION ROLE SNOWFLAKE.\"${local.embedding_model_role}\" FROM ROLE ${snowflake_account_role.login["builder"].name}"
}

# --- Closing Snowflake's account-wide AI defaults --------------------------------------
# A new account lets every role use every AI model: PUBLIC (a role every login has) holds
# the feature role CORTEX_USER, and the account's model list CORTEX_MODELS_ALLOWLIST is
# "All". With those, any login could embed text, not only the dataset builder (spec,
# appendix 6 section 10), and the builder working would not prove the grant above works.
# Closing them is account-wide: a person's own role also loses AI features unless given
# them the same way. ACCOUNTADMIN keeps access. `terraform destroy` restores both.
# Third default, left in place: Snowflake's own application role SNOWFLAKE.PUBLIC, which
# every role holds through PUBLIC, contains the all-models role. Tried live on 2026-11-20:
# with the model list set to None it still let the builder use models it was never given,
# and revoking it is refused even to ACCOUNTADMIN ("Insufficient privileges"). So the
# feature gate (CORTEX_USER) is what keeps every other login from embedding; the per-model
# grant above is in place but cannot be shown to work alone on this account.

resource "snowflake_execute" "public_loses_cortex_user" {
  execute = "REVOKE DATABASE ROLE SNOWFLAKE.CORTEX_USER FROM ROLE PUBLIC"
  revert  = "GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE PUBLIC"
}

resource "snowflake_account_parameter" "cortex_models_allowlist" {
  key   = "CORTEX_MODELS_ALLOWLIST"
  value = "None"
}

# First set with snowflake_execute; handed to the provider's own resource above without
# touching the account. Both blocks can go once every state has been through one apply.
removed {
  from = snowflake_execute.no_models_by_default
  lifecycle {
    destroy = false
  }
}

import {
  to = snowflake_account_parameter.cortex_models_allowlist
  id = "CORTEX_MODELS_ALLOWLIST"
}
