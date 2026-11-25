# Environnement Container Apps injecté dans le VNet (sous-réseau dédié) :
#  - internal_only = true  : équilibreur interne, aucune entrée publique ;
#  - internal_only = false : entrée publique HTTPS restreinte par liste blanche IP
#    (ip_security_restriction) + NSG du sous-réseau.
# Les journaux stdout/stderr partent dans Log Analytics.
resource "azurerm_container_app_environment" "this" {
  name                           = "cae-${var.name}"
  location                       = var.location
  resource_group_name            = var.resource_group_name
  log_analytics_workspace_id     = var.log_analytics_workspace_id
  infrastructure_subnet_id       = var.infrastructure_subnet_id
  internal_load_balancer_enabled = var.internal_only
  tags                           = var.tags
}

locals {
  # "app-api-key" -> variable d'environnement "APP_API_KEY"
  secret_env = { for s in var.secret_names : s => upper(replace(s, "-", "_")) }
}

resource "azurerm_container_app" "this" {
  name                         = "ca-${var.name}"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_id]
  }

  # Pull de l'image avec l'identité managée (rôle AcrPull), pas de mot de passe.
  registry {
    server   = var.acr_login_server
    identity = var.identity_id
  }

  # Références Key Vault : la plateforme lit le secret avec l'identité managée
  # (rôle Key Vault Secrets User). URI sans version = dernière version (rotation).
  dynamic "secret" {
    for_each = local.secret_env
    content {
      name                = secret.key
      key_vault_secret_id = "${var.key_vault_uri}secrets/${secret.key}"
      identity            = var.identity_id
    }
  }

  ingress {
    external_enabled           = true # « externe » à l'environnement ; l'environnement lui-même peut être interne
    target_port                = 8080
    transport                  = "auto"
    allow_insecure_connections = false # HTTPS uniquement

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }

    dynamic "ip_security_restriction" {
      for_each = var.allowed_ingress_cidrs
      content {
        name             = "allow-${ip_security_restriction.key}"
        action           = "Allow"
        ip_address_range = ip_security_restriction.value
      }
    }
  }

  template {
    min_replicas = 0 # aucun coût de calcul sans trafic
    max_replicas = 2

    container {
      name   = "ragapp"
      image  = var.image
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "AZURE_CLIENT_ID"
        value = var.identity_client_id
      }
      env {
        name  = "KEY_VAULT_URL"
        value = var.key_vault_uri
      }

      dynamic "env" {
        for_each = var.app_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.secret_env
        content {
          name        = env.value
          secret_name = env.key
        }
      }

      liveness_probe {
        transport = "HTTP"
        port      = 8080
        path      = "/healthz"
      }

      readiness_probe {
        transport = "HTTP"
        port      = 8080
        path      = "/readyz"
      }
    }
  }

  tags = var.tags
}
