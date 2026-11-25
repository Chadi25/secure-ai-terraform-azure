# Principes Zero Trust appliqués au déploiement

Le modèle Zero Trust part du principe qu'aucun réseau n'est digne de confiance par défaut. Chaque accès est authentifié, autorisé et journalisé, quelle que soit sa provenance.

Dans ce déploiement, l'application n'utilise aucun mot de passe ni secret client pour parler aux services Azure : elle s'authentifie avec une identité managée attribuée par l'utilisateur. Les droits sont limités au strict nécessaire (moindre privilège) : lecture des secrets Key Vault et récupération des images du registre.

Le coffre Key Vault n'est joignable que par un point de terminaison privé dans le réseau virtuel. L'accès réseau public est désactivé et la protection contre la purge empêche la suppression définitive des secrets pendant la période de rétention.
