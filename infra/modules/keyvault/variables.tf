variable "name" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "vnet_id" { type = string }
variable "private_endpoint_subnet_id" { type = string }
variable "log_analytics_workspace_id" { type = string }
variable "secret_reader_principal_ids" {
  description = "Map clé statique -> object id des principaux autorisés à lire les secrets."
  type        = map(string)
}
variable "tags" { type = map(string) }
