# Every value is passed by infra/rds.py: the secret ones from .env as TF_VAR_* variables.

variable "admin_password" {
  description = "Password of the database's admin login (POSTGRES_ADMIN_PASSWORD). Sent write-only: the state never holds it."
  type        = string
  sensitive   = true
  ephemeral   = true
}

variable "admin_password_version" {
  description = "Raise by one after changing POSTGRES_ADMIN_PASSWORD, or Terraform does not send the new one."
  type        = number
  default     = 1
}

variable "budget_email" {
  description = "Where the budget alarm writes (AWS_BUDGET_EMAIL)."
  type        = string
}

variable "parked" {
  description = "True while the database is deleted and kept as a snapshot (infra/rds.py snapshot-and-delete): no database is made."
  type        = bool
  default     = false
}

variable "restore_from" {
  description = "The snapshot a new database starts from (infra/rds.py restore). Null: an empty database."
  type        = string
  default     = null
}
