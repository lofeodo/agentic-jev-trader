output "namespace" {
  description = "Where the services, the secrets and the jobs live."
  value       = kubernetes_namespace_v1.this.metadata[0].name
}

output "on_this_computer" {
  description = "Where this computer reaches the web app and the API (127.0.0.1 only)."
  value       = { for name, opened in local.this_computer : name => opened.address }
}
