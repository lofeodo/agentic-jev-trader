output "databases" {
  value = [for db in snowflake_database.this : db.name]
}

output "warehouse" {
  value = snowflake_warehouse.this.name
}

output "logins" {
  description = "Service user and role of each login."
  value = { for login, user in snowflake_service_user.login : login => {
    user = user.name
    role = snowflake_account_role.login[login].name
  } }
}
