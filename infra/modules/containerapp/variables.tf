variable "name" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "infrastructure_subnet_id" { type = string }
variable "log_analytics_workspace_id" { type = string }
variable "internal_only" { type = bool }
variable "allowed_ingress_cidrs" { type = list(string) }
variable "image" { type = string }
variable "identity_id" { type = string }
variable "identity_client_id" { type = string }
variable "acr_login_server" { type = string }
variable "key_vault_uri" { type = string }
variable "secret_names" {
  type = list(string)
  validation {
    condition     = alltrue([for s in var.secret_names : can(regex("^[a-z0-9-]{1,127}$", s))])
    error_message = "Noms de secrets : minuscules, chiffres et tirets."
  }
}
variable "app_env" {
  description = "Variables d'environnement NON sensibles."
  type        = map(string)
  default     = {}
}
variable "tags" { type = map(string) }
