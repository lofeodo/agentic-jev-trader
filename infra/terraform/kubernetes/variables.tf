# Which cluster to deploy to, which images to run, and the secrets the services and jobs read.
# Secrets are passed in (TF_VAR_*), never written in the repo.

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
  description = "The git commit both images are tagged with (python and web)."
  type        = string
}

variable "snowflake_account" {
  description = "SNOWFLAKE_ACCOUNT from .env (ORGNAME-ACCOUNTNAME)."
  type        = string
  sensitive   = true
}

variable "snowflake_private_key_passphrase" {
  description = "SNOWFLAKE_PRIVATE_KEY_FILE_PWD from .env: the passphrase of every private key below."
  type        = string
  sensitive   = true
}

variable "snowflake_private_keys" {
  description = "Encrypted private key text (the .p8 file) of each login the cluster runs: api, memory, sim, builder."
  type        = map(string)
  sensitive   = true

  validation {
    condition     = toset(keys(var.snowflake_private_keys)) == toset(["api", "memory", "sim", "builder"])
    error_message = "snowflake_private_keys must hold exactly api, memory, sim and builder."
  }
}

variable "twelve_data_api_key" {
  description = "TWELVE_DATA_API_KEY from .env, for dataset build jobs."
  type        = string
  sensitive   = true
}

variable "typesafe_api_key" {
  description = "TYPESAFE_API_KEY from .env (Jev), for sim jobs."
  type        = string
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "ANTHROPIC_API_KEY from .env (the LLM), for sim jobs."
  type        = string
  sensitive   = true
}
