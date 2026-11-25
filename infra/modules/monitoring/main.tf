# Journalisation centralisée : un seul espace Log Analytics reçoit les journaux de
# l'application (via l'environnement Container Apps) et les journaux d'audit
# (Key Vault, ACR, NSG). Rétention courte pour la démo.
resource "azurerm_log_analytics_workspace" "this" {
  name                = "log-${var.name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = var.retention_days
  # Plafond d'ingestion quotidien : garde-fou de coût (Go/jour).
  daily_quota_gb = 1
  tags           = var.tags
}

# Garde-fou financier : alertes à 50 %, 80 % (réel) et 100 % (prévisionnel).
resource "azurerm_consumption_budget_resource_group" "this" {
  name              = "budget-${var.name}"
  resource_group_id = var.resource_group_id
  amount            = var.budget_amount
  time_grain        = "Monthly"

  time_period {
    start_date = var.budget_start_date
  }

  notification {
    enabled        = true
    threshold      = 50
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = var.budget_contact_emails
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = var.budget_contact_emails
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Forecasted"
    contact_emails = var.budget_contact_emails
  }

  lifecycle {
    # Azure peut normaliser la date ; évite un diff perpétuel.
    ignore_changes = [time_period]
  }
}
