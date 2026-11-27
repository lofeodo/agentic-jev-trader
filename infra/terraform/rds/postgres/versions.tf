terraform {
  required_version = ">= 1.16"

  required_providers {
    postgresql = {
      source  = "cyrilgdn/postgresql"
      version = "~> 1.26"
    }
  }

  # What is inside the RDS database, a root of its own: it logs in to the database, so it runs
  # only once the database exists and is switched on (infra/rds.py runs it after the AWS root).
  # State stays outside the repo (-backend-config=path=..., passed by infra/rds.py).
  backend "local" {}
}
