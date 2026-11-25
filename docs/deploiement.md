# Déploiement, dépôt des secrets et destruction

Prérequis : Azure CLI, Terraform ≥ 1.6, Docker, un abonnement Azure (essai gratuit possible), droits *Owner* sur l'abonnement de démo (ou *Contributor* + *User Access Administrator*).

## 0. (Une fois) Fédération OIDC pour GitHub Actions

```bash
az ad app create --display-name gh-secure-ai-terraform
APP_ID=$(az ad app list --display-name gh-secure-ai-terraform --query "[0].appId" -o tsv)
az ad sp create --id "$APP_ID"
# Jeton accepté uniquement pour l'environnement GitHub « demo » de CE dépôt :
az ad app federated-credential create --id "$APP_ID" --parameters '{
  "name": "gh-demo", "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:<compte>/<depot>:environment:demo", "audiences": ["api://AzureADTokenExchange"] }'
az role assignment create --assignee "$APP_ID" --role Contributor --scope /subscriptions/<sub>
az role assignment create --assignee "$APP_ID" --role "User Access Administrator" --scope /subscriptions/<sub>
```
Puis, dans GitHub → *Settings → Variables* : `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `TF_OWNER`, `TF_ALLOWED_INGRESS_CIDRS`, `TF_BUDGET_EMAILS`, `TF_CONTAINER_IMAGE`, `ACR_NAME`. Aucun *secret* n'est nécessaire. Créer l'environnement `demo` avec approbation obligatoire.

## 1. Amorçage (registre + identité)

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # renseigner owner, IP, e-mail
az login
terraform init
terraform apply -target=module.acr -target=module.identity -target=module.monitoring
terraform output acr_login_server              # -> mettre à jour container_image
```

## 2. Image

```bash
cd ..
make test                                       # tests app + règles
ACR=acrsecaixxxxx make push                     # nécessite le rôle AcrPush pour votre compte
```

## 3. Déploiement complet

```bash
make policy                                     # règles maison (bloquant)
terraform -chdir=infra plan -out=tfplan
terraform -chdir=infra apply tfplan
curl -s "$(terraform -chdir=infra output -raw app_url)/healthz"
```

## 4. Dépôt d'un secret dans Key Vault (hors Terraform)

Le coffre n'a pas d'accès public : il faut soit opérer depuis le VNet (VM de rebond, Cloud Shell injecté dans le VNet), soit — pour une démo — ouvrir **temporairement** l'accès à sa seule IP :

```bash
KV=$(terraform -chdir=infra output -raw key_vault_name)
ME=$(az ad signed-in-user show --query id -o tsv)
MYIP=$(curl -s ifconfig.me)
az role assignment create --assignee "$ME" --role "Key Vault Secrets Officer" \
  --scope "$(az keyvault show -n "$KV" --query id -o tsv)"
az keyvault update -n "$KV" --public-network-access Enabled --default-action Deny
az keyvault network-rule add -n "$KV" --ip-address "$MYIP/32"
az keyvault secret set --vault-name "$KV" -n app-api-key --value "$(openssl rand -hex 24)" -o none
az keyvault network-rule remove -n "$KV" --ip-address "$MYIP/32"
az keyvault update -n "$KV" --public-network-access Disabled
```
Puis `app_secret_names = ["app-api-key"]` dans `terraform.tfvars` et `terraform apply`. La valeur n'apparaît ni dans le plan ni dans l'état. Le prochain `apply` corrige de toute façon une dérive éventuelle de l'accès public.

## 5. Destruction après la démo

```bash
terraform -chdir=infra destroy
az group list --tag project=secai -o table      # doit être vide
az keyvault list-deleted -o table               # le coffre y figure : normal (purge protection)
```
Ou via GitHub : *Actions → destroy → Run workflow*, saisir `DETRUIRE`, approuver.
Le coffre supprimé reste récupérable pendant `soft_delete_retention_days` (7 jours) ; il n'est pas facturé et son nom reste réservé pendant ce délai (le suffixe aléatoire évite le conflit au redéploiement).
