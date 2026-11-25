# Image minimale, utilisateur non-root, système de fichiers en lecture seule possible.
# En production, épingler l'image de base par digest (@sha256:...) et la scanner (Trivy) en CI.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Utilisateur dédié sans shell ni home inscriptible.
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY --chown=root:root ragapp ./ragapp
COPY --chown=root:root docs ./docs

USER 10001:10001
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).status == 200 else 1)"]

ENTRYPOINT ["python", "-m", "ragapp"]
