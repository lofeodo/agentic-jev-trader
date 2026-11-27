# Which cluster to deploy to, which images to run, where the database is, and the secrets the
# services and jobs read.
#
# The secret values are passed in when Terraform runs (TF_VAR_*), never written in the repo.
# They are ephemeral and reach the cluster only through write-only attributes, so Terraform
# keeps them in neither its state nor a saved plan.

variable "kubeconfig_path" {
  description = "The kubeconfig file that `kind create cluster` writes to."
  type        = string
  default     = "~/.kube/config"
}

variable "kube_context" {
  description = "The kind cluster's context in that file: kind-<cluster name>."
  type        = string
  default     = "kind-jev-trader"
}

variable "image_tag" {
  description = "The git commit both images are tagged with (python and web): `python infra/images.py tag`."
  type        = string
}

variable "database" {
  description = "The database the memory server and the API serve (Postgres's trading_agent or trading_agent_test)."
  type        = string
  default     = "TRADING_AGENT"

  validation {
    condition     = contains(["TRADING_AGENT", "TRADING_AGENT_TEST"], var.database)
    error_message = "database must be TRADING_AGENT or TRADING_AGENT_TEST."
  }
}

variable "postgres_host" {
  description = "POSTGRES_HOST from .env: the database's address, as the programs in the cluster reach it (RDS's address; never 127.0.0.1, which in a pod names the pod itself)."
  type        = string

  validation {
    condition     = !contains(["127.0.0.1", "localhost", "::1", ""], lower(trimspace(var.postgres_host)))
    error_message = "postgres_host must be an address the cluster can reach: 127.0.0.1 or localhost in a pod names the pod itself."
  }
}

variable "postgres_port" {
  description = "POSTGRES_PORT from .env: the database's port."
  type        = number
  default     = 5432
}

variable "postgres_ssl_mode" {
  description = "POSTGRES_SSL_MODE from .env: require (encrypted, the default) for RDS; disable only for a local Postgres without encryption."
  type        = string
  default     = "require"
}

variable "postgres_passwords" {
  description = "The password of each login that runs in the cluster (api, memory, sim, builder), POSTGRES_<LOGIN>_PASSWORD from .env, by login."
  type        = map(string)
  sensitive   = true
  ephemeral   = true
}

variable "twelve_data_api_key" {
  description = "TWELVE_DATA_API_KEY from .env, for dataset build jobs."
  type        = string
  sensitive   = true
  ephemeral   = true
}

variable "typesafe_api_key" {
  description = "TYPESAFE_API_KEY from .env (Jev), for sim jobs."
  type        = string
  sensitive   = true
  ephemeral   = true
}

variable "anthropic_api_key" {
  description = "ANTHROPIC_API_KEY from .env (the LLM), for sim jobs."
  type        = string
  sensitive   = true
  ephemeral   = true
}

variable "secrets_revision" {
  description = "Raise by one to send changed secret values: Terraform cannot see a write-only value change, so it rewrites the secrets only when this number changes."
  type        = number
  default     = 1
}
