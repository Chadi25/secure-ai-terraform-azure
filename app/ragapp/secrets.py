"""Lecture des secrets sans jamais les écrire dans le code ni dans l'image.

Ordre de résolution :
1. variable d'environnement (cas nominal sur Azure Container Apps : le secret est
   une *référence Key Vault* résolue par la plateforme avec l'identité managée) ;
2. appel direct à Key Vault avec l'identité managée (endpoint IDENTITY_ENDPOINT
   fourni par Container Apps / App Service), si KEY_VAULT_URL est défini ;
3. None (la fonctionnalité qui en dépend est désactivée).

Aucun secret n'est journalisé ; les erreurs ne renvoient que le nom du secret.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request

log = logging.getLogger("ragapp.secrets")

VAULT_RESOURCE = "https://vault.azure.net"
COGNITIVE_RESOURCE = "https://cognitiveservices.azure.com"

_token_cache: dict[str, tuple[str, float]] = {}


def managed_identity_token(resource: str, timeout: float = 5.0) -> str | None:
    """Jeton Entra ID via l'identité managée (aucun secret client)."""
    cached = _token_cache.get(resource)
    if cached and cached[1] - 60 > time.time():
        return cached[0]
    endpoint = os.getenv("IDENTITY_ENDPOINT")
    header = os.getenv("IDENTITY_HEADER")
    if not endpoint or not header:
        return None
    params = {"resource": resource, "api-version": "2019-08-01"}
    client_id = os.getenv("AZURE_CLIENT_ID")  # identité user-assigned
    if client_id:
        params["client_id"] = client_id
    req = urllib.request.Request(
        f"{endpoint}?{urllib.parse.urlencode(params)}",
        headers={"X-IDENTITY-HEADER": header},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except Exception:  # noqa: BLE001 - on ne divulgue pas le détail
        log.warning("échec d'obtention du jeton d'identité managée pour %s", resource)
        return None
    token = data.get("access_token")
    expires = float(data.get("expires_on", time.time() + 300))
    if token:
        _token_cache[resource] = (token, expires)
    return token


def get_secret(env_name: str, vault_secret_name: str | None = None) -> str | None:
    value = os.getenv(env_name)
    if value:
        return value
    vault_url = os.getenv("KEY_VAULT_URL")
    if not vault_url or not vault_secret_name:
        return None
    token = managed_identity_token(VAULT_RESOURCE)
    if not token:
        return None
    url = f"{vault_url.rstrip('/')}/secrets/{urllib.parse.quote(vault_secret_name)}?api-version=7.4"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            return json.load(resp).get("value")
    except Exception:  # noqa: BLE001
        log.warning("secret %s illisible dans Key Vault", vault_secret_name)
        return None
