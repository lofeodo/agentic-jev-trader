terraform {
  required_version = ">= 1.16"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    http = {
      source  = "hashicorp/http"
      version = "~> 3.5"
    }
  }

  # A root of its own, apart from the Snowflake part and the Kubernetes part: the AWS pieces only.
  # What is inside the database (logins, the two databases, pgvector) is the `postgres/` root
  # beside it, since it can only be reached once the database exists. State stays outside the
  # repo (-backend-config=path=..., passed by infra/rds.py).
  backend "local" {}
}
