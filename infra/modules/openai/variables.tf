variable "name" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "vnet_id" { type = string }
variable "private_endpoint_subnet_id" { type = string }
variable "log_analytics_workspace_id" { type = string }
variable "model" {
  type = object({
    name     = string
    version  = string
    capacity = number
  })
}
variable "user_principal_ids" { type = map(string) }
variable "tags" { type = map(string) }
