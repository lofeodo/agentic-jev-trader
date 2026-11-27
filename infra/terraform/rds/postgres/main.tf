# Inside the RDS database (spec appendix 11, section 1): the five logins, the two databases and
# pgvector. The same as infra/local-postgres/init.sql makes in the local Postgres the tests use.
# What each login may read and write is granted by Alembic's first file, as it makes the tables
# (infra/alembic/versions/0001_todays_tables.py): here the logins get no rights at all. The
# memory login is granted reading only there, so it can only ever read (ADR 0006).

provider "postgresql" {
  host      = var.host
  port      = 5432
  username  = var.admin_user
  password  = var.admin_password
  sslmode   = "require"
  superuser = false # RDS's admin login is not a true superuser
}

locals {
  # Must match jev_trader.storage.postgres (LOGINS, DATABASE, TEST_DATABASE).
  logins    = toset(["builder", "sim", "memory", "api", "setup"])
  databases = toset(["trading_agent", "trading_agent_test"])
}

resource "postgresql_role" "login" {
  for_each = local.logins

  name                = "trading_agent_${each.key}"
  login               = true
  password_wo         = var.passwords[each.key]
  password_wo_version = var.passwords_version
}

# Both owned by the setup login, which makes the tables in them.
resource "postgresql_database" "this" {
  for_each = local.databases

  name  = each.key
  owner = postgresql_role.login["setup"].name
}

# pgvector, for the lists of numbers memory compares. Only the admin may add it.
resource "postgresql_extension" "vector" {
  for_each = local.databases

  name     = "vector"
  database = postgresql_database.this[each.key].name
}
