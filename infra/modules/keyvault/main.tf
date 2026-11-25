data "azurerm_client_config" "current" {}

# Key Vault durci :
#  - autorisation RBAC (pas de politiques d'accès héritées, rôles auditables) ;
#  - accès réseau public désactivé : joignable uniquement via le point de terminaison privé ;
#  - suppression réversible + protection contre la purge (anti-destruction / rançongiciel) ;
#  - journal d'audit (AuditEvent) vers Log Analytics.
# Les VALEURS des secrets ne passent pas par Terraform : elles ne finissent ni dans le
# code, ni dans le plan, ni dans l'état. Voir docs/deploiement.md.
resource "azurerm_key_vault" "this" {
  name                          = var.name
  location                      = var.location
  resource_group_name           = var.resource_group_name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  enable_rbac_authorization     = true
  public_network_access_enabled = false
  purge_protection_enabled      = true
  soft_delete_retention_days    = 7

  network_acls {
    default_action = "Deny"
    bypass         = "AzureServices"
  }

  tags = var.tags
}

resource "azurerm_private_dns_zone" "kv" {
  name                = "privatelink.vaultcore.azure.net"
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "kv" {
  name                  = "link-kv"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.kv.name
  virtual_network_id    = var.vnet_id
  registration_enabled  = false
  tags                  = var.tags
}

resource "azurerm_private_endpoint" "kv" {
  name                = "pe-${var.name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoint_subnet_id

  private_service_connection {
    name                           = "psc-${var.name}"
    private_connection_resource_id = azurerm_key_vault.this.id
    subresource_names              = ["vault"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.kv.id]
  }

  tags = var.tags
}

# Moindre privilège : lecture des secrets uniquement, portée limitée à CE coffre.
resource "azurerm_role_assignment" "secret_reader" {
  for_each = var.secret_reader_principal_ids

  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = each.value
  principal_type       = "ServicePrincipal"
}

resource "azurerm_monitor_diagnostic_setting" "kv" {
  name                       = "diag-to-law"
  target_resource_id         = azurerm_key_vault.this.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category = "AuditEvent"
  }
  metric {
    category = "AllMetrics"
  }
}
