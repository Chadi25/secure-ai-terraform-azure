# Azure OpenAI optionnel, sans clé :
#  - local_auth_enabled = false : les clés d'API sont désactivées, seule
#    l'authentification Entra ID fonctionne (identité managée de l'app) ;
#  - accès public coupé, point de terminaison privé dans le VNet.
resource "azurerm_cognitive_account" "this" {
  name                          = var.name
  location                      = var.location
  resource_group_name           = var.resource_group_name
  kind                          = "OpenAI"
  sku_name                      = "S0"
  custom_subdomain_name         = var.name
  local_auth_enabled            = false
  public_network_access_enabled = false

  # Prévention de fuite de données (CKV_AZURE_247) : le service ne peut joindre
  # aucune destination sortante hors de la liste explicite (vide ici).
  outbound_network_access_restricted = true
  fqdns                              = []

  network_acls {
    default_action = "Deny"
  }

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}

resource "azurerm_cognitive_deployment" "chat" {
  name                 = var.model.name
  cognitive_account_id = azurerm_cognitive_account.this.id

  model {
    format  = "OpenAI"
    name    = var.model.name
    version = var.model.version
  }

  # azurerm 3.x : bloc "scale" (renommé "sku" en 4.x)
  scale {
    type     = "Standard"
    capacity = var.model.capacity
  }
}

resource "azurerm_role_assignment" "user" {
  for_each = var.user_principal_ids

  scope                = azurerm_cognitive_account.this.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = each.value
  principal_type       = "ServicePrincipal"
}

resource "azurerm_private_dns_zone" "oai" {
  name                = "privatelink.openai.azure.com"
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "oai" {
  name                  = "link-oai"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.oai.name
  virtual_network_id    = var.vnet_id
  registration_enabled  = false
  tags                  = var.tags
}

resource "azurerm_private_endpoint" "oai" {
  name                = "pe-${var.name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoint_subnet_id

  private_service_connection {
    name                           = "psc-${var.name}"
    private_connection_resource_id = azurerm_cognitive_account.this.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.oai.id]
  }

  tags = var.tags
}

resource "azurerm_monitor_diagnostic_setting" "oai" {
  name                       = "diag-to-law"
  target_resource_id         = azurerm_cognitive_account.this.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category = "Audit"
  }
  enabled_log {
    category = "RequestResponse"
  }
  metric {
    category = "AllMetrics"
  }
}
