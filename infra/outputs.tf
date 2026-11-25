output "resource_group" {
  value = azurerm_resource_group.this.name
}

output "app_url" {
  description = "URL HTTPS de l'application (privée si internal_only = true)."
  value       = module.containerapp.url
}

output "acr_login_server" {
  value = module.acr.login_server
}

output "key_vault_name" {
  value = module.keyvault.name
}

output "key_vault_uri" {
  value = module.keyvault.vault_uri
}

output "app_identity_client_id" {
  value = module.identity.client_id
}

output "log_analytics_workspace_id" {
  value = module.monitoring.workspace_id
}
