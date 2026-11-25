# Gestion des secrets

Aucun secret n'est stocké dans le code, l'image Docker, les variables Terraform ou l'état Terraform. Les valeurs sensibles (clé d'API applicative, clé d'un fournisseur LLM tiers) sont déposées dans Key Vault hors Terraform, puis référencées par Azure Container Apps.

La plateforme résout la référence Key Vault au démarrage du conteneur grâce à l'identité managée et l'expose comme variable d'environnement. La rotation d'un secret ne demande donc pas de reconstruire l'image.

Pour Azure OpenAI, la méthode recommandée est l'authentification Entra ID avec le rôle Cognitive Services OpenAI User attribué à l'identité managée : aucune clé n'est alors nécessaire.
