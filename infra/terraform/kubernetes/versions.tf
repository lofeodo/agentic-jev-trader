terraform {
  required_version = ">= 1.16"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 3.5"
    }
  }

  # A root of its own, apart from the Snowflake part in the folder above: its own provider and
  # its own state, so deploying to a kind cluster never touches Snowflake. State stays outside
  # the repo, as for the Snowflake part (-backend-config=path=...).
  backend "local" {}
}
