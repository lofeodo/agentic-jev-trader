# The project's Kubernetes part: the three long-lived services (the memory server, the API and
# the web app) in a local kind cluster, the secrets they and the jobs read, and the permission
# for the API to start and stop Jobs. Spec: issue #82, appendix 10 section 3.
# Kept apart from the Snowflake part in infra/terraform, which it does not touch.
#
# Skeleton: no resources yet. They arrive with the slice's Terraform ticket (#199).

provider "kubernetes" {
  config_path    = var.kubeconfig_path
  config_context = var.kube_context
}
