terraform {
  required_version = ">= 1.16"

  required_providers {
    snowflake = {
      source  = "snowflakedb/snowflake"
      version = "~> 2.23"
    }
  }

  # State is kept outside the repo, in the folder `infra/terraform.py` passes with
  # -backend-config=path=... (see infra/README.md). It holds public keys and grant
  # details, and a git worktree is deleted when its work ends.
  backend "local" {}
}
