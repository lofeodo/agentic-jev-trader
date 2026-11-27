terraform {
  required_version = ">= 1.16"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 3.5"
    }
  }

  # A root of its own, apart from the RDS part: its own provider and its own state. State stays
  # outside the repo (-backend-config=path=..., passed by infra/deploy.py).
  backend "local" {}
}
