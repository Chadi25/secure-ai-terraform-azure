terraform {
  required_version = ">= 1.6.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.116"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # État distant : un compte de stockage dédié, accès Entra ID uniquement (pas de clé
  # de compte), verrouillage natif par bail blob. L'état ne contient AUCUN secret
  # applicatif (les secrets sont déposés dans Key Vault hors Terraform), mais il
  # contient la topologie : il reste un actif sensible.
  #
  # backend "azurerm" {
  #   resource_group_name  = "rg-tfstate"
  #   storage_account_name = "sttfstatechadi"
  #   container_name       = "tfstate"
  #   key                  = "secure-ai/demo.tfstate"
  #   use_azuread_auth     = true
  #   use_oidc             = true
  # }
}

provider "azurerm" {
  # Authentification : en CI via OIDC fédéré GitHub -> Entra ID (ARM_USE_OIDC=true,
  # ARM_CLIENT_ID, ARM_TENANT_ID, ARM_SUBSCRIPTION_ID). Aucun secret client.
  # En local : `az login`.
  storage_use_azuread = true

  features {
    key_vault {
      # On ne purge jamais un coffre en destroy : la protection contre la purge
      # l'interdirait de toute façon, et c'est le comportement souhaité.
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}
