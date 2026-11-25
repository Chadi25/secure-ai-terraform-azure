# Estimation de coût — INDICATIVE, À VÉRIFIER

> Ordres de grandeur établis de mémoire, **non vérifiés** sur la grille tarifaire actuelle.
> Avant tout déploiement : recalculer avec la [calculatrice de prix Azure](https://azure.microsoft.com/pricing/calculator/) pour la région France Central, et activer le budget (déjà dans le code).

| Ressource | Hypothèse | Ordre de grandeur / mois si laissé allumé |
|---|---|---|
| Container Apps (consommation) | 0 réplica au repos, quelques requêtes de démo | ~0 (couvert par l'allocation gratuite mensuelle) |
| Environnement Container Apps en VNet | IP publique / équilibreur gérés par la plateforme | quelques € |
| ACR Basic | 10 Go inclus | ~5 € |
| Key Vault standard | quelques centaines d'opérations | < 1 € |
| Point(s) de terminaison privé(s) | 1 (Key Vault), +1 si OpenAI, +1 si ACR Premium | ~7 € chacun |
| Zones DNS privées | 1 à 3 zones | < 2 € |
| Log Analytics | < 1 Go ingéré, plafond 1 Go/jour | ~0 à quelques € |
| Azure OpenAI (optionnel) | facturé au jeton | dépend de l'usage |
| **Total indicatif** | sans OpenAI, ACR Basic | **~15 à 20 € / mois** |

Pour une démo d'une journée puis `destroy`, le coût attendu est de l'ordre de **1 €**.
Option à surveiller : `acr_sku = "Premium"` ajoute un coût fixe nettement plus élevé (plusieurs dizaines d'€ / mois).
