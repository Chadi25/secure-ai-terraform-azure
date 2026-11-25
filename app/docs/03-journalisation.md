# Journalisation et supervision

Les journaux applicatifs sont émis en JSON sur la sortie standard et collectés par l'environnement Container Apps dans un espace de travail Log Analytics. Ils contiennent l'identifiant de requête, le chemin, le code de statut et la durée, mais jamais le contenu des questions ni les secrets.

Les journaux d'audit du Key Vault (catégorie AuditEvent) et du registre de conteneurs sont envoyés au même espace de travail par des paramètres de diagnostic. On peut ainsi détecter une lecture de secret inhabituelle avec une requête KQL.

La rétention est fixée à 30 jours pour maîtriser le coût de la démonstration.
