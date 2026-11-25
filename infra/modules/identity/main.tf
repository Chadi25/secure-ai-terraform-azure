# Identité managée attribuée par l'utilisateur (user-assigned) plutôt que system-assigned :
# elle existe avant l'application, ce qui permet d'attribuer les rôles (AcrPull,
# Key Vault Secrets User) AVANT le premier démarrage, et survit au recréation de l'app.
# Aucun secret client n'existe pour cette identité.
resource "azurerm_user_assigned_identity" "this" {
  name                = "id-${var.name}-app"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags
}
