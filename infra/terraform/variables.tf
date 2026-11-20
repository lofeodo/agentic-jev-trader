# Every value is passed by infra/snowflake_admin.py from .env, as TF_VAR_* variables.

variable "organization_name" {
  description = "First half of SNOWFLAKE_ACCOUNT (ORGNAME-ACCOUNTNAME)."
  type        = string
}

variable "account_name" {
  description = "Second half of SNOWFLAKE_ACCOUNT (ORGNAME-ACCOUNTNAME)."
  type        = string
}

variable "admin_user" {
  description = "The service user Terraform logs in as. Made by hand once, holds ACCOUNTADMIN (infra/README.md)."
  type        = string
}

variable "admin_private_key_path" {
  description = "Encrypted private key of the admin user, outside the repo."
  type        = string
}

variable "private_key_passphrase" {
  description = "Passphrase of the encrypted private keys."
  type        = string
  sensitive   = true
}

variable "public_keys_dir" {
  description = "Folder holding <login>.pub for each of the five service logins."
  type        = string
}

variable "embedding_grant_method" {
  description = <<-EOT
    How the dataset builder's role gets the embedding model:
    "application_role" (snowflake_grant_application_role, preferred) or
    "execute" (snowflake_execute running GRANT APPLICATION ROLE, the fallback if the first fails).
  EOT
  type        = string
  default     = "application_role"

  validation {
    condition     = contains(["application_role", "execute"], var.embedding_grant_method)
    error_message = "embedding_grant_method must be \"application_role\" or \"execute\"."
  }
}
