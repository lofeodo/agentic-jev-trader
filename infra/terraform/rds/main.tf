# Postgres on AWS RDS (spec appendix 11, sections 1 and 7; ADR 0018): the database, the network
# rule that lets in only this computer's home internet address, and the budget alarm.
# Run through infra/rds.py, never by hand: it passes the passwords from .env and knows whether the
# database is parked (deleted and kept as a snapshot).
# Each apply that makes the database costs money: about 2.3 cents an hour while it is on (1.8 for
# the database, 0.5 for its internet address), and about $2.50 a month for its disk even while
# stopped.

provider "aws" {
  region = "ca-central-1" # Montreal, where the Snowflake trial ran

  default_tags {
    tags = { project = "agentic-jev-trader" }
  }
}

locals {
  identifier = "trading-agent"       # also fixes the database's address, so a restore keeps it (infra/rds.py)
  admin_user = "trading_agent_admin" # infra/rds.py ADMIN_USER
  home_ip    = chomp(data.http.home_ip.response_body)
}

# --- Who may connect: this computer's home internet address only ------------------------------
# Asked afresh on each plan, so re-running Terraform after the address changes moves the rule.

data "http" "home_ip" {
  url = "https://checkip.amazonaws.com"

  lifecycle {
    postcondition {
      condition     = can(cidrhost("${chomp(self.response_body)}/32", 0))
      error_message = "checkip.amazonaws.com did not answer with an internet address."
    }
  }
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "database" {
  name        = "trading-agent-database"
  description = "Postgres from the developer's home internet address only"
  vpc_id      = data.aws_vpc.default.id
}

resource "aws_vpc_security_group_ingress_rule" "home" {
  security_group_id = aws_security_group.database.id
  description       = "Postgres from home"
  cidr_ipv4         = "${local.home_ip}/32"
  ip_protocol       = "tcp"
  from_port         = 5432
  to_port           = 5432
}

resource "aws_db_subnet_group" "database" {
  name       = "trading-agent"
  subnet_ids = data.aws_subnets.default.ids
}

# --- The database --------------------------------------------------------------------------

# Refuses any connection that is not encrypted (already Postgres 17's default on RDS; set here so
# it shows).
resource "aws_db_parameter_group" "database" {
  name   = "trading-agent-postgres17"
  family = "postgres17"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
}

resource "aws_db_instance" "database" {
  count = var.parked ? 0 : 1

  identifier     = local.identifier
  engine         = "postgres"
  engine_version = "17" # the local Postgres the tests use is 17 too (infra/local-postgres)
  instance_class = "db.t4g.micro"
  multi_az       = false

  allocated_storage = 20 # the least gp3 allows
  storage_type      = "gp3"
  storage_encrypted = true

  # From a snapshot (restore), the admin login and everything inside come from it.
  snapshot_identifier    = var.restore_from
  username               = var.restore_from == null ? local.admin_user : null
  password_wo            = var.admin_password
  password_wo_version    = var.admin_password_version
  parameter_group_name   = aws_db_parameter_group.database.name
  db_subnet_group_name   = aws_db_subnet_group.database.name
  vpc_security_group_ids = [aws_security_group.database.id]
  publicly_accessible    = true

  backup_retention_period    = 1 # one day of automatic backups, free up to the disk's size
  auto_minor_version_upgrade = true
  apply_immediately          = true
  copy_tags_to_snapshot      = true

  # infra/rds.py snapshot-and-delete deletes the database itself, with a dated snapshot. This
  # last snapshot is for `terraform destroy` only.
  deletion_protection       = false
  skip_final_snapshot       = false
  final_snapshot_identifier = "trading-agent-final"

  lifecycle {
    # Which snapshot a running database came from does not matter once it runs.
    ignore_changes = [snapshot_identifier]
  }
}

# --- The budget alarm ------------------------------------------------------------------------
# Emails once the month's whole AWS bill passes $5. It warns; it switches nothing off.

resource "aws_budgets_budget" "monthly" {
  name         = "trading-agent-monthly"
  budget_type  = "COST"
  limit_amount = "5"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_email]
  }
}
