locals {
  name = "${var.project}-${var.environment}"

  tags = merge({
    project     = var.project
    environment = var.environment
    owner       = var.owner
    managed_by  = "terraform"
    ephemeral   = "true" # à détruire après la démo
  }, var.tags)
}

# Suffixe pour les noms globalement uniques (Key Vault, ACR, Azure OpenAI).
resource "random_string" "suffix" {
  length  = 5
  upper   = false
  special = false
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.name}"
  location = var.location
  tags     = local.tags
}

module "monitoring" {
  source = "./modules/monitoring"

  name                  = local.name
  location              = var.location
  resource_group_name   = azurerm_resource_group.this.name
  resource_group_id     = azurerm_resource_group.this.id
  retention_days        = var.log_retention_days
  budget_amount         = var.budget_amount
  budget_start_date     = var.budget_start_date
  budget_contact_emails = var.budget_contact_emails
  tags                  = local.tags
}

module "network" {
  source = "./modules/network"

  name                       = local.name
  location                   = var.location
  resource_group_name        = azurerm_resource_group.this.name
  vnet_cidr                  = var.vnet_cidr
  allowed_ingress_cidrs      = var.allowed_ingress_cidrs
  log_analytics_workspace_id = module.monitoring.workspace_id
  tags                       = local.tags
}

module "identity" {
  source = "./modules/identity"

  name                = local.name
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

module "keyvault" {
  source = "./modules/keyvault"

  name                       = "kv-${var.project}-${random_string.suffix.result}"
  location                   = var.location
  resource_group_name        = azurerm_resource_group.this.name
  vnet_id                    = module.network.vnet_id
  private_endpoint_subnet_id = module.network.private_endpoint_subnet_id
  log_analytics_workspace_id = module.monitoring.workspace_id
  # Seule l'identité de l'application lit les secrets (rôle « Key Vault Secrets User »).
  secret_reader_principal_ids = { app = module.identity.principal_id }
  tags                        = local.tags
}

module "acr" {
  source = "./modules/acr"

  name                       = "acr${var.project}${random_string.suffix.result}"
  location                   = var.location
  resource_group_name        = azurerm_resource_group.this.name
  sku                        = var.acr_sku
  vnet_id                    = module.network.vnet_id
  private_endpoint_subnet_id = module.network.private_endpoint_subnet_id
  log_analytics_workspace_id = module.monitoring.workspace_id
  pull_principal_ids         = { app = module.identity.principal_id }
  tags                       = local.tags
}

module "openai" {
  source = "./modules/openai"
  count  = var.enable_azure_openai ? 1 : 0

  name                       = "oai-${var.project}-${random_string.suffix.result}"
  location                   = var.location
  resource_group_name        = azurerm_resource_group.this.name
  vnet_id                    = module.network.vnet_id
  private_endpoint_subnet_id = module.network.private_endpoint_subnet_id
  log_analytics_workspace_id = module.monitoring.workspace_id
  model                      = var.openai_model
  user_principal_ids         = { app = module.identity.principal_id }
  tags                       = local.tags
}

module "containerapp" {
  source = "./modules/containerapp"

  name                       = local.name
  location                   = var.location
  resource_group_name        = azurerm_resource_group.this.name
  infrastructure_subnet_id   = module.network.app_subnet_id
  log_analytics_workspace_id = module.monitoring.workspace_id
  internal_only              = var.internal_only
  allowed_ingress_cidrs      = var.allowed_ingress_cidrs
  image                      = var.container_image
  identity_id                = module.identity.id
  identity_client_id         = module.identity.client_id
  acr_login_server           = module.acr.login_server
  key_vault_uri              = module.keyvault.vault_uri
  secret_names               = var.app_secret_names

  app_env = var.enable_azure_openai ? {
    LLM_PROVIDER            = "azure_openai"
    AZURE_OPENAI_ENDPOINT   = module.openai[0].endpoint
    AZURE_OPENAI_DEPLOYMENT = module.openai[0].deployment_name
  } : { LLM_PROVIDER = "none" }

  tags = local.tags

  # Les rôles doivent exister avant que la plateforme tire l'image / lise les secrets.
  depends_on = [module.acr, module.keyvault]
}
