variable "project" {
  description = "Préfixe court des noms de ressources (minuscules, chiffres)."
  type        = string
  default     = "secai"

  validation {
    condition     = can(regex("^[a-z0-9]{3,10}$", var.project))
    error_message = "3 à 10 caractères minuscules ou chiffres."
  }
}

variable "environment" {
  description = "Nom d'environnement (demo, dev...)."
  type        = string
  default     = "demo"
}

variable "location" {
  description = "Région Azure. France Central pour la localisation des données."
  type        = string
  default     = "francecentral"
}

variable "owner" {
  description = "Propriétaire, reporté dans les tags."
  type        = string
}

variable "tags" {
  description = "Tags supplémentaires."
  type        = map(string)
  default     = {}
}

variable "vnet_cidr" {
  description = "Plage du réseau virtuel."
  type        = string
  default     = "10.20.0.0/16"
}

variable "allowed_ingress_cidrs" {
  description = "Plages IP publiques autorisées à joindre l'application (liste blanche). Jamais 0.0.0.0/0."
  type        = list(string)

  validation {
    condition     = length(var.allowed_ingress_cidrs) > 0 && !contains(var.allowed_ingress_cidrs, "0.0.0.0/0")
    error_message = "Fournir au moins une plage, et pas 0.0.0.0/0."
  }
}

variable "internal_only" {
  description = "true = application joignable uniquement depuis le VNet (pas d'IP publique d'entrée)."
  type        = bool
  default     = false
}

variable "container_image" {
  description = "Image de l'application dans l'ACR, ex. acrsecaixxxxx.azurecr.io/ragapp:0.1.0 (voir docs/deploiement.md, amorçage)."
  type        = string
}

variable "app_secret_names" {
  description = "Secrets Key Vault (déposés hors Terraform) à injecter dans l'application, ex. [\"app-api-key\"]."
  type        = list(string)
  default     = []
}

variable "acr_sku" {
  description = "SKU du registre. Premium requis pour un point de terminaison privé."
  type        = string
  default     = "Basic"
}

variable "enable_azure_openai" {
  description = "Déployer un compte Azure OpenAI privé (authentification Entra ID uniquement)."
  type        = bool
  default     = false
}

variable "openai_model" {
  description = "Modèle Azure OpenAI à déployer."
  type = object({
    name     = string
    version  = string
    capacity = number
  })
  default = {
    name     = "gpt-4o-mini"
    version  = "2024-07-18"
    capacity = 10
  }
}

variable "log_retention_days" {
  description = "Rétention Log Analytics (jours)."
  type        = number
  default     = 30
}

variable "budget_amount" {
  description = "Budget mensuel du groupe de ressources (devise de l'abonnement)."
  type        = number
  default     = 20
}

variable "budget_start_date" {
  description = "Début du budget, premier jour d'un mois, format RFC3339."
  type        = string
  default     = "2026-12-01T00:00:00Z"
}

variable "budget_contact_emails" {
  description = "Destinataires des alertes de budget."
  type        = list(string)
}
