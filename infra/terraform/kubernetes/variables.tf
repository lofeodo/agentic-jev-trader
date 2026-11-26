# Which cluster to deploy to, which images to run, and the secrets the services and jobs read.
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
  description = "The Snowflake database the memory server and the API serve."
  type        = string
  default     = "TRADING_AGENT"

  validation {
    condition     = contains(["TRADING_AGENT", "TRADING_AGENT_TEST"], var.database)
    error_message = "database must be TRADING_AGENT or TRADING_AGENT_TEST."
  }
}

variable "snowflake_keys_dir" {
  description = "The folder holding the encrypted private key of each login the cluster runs (api.p8, memory.p8, sim.p8, builder.p8): the keys folder in SNOWFLAKE_LOCAL_DIR."
  type        = string

  validation {
    condition = alltrue([
      for login in ["api", "memory", "sim", "builder"] :
      fileexists("${var.snowflake_keys_dir}/${login}.p8")
    ])
    error_message = "snowflake_keys_dir must hold api.p8, memory.p8, sim.p8 and builder.p8."
  }
}

variable "snowflake_account" {
  description = "SNOWFLAKE_ACCOUNT from .env (ORGNAME-ACCOUNTNAME)."
  type        = string
  sensitive   = true
  ephemeral   = true
}

variable "snowflake_private_key_passphrase" {
  description = "SNOWFLAKE_PRIVATE_KEY_FILE_PWD from .env: the passphrase of every private key."
  type        = string
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
