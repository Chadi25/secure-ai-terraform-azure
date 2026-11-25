locals {
  premium = var.sku == "Premium"
}

# Registre de conteneurs :
#  - compte admin désactivé (pas de login/mot de passe partagé) ; les pulls se font
#    avec l'identité managée (rôle AcrPull), les pushs CI via OIDC (rôle AcrPush) ;
#  - pull anonyme désactivé ;
#  - en Premium : accès public coupé + point de terminaison privé. En Basic (démo à
#    coût réduit), l'accès public reste ouvert mais authentifié Entra ID uniquement :
#    écart assumé et documenté dans .checkov.yaml.
resource "azurerm_container_registry" "this" {
  name                          = var.name
  location                      = var.location
  resource_group_name           = var.resource_group_name
  sku                           = var.sku
  admin_enabled                 = false
  anonymous_pull_enabled        = false
  public_network_access_enabled = local.premium ? false : true
  tags                          = var.tags
}

resource "azurerm_role_assignment" "pull" {
  for_each = var.pull_principal_ids

  scope                = azurerm_container_registry.this.id
  role_definition_name = "AcrPull"
  principal_id         = each.value
  principal_type       = "ServicePrincipal"
}

resource "azurerm_private_dns_zone" "acr" {
  count               = local.premium ? 1 : 0
  name                = "privatelink.azurecr.io"
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "acr" {
  count                 = local.premium ? 1 : 0
  name                  = "link-acr"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.acr[0].name
  virtual_network_id    = var.vnet_id
  registration_enabled  = false
  tags                  = var.tags
}

resource "azurerm_private_endpoint" "acr" {
  count               = local.premium ? 1 : 0
  name                = "pe-${var.name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoint_subnet_id

  private_service_connection {
    name                           = "psc-${var.name}"
    private_connection_resource_id = azurerm_container_registry.this.id
    subresource_names              = ["registry"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.acr[0].id]
  }

  tags = var.tags
}

resource "azurerm_monitor_diagnostic_setting" "acr" {
  name                       = "diag-to-law"
  target_resource_id         = azurerm_container_registry.this.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category = "ContainerRegistryLoginEvents"
  }
  enabled_log {
    category = "ContainerRegistryRepositoryEvents"
  }
  metric {
    category = "AllMetrics"
  }
}
