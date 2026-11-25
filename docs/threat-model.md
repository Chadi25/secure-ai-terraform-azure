# Modèle de menace (STRIDE, version courte)

Périmètre : l'application RAG, son infrastructure Azure et la chaîne CI/CD. Actifs : secrets (clé d'API, éventuelle clé LLM tierce), corpus documentaire, état Terraform, image de conteneur, budget.

| STRIDE | Menace | Mesures en place | Risque résiduel / piste |
|---|---|---|---|
| **S**poofing | Usurpation d'identité de l'app ou du pipeline auprès d'Azure | Identité managée (aucun secret client) ; OIDC GitHub limité au dépôt / à la branche via le *subject* de la fédération | Bien restreindre le *subject* OIDC (`repo:org/repo:environment:demo`) |
| **S** | Appelant non autorisé sur l'API | Liste blanche IP (ingress + NSG), clé d'API optionnelle comparée en temps constant | Pas d'authentification utilisateur forte → Entra ID *Easy Auth* en évolution |
| **T**ampering | Image modifiée ou malveillante | Build en CI, scan Trivy, pull uniquement via identité ; admin ACR désactivé | Pas de signature d'image (Notation / content trust nécessite Premium) |
| **T** | Modification de l'infra hors processus | Apply uniquement sur `main` après approbation (environnement GitHub protégé) ; Checkov + règles maison bloquants | Pas de détection de dérive planifiée → `terraform plan` nocturne |
| **R**epudiation | Lecture de secret sans trace | Journal `AuditEvent` du Key Vault, journaux ACR et NSG dans Log Analytics ; journaux applicatifs avec identifiant de requête | Rétention 30 j (démo) ; pas d'alerte KQL fournie |
| **I**nformation disclosure | Fuite de secret via le code, l'image ou l'état | Secrets déposés hors Terraform, lus à l'exécution ; `.gitignore` des tfvars ; détection de motifs de secrets (policy_check) | Le compte de stockage de l'état doit lui-même être privé et chiffré |
| **I** | Exfiltration via injection de prompt (le contexte documentaire contient des consignes) | Prompt système qui traite le contexte comme donnée, contexte balisé, réponse limitée aux sources | Atténuation, pas une garantie : filtrage de sortie et tests adverses à ajouter (OWASP LLM01) |
| **I** | Accès direct au Key Vault / OpenAI depuis Internet | Accès public désactivé, points de terminaison privés, NSG du sous-réseau PE | — |
| **D**enial of service | Saturation de l'API / explosion de la facture | Taille de requête et de question bornées, `max_replicas = 2`, budget avec alertes, quota d'ingestion Log Analytics | Pas de limitation de débit par client → API Management / Front Door WAF |
| **E**levation of privilege | Identité de l'app trop puissante | Rôles minimaux, portée limitée à chaque ressource (pas au groupe de ressources) | L'identité CI a des droits larges (Contributor + User Access Administrator) : à scinder plan / apply |
| **E** | Évasion du conteneur | Utilisateur non-root (UID 10001), image slim, pas de shell de connexion | Système de fichiers en lecture seule non imposé par Container Apps |
