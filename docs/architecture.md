# Architecture

```mermaid
flowchart LR
  user([Utilisateur<br/>IP en liste blanche]) -->|HTTPS 443| ing

  subgraph GH[GitHub Actions]
    ci[fmt · validate · tflint<br/>Checkov · Trivy · policy_check]
    plan[plan / apply<br/>OIDC, sans secret]
  end

  subgraph RG[Groupe de ressources rg-secai-demo · France Central]
    subgraph VNET[VNet 10.20.0.0/16]
      subgraph SAPP[snet-app /23 · NSG : 443 liste blanche, Internet refusé]
        ing[Ingress Container Apps<br/>HTTPS only + ip_security_restriction]
        app[Container App ragapp<br/>non-root · min 0 réplica]
      end
      subgraph SPE[snet-pe /27 · NSG : 443 depuis snet-app uniquement]
        pekv[PE Key Vault]
        peoai[PE Azure OpenAI<br/>optionnel]
      end
    end
    id[[Identité managée<br/>user-assigned]]
    kv[(Key Vault<br/>RBAC · public off<br/>purge protection)]
    acr[(ACR<br/>admin off · pull anonyme off)]
    oai[(Azure OpenAI<br/>clés désactivées · public off)]
    law[(Log Analytics<br/>30 j · 1 Go/j)]
    budget{{Budget<br/>alertes 50/80/100 %}}
  end

  ing --> app
  app -. jeton Entra ID .-> id
  id -->|Key Vault Secrets User| kv
  id -->|AcrPull| acr
  id -->|OpenAI User| oai
  app --> pekv --> kv
  app --> peoai --> oai
  app -->|stdout JSON| law
  kv -->|AuditEvent| law
  acr -->|login / repository events| law
  plan -->|ARM| RG
  ci --> plan
```

## Flux de confiance

| Flux | Authentification | Réseau |
|---|---|---|
| Utilisateur → app | clé d'API optionnelle (`X-API-Key`, valeur en Key Vault) | HTTPS, liste blanche IP (ingress + NSG) |
| App → Key Vault | identité managée, rôle *Key Vault Secrets User* | point de terminaison privé, DNS privé |
| App → Azure OpenAI | identité managée, rôle *Cognitive Services OpenAI User*, clés désactivées | point de terminaison privé |
| Plateforme → ACR (pull) | identité managée, rôle *AcrPull* | public authentifié (Basic) ou privé (Premium) |
| GitHub → Azure | OIDC fédéré, aucun secret stocké | Internet (API ARM) |
| Terraform → état | Entra ID (`use_azuread_auth`), pas de clé de compte | Internet (à restreindre) |

## Choix et alternatives

- **Container Apps** plutôt qu'App Service : facturation à l'usage avec zéro réplica, références Key Vault natives, injection VNet.
- **Identité user-assigned** : les rôles sont attribués avant le premier démarrage (pas de course entre création de l'app et droits).
- **Secrets hors Terraform** : la valeur d'un `azurerm_key_vault_secret` finit dans l'état en clair. Ici l'état ne contient aucun secret applicatif.
- **Variante 100 % privée** : `internal_only = true` + `acr_sku = "Premium"` ; l'accès passe alors par un VPN / Bastion (non inclus).
