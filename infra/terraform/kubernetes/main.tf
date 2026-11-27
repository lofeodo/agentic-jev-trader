# The project's Kubernetes part: the three long-lived services (the memory server, the API and
# the web app) in a local kind cluster, the secrets they and the jobs read, and the permission
# for the API to start and stop Jobs. Spec: issue #82, appendix 10 section 3.
# Kept apart from the RDS part in infra/terraform/rds, which it does not touch.
#
# The programs log in to Postgres on AWS RDS (spec appendix 11, section 1): the address and the
# connection settings in the ConfigMap `postgres`, each login's password in its own secret.
#
# Everything sits in one namespace. The memory server is reached inside the cluster only, as
# `memory`; the API (`api`) and the web app (`web`) are also opened to this computer, on
# 127.0.0.1 only, through the ports infra/kind-cluster.yaml maps (local.this_computer).

provider "kubernetes" {
  config_path    = var.kubeconfig_path
  config_context = var.kube_context
}

locals {
  namespace = "jev-trader"

  # Both images are loaded into kind by infra/images.py, never downloaded: the cluster must
  # not try a registry.
  python_image = "jev-trader:${var.image_tag}"
  web_image    = "jev-trader-web:${var.image_tag}"

  # The Python image's plain user (Dockerfile).
  python_user = 10001

  # The cluster's node ports for the API and the web app, and the ports on this computer kind
  # maps them to. These must match infra/kind-cluster.yaml.
  this_computer = {
    api = { node_port = 30081, address = "http://127.0.0.1:8081" }
    web = { node_port = 30080, address = "http://127.0.0.1:8080" }
  }

  # The two Python services. Each logs in to Postgres as its own login and gets that login's
  # secret only.
  python_services = {
    memory = {
      port    = 8765
      command = ["python", "-m", "jev_trader.memory", "serve", "--in-cluster", "--database", var.database]
      env     = {}
    }
    api = {
      port    = 8000
      command = ["python", "-m", "jev_trader.api", "serve", "--in-cluster", "--database", var.database]
      # Sims and dataset builds start as Jobs in this cluster, from the API's own image. Each
      # Job reads the ConfigMap postgres, its own login's secret (postgres-sim or
      # postgres-builder) and models or twelve-data, named in src/jev_trader/jobs.py.
      env = { JOB_LAUNCHER = "kubernetes", JOB_IMAGE = local.python_image }
    }
  }

  # The logins that run in the cluster: the two services and the two kinds of Job. The setup
  # login (it makes the tables) stays on the developer's computer.
  logins = toset(["api", "memory", "sim", "builder"])
}

resource "kubernetes_namespace_v1" "this" {
  metadata {
    name = local.namespace
  }
}

# --- Where the database is, and the secrets ---------------------------------------------------
# The ConfigMap `postgres` holds what every program needs to find the database and is no
# secret: the address, the port and the encryption. One secret per login (the
# services' memory and api, the jobs' sim and builder) holds that login's password only. The sim
# jobs' model keys and the build jobs' price-data key are secrets of their own. The ZAI key
# (only the benchmark uses it, on the developer's machine) and the LangSmith key (tracing,
# optional) do not enter the cluster.

resource "kubernetes_config_map_v1" "postgres" {
  metadata {
    name      = "postgres"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  data = {
    POSTGRES_HOST     = var.postgres_host
    POSTGRES_PORT     = tostring(var.postgres_port)
    POSTGRES_SSL_MODE = var.postgres_ssl_mode
  }
}

resource "kubernetes_secret_v1" "postgres" {
  for_each = local.logins

  metadata {
    name      = "postgres-${each.key}"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  # The name the programs read it by (jev_trader.storage.postgres.password_variable).
  data_wo = {
    "POSTGRES_${upper(each.key)}_PASSWORD" = var.postgres_passwords[each.key]
  }
  data_wo_revision = var.secrets_revision
}

resource "kubernetes_secret_v1" "models" {
  metadata {
    name      = "models"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  data_wo = {
    TYPESAFE_API_KEY  = var.typesafe_api_key
    ANTHROPIC_API_KEY = var.anthropic_api_key
  }
  data_wo_revision = var.secrets_revision
}

resource "kubernetes_secret_v1" "twelve_data" {
  metadata {
    name      = "twelve-data"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  data_wo = {
    TWELVE_DATA_API_KEY = var.twelve_data_api_key
  }
  data_wo_revision = var.secrets_revision
}

# --- The API's permission to start and stop Jobs ----------------------------------------------
# A Role, not a ClusterRole: it holds in this namespace only. ConfigMaps carry a dataset
# build's settings file to its Job.

resource "kubernetes_service_account_v1" "api" {
  metadata {
    name      = "api"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }
}

resource "kubernetes_role_v1" "jobs" {
  metadata {
    name      = "start-and-stop-jobs"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  rule {
    api_groups = ["batch"]
    resources  = ["jobs"]
    verbs      = ["create", "get", "list", "watch", "delete"]
  }

  rule {
    api_groups = ["batch"]
    resources  = ["jobs/status"]
    verbs      = ["get"]
  }

  rule {
    api_groups = [""]
    resources  = ["configmaps"]
    verbs      = ["create", "get", "delete"]
  }
}

resource "kubernetes_role_binding_v1" "api_jobs" {
  metadata {
    name      = "api-starts-and-stops-jobs"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = kubernetes_role_v1.jobs.metadata[0].name
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account_v1.api.metadata[0].name
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }
}

# --- The memory server and the API ------------------------------------------------------------
# Terraform waits until each is ready (its health address answers), so an apply that ends well
# means all three services are up.

resource "kubernetes_deployment_v1" "python" {
  for_each = local.python_services

  metadata {
    name      = each.key
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels    = { app = each.key }
  }

  spec {
    replicas = 1

    selector {
      match_labels = { app = each.key }
    }

    template {
      metadata {
        labels = { app = each.key }
      }

      spec {
        # Only the API talks to the cluster itself, to start and stop Jobs.
        service_account_name            = each.key == "api" ? kubernetes_service_account_v1.api.metadata[0].name : null
        automount_service_account_token = each.key == "api"

        security_context {
          run_as_non_root = true
          run_as_user     = local.python_user
        }

        container {
          name              = each.key
          image             = local.python_image
          image_pull_policy = "Never"
          command           = each.value.command

          port {
            container_port = each.value.port
          }

          env_from {
            config_map_ref {
              name = kubernetes_config_map_v1.postgres.metadata[0].name
            }
          }

          env_from {
            secret_ref {
              name = kubernetes_secret_v1.postgres[each.key].metadata[0].name
            }
          }

          dynamic "env" {
            for_each = each.value.env
            content {
              name  = env.key
              value = env.value
            }
          }

          # Asked under the service's own name and port: each server refuses an address name
          # it does not know, and the probe would otherwise give the pod's address.
          readiness_probe {
            http_get {
              path = "/health"
              port = each.value.port
              http_header {
                name  = "Host"
                value = "${each.key}:${each.value.port}"
              }
            }
            period_seconds = 5
          }
        }
      }
    }
  }

  depends_on = [kubernetes_role_binding_v1.api_jobs]
}

resource "kubernetes_service_v1" "memory" {
  metadata {
    name      = "memory"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  spec {
    selector = { app = "memory" }
    port {
      port        = local.python_services.memory.port
      target_port = local.python_services.memory.port
    }
  }
}

resource "kubernetes_service_v1" "api" {
  metadata {
    name      = "api"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  spec {
    type     = "NodePort"
    selector = { app = "api" }
    port {
      port        = local.python_services.api.port
      target_port = local.python_services.api.port
      node_port   = local.this_computer.api.node_port
    }
  }
}

# --- The web app ------------------------------------------------------------------------------

resource "kubernetes_deployment_v1" "web" {
  metadata {
    name      = "web"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels    = { app = "web" }
  }

  spec {
    replicas = 1

    selector {
      match_labels = { app = "web" }
    }

    template {
      metadata {
        labels = { app = "web" }
      }

      spec {
        automount_service_account_token = false

        container {
          name              = "web"
          image             = local.web_image
          image_pull_policy = "Never"

          port {
            container_port = 80
          }

          readiness_probe {
            http_get {
              path = "/"
              port = 80
            }
            period_seconds = 5
          }
        }
      }
    }
  }

  # The web app's server looks the API's name up once, when it starts: the name must exist.
  depends_on = [kubernetes_service_v1.api]
}

resource "kubernetes_service_v1" "web" {
  metadata {
    name      = "web"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  spec {
    type     = "NodePort"
    selector = { app = "web" }
    port {
      port        = 80
      target_port = 80
      node_port   = local.this_computer.web.node_port
    }
  }
}
