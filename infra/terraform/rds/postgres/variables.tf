# Every value is passed by infra/rds.py: the address from the AWS root's output, the passwords
# from .env as TF_VAR_* variables.

variable "host" {
  description = "The database's address (the AWS root's `address` output)."
  type        = string
}

variable "admin_user" {
  description = "The admin login made with the database (the AWS root's `admin_user` output)."
  type        = string
}

variable "admin_password" {
  description = "POSTGRES_ADMIN_PASSWORD."
  type        = string
  sensitive   = true
  ephemeral   = true
}

variable "passwords" {
  description = "Each login's password, POSTGRES_<LOGIN>_PASSWORD, by login. Sent write-only: the state never holds them."
  type        = map(string)
  sensitive   = true
  ephemeral   = true
}

variable "passwords_version" {
  description = "Raise by one after changing a login's password in .env, or Terraform does not send it."
  type        = number
  default     = 1
}
