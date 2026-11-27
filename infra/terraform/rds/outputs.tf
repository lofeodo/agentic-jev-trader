output "address" {
  description = "The database's address, for POSTGRES_HOST in .env. Null while parked."
  value       = one(aws_db_instance.database[*].address)
}

output "home_ip" {
  description = "The one internet address the network rule lets in."
  value       = local.home_ip
}
