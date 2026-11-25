variable "name" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "sku" {
  type = string
  validation {
    condition     = contains(["Basic", "Standard", "Premium"], var.sku)
    error_message = "Basic, Standard ou Premium."
  }
}
variable "vnet_id" { type = string }
variable "private_endpoint_subnet_id" { type = string }
variable "log_analytics_workspace_id" { type = string }
variable "pull_principal_ids" { type = map(string) }
variable "tags" { type = map(string) }
