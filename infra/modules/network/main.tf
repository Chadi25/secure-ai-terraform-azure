# Réseau : un VNet, deux sous-réseaux.
#  - snet-app : infrastructure de l'environnement Container Apps (/23 requis en mode consommation)
#  - snet-pe  : points de terminaison privés (Key Vault, ACR Premium, Azure OpenAI)
# Chaque sous-réseau a son NSG. Les règles par défaut d'Azure autorisent le trafic
# intra-VNet ; on interdit explicitement Internet en entrée et on n'ouvre que le
# strict nécessaire (liste blanche HTTPS vers l'app, 443 app -> PE).

resource "azurerm_virtual_network" "this" {
  name                = "vnet-${var.name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = [var.vnet_cidr]
  tags                = var.tags
}

resource "azurerm_subnet" "app" {
  name                 = "snet-app"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [cidrsubnet(var.vnet_cidr, 7, 0)] # /23
}

resource "azurerm_subnet" "pe" {
  name                 = "snet-pe"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [cidrsubnet(var.vnet_cidr, 11, 16)] # /27
  # Active l'application des NSG sur les points de terminaison privés.
  private_endpoint_network_policies = "Enabled"
}

# ---------- NSG du sous-réseau applicatif ----------
resource "azurerm_network_security_group" "app" {
  name                = "nsg-${var.name}-app"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_network_security_rule" "app_https_allowlist" {
  name                        = "Allow-HTTPS-Allowlist"
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefixes     = var.allowed_ingress_cidrs # jamais 0.0.0.0/0 (validé en amont)
  destination_address_prefix  = "VirtualNetwork"
  resource_group_name         = var.resource_group_name
  network_security_group_name = azurerm_network_security_group.app.name
}

resource "azurerm_network_security_rule" "app_lb_probe" {
  name                        = "Allow-AzureLoadBalancer"
  priority                    = 110
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "*"
  source_port_range           = "*"
  destination_port_range      = "*"
  source_address_prefix       = "AzureLoadBalancer" # sondes de santé de la plateforme
  destination_address_prefix  = "VirtualNetwork"
  resource_group_name         = var.resource_group_name
  network_security_group_name = azurerm_network_security_group.app.name
}

resource "azurerm_network_security_rule" "app_deny_internet" {
  name                        = "Deny-Internet-Inbound"
  priority                    = 4000
  direction                   = "Inbound"
  access                      = "Deny"
  protocol                    = "*"
  source_port_range           = "*"
  destination_port_range      = "*"
  source_address_prefix       = "Internet"
  destination_address_prefix  = "*"
  resource_group_name         = var.resource_group_name
  network_security_group_name = azurerm_network_security_group.app.name
}

resource "azurerm_subnet_network_security_group_association" "app" {
  subnet_id                 = azurerm_subnet.app.id
  network_security_group_id = azurerm_network_security_group.app.id
}

# ---------- NSG du sous-réseau des points de terminaison privés ----------
resource "azurerm_network_security_group" "pe" {
  name                = "nsg-${var.name}-pe"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_network_security_rule" "pe_from_app" {
  name                         = "Allow-App-To-PE-443"
  priority                     = 100
  direction                    = "Inbound"
  access                       = "Allow"
  protocol                     = "Tcp"
  source_port_range            = "*"
  destination_port_range       = "443"
  source_address_prefixes      = azurerm_subnet.app.address_prefixes
  destination_address_prefixes = azurerm_subnet.pe.address_prefixes
  resource_group_name          = var.resource_group_name
  network_security_group_name  = azurerm_network_security_group.pe.name
}

resource "azurerm_network_security_rule" "pe_deny_all" {
  name                        = "Deny-All-Inbound"
  priority                    = 4096
  direction                   = "Inbound"
  access                      = "Deny"
  protocol                    = "*"
  source_port_range           = "*"
  destination_port_range      = "*"
  source_address_prefix       = "*"
  destination_address_prefix  = "*"
  resource_group_name         = var.resource_group_name
  network_security_group_name = azurerm_network_security_group.pe.name
}

resource "azurerm_subnet_network_security_group_association" "pe" {
  subnet_id                 = azurerm_subnet.pe.id
  network_security_group_id = azurerm_network_security_group.pe.id
}

# Journaux des NSG vers Log Analytics.
resource "azurerm_monitor_diagnostic_setting" "nsg" {
  for_each = {
    app = azurerm_network_security_group.app.id
    pe  = azurerm_network_security_group.pe.id
  }

  name                       = "diag-to-law"
  target_resource_id         = each.value
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category = "NetworkSecurityGroupEvent"
  }
  enabled_log {
    category = "NetworkSecurityGroupRuleCounter"
  }
}
