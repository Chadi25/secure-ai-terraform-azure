# secure-ai-terraform-azure

> **EN — summary.** A small RAG API (Python, numpy TF-IDF, optional Azure OpenAI) and the Terraform code to deploy it on Azure under security-first defaults: VNet-integrated Container Apps with IP-allowlisted HTTPS ingress, private Key Vault (RBAC, purge protection, public access off) referenced through a user-assigned managed identity, admin-less ACR, keyless Azure OpenAI over private endpoint, centralised logging in Log Analytics, and a cost budget. GitHub Actions runs `fmt`, `validate`, `tflint`, Checkov, Trivy and an in-house policy checker, plans on PRs and applies through OIDC (no stored cloud secret). **Status: `terraform validate`, tflint, Checkov (43 checks passed, 1 documented exception), Trivy, the in-house policy checker, the app tests and the Docker image (build + `/healthz`) all pass locally; no real Azure deployment yet** (see *Limites*).

Projet personnel : déployer une application d'IA générative sur Azure **en appliquant la sécurité dès le code d'infrastructure** — réseau privé, zéro secret dans le code ou l'état Terraform, identités managées, journalisation, contrôles automatiques en CI et maîtrise des coûts.

## Ce que fait le projet

| Domaine | Mise en œuvre | Fichier |
|---|---|---|
| Réseau | VNet, sous-réseau applicatif et sous-réseau de points de terminaison privés, NSG avec liste blanche HTTPS et refus d'Internet | `infra/modules/network` |
| Exposition | Container Apps injecté dans le VNet, HTTPS uniquement, `ip_security_restriction` ; option `internal_only` | `infra/modules/containerapp` |
| Secrets | Key Vault RBAC, accès public coupé, protection contre la purge, point de terminaison privé + DNS privé ; secrets déposés **hors Terraform**, injectés par référence Key Vault | `infra/modules/keyvault`, `docs/deploiement.md` |
| Identité | Identité managée *user-assigned*, rôles minimaux à la portée de chaque ressource (Key Vault Secrets User, AcrPull, OpenAI User) | `infra/modules/identity` |
| Registre | ACR admin désactivé, pull anonyme désactivé, point de terminaison privé si Premium | `infra/modules/acr` |
| LLM (optionnel) | Azure OpenAI avec **clés désactivées** (Entra ID uniquement) et accès privé | `infra/modules/openai` |
| Journaux | Log Analytics (30 j, plafond 1 Go/j), diagnostics Key Vault / ACR / NSG / OpenAI, journaux applicatifs JSON | `infra/modules/monitoring` |
| Coûts | Budget mensuel avec alertes 50/80/100 %, zéro réplica au repos, destruction guidée | `infra/modules/monitoring`, `docs/cout.md` |
| CI/CD | fmt · validate · tflint · Checkov (bloquant) · Trivy IaC & image · règles maison ; plan sur PR, apply après approbation, destroy manuel ; OIDC sans secret | `.github/workflows/` |
| Contrôles maison | Vérificateur Python sans dépendance : 17 règles (Key Vault, ACR, NSG, ingress, OpenAI, tags, secrets en dur) | `policy_check/` |
| Application | API stdlib : `/healthz`, `/readyz`, `/ask` ; bornes d'entrée, clé d'API en temps constant, en-têtes de sécurité, prompt anti-injection, repli extractif sans LLM | `app/` |

Documentation : [architecture (Mermaid)](docs/architecture.md) · [modèle de menace STRIDE](docs/threat-model.md) · [déploiement, secrets, destruction](docs/deploiement.md) · [coût indicatif](docs/cout.md).

## Démarrage rapide (local, sans Azure)

```bash
make test          # 12 tests application + 7 tests du vérificateur
make policy        # règles de sécurité sur infra/
make run           # API sur http://127.0.0.1:8080
curl -s -X POST localhost:8080/ask -H 'Content-Type: application/json' \
     -d '{"question":"Comment se passe la rotation des secrets ?"}'
```
Dépendance unique de l'application : `numpy`. LLM local possible : `LLM_PROVIDER=openai_compat LLM_BASE_URL=http://localhost:11434 LLM_MODEL=llama3.1` (Ollama).

## Déploiement Azure

Voir [docs/deploiement.md](docs/deploiement.md) : fédération OIDC, amorçage ACR, push de l'image, `plan/apply`, dépôt du secret, `destroy`. **Détruire après la démo.**

## Règles du vérificateur (`policy_check/check.py`)

`KV001-004` Key Vault public off / purge protection / RBAC / ACL Deny · `ACR001-003` admin off / pas de pull anonyme / accès public conditionnel (avertissement) · `NSG001` pas d'entrée Allow depuis `*`, `0.0.0.0/0`, `Internet` · `CA001-003` HTTPS seul / liste blanche obligatoire si entrée externe / pas de plage universelle · `COG001-002` OpenAI sans clé et privé · `TAG001` tags obligatoires · `SEC001-002` secrets en dur (attributs et motifs : clé de stockage, clé privée, jetons GitHub/OpenAI/AWS, SAS) · `VAR001` pas de `0.0.0.0/0` par défaut.

Résultat actuel sur `infra/` : 39 ressources, 0 échec, 1 avertissement (ACR Basic à accès public authentifié, écart documenté dans `.checkov.yaml`).

## Limites (honnêtes)

- **Contrôles exécutés localement (Windows 11)** : `terraform fmt -check` et `validate` (azurerm ~> 3.116) OK, tflint OK, Trivy config OK, vérificateur maison 0 échec, Checkov **43 contrôles réussis**. Le seul contrôle en échec, CKV_AZURE_247 (prévention de fuite de données Azure OpenAI), est en exception documentée : la ressource interdit toute sortie réseau (`outbound_network_access_restricted = true`, liste `fqdns` vide), ce qui est plus strict que ce que la règle attend. `validate` a révélé une erreur corrigée (bloc `scale` attendu par azurerm 3.x au lieu de `sku`).
- **Pas encore de déploiement réel** : ni `terraform plan` contre un abonnement, ni `apply`. Des erreurs propres à Azure (quotas, noms déjà pris, disponibilité régionale d'Azure OpenAI) peuvent encore apparaître.
- **Image Docker** construite et démarrée localement (`/healthz` → 200), pas encore poussée dans un ACR.
- Le vérificateur maison analyse le texte HCL : il ne résout ni variables ni modules. C'est un garde-fou rapide, pas un substitut à Checkov.
- Les appels LLM réels (Azure OpenAI, Ollama) et l'identité managée sont testés contre des serveurs simulés, pas contre Azure.
- ACR Basic garde un accès public authentifié ; la variante entièrement privée (Premium + `internal_only`) est prévue mais plus coûteuse et sans accès VPN fourni.
- Le RAG est volontairement minimal (TF-IDF, 4 documents) : le sujet est la sécurité du déploiement.

## Phrase CV (une fois déployé et vérifié)

> « Déploiement sécurisé d'une application IA en IaC (Terraform, Azure) : réseau privé, gestion des secrets, scan Checkov en CI. »

Tant que le déploiement réel n'a pas été fait, formulation exacte : « conception d'un déploiement sécurisé d'application IA en Terraform (Azure) avec contrôles de sécurité automatisés en CI ».

## Arborescence

```
app/            API RAG (ragapp/), corpus (docs/), tests, Dockerfile non-root
infra/          racine Terraform + modules network, keyvault, identity, acr, openai, containerapp, monitoring
policy_check/   vérificateur de politiques + tests
docs/           architecture, STRIDE, déploiement, coût
.github/        workflows terraform, app, destroy
.checkov.yaml   exceptions justifiées      .tflint.hcl   configuration tflint
```
