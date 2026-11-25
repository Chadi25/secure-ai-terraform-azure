"""API HTTP (bibliothèque standard uniquement).

GET  /healthz  -> sonde de vie (utilisée par Docker HEALTHCHECK et Container Apps)
GET  /readyz   -> index chargé
POST /ask      -> {"question": "..."} ; renvoie réponse + sources

Mesures de sécurité applicatives :
- taille de requête et longueur de question bornées ;
- clé d'API optionnelle (APP_API_KEY, idéalement référence Key Vault), comparée
  en temps constant ;
- en-têtes de sécurité, pas de trace d'exception renvoyée au client ;
- journaux JSON sur stdout (collectés par Log Analytics), sans contenu sensible.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import llm
from .retriever import TfidfRetriever
from .secrets import get_secret

MAX_BODY = 8 * 1024
MAX_QUESTION = 1000
DOCS_DIR = Path(os.getenv("DOCS_DIR", Path(__file__).resolve().parent.parent / "docs"))

log = logging.getLogger("ragapp")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"ts": round(time.time(), 3), "level": record.levelname, "msg": record.getMessage()}
        payload.update(getattr(record, "extra_fields", {}))
        return json.dumps(payload, ensure_ascii=False)


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'",
    "Cache-Control": "no-store",
    "Strict-Transport-Security": "max-age=31536000",
}


def answer(retriever: TfidfRetriever, question: str) -> dict:
    hits = retriever.search(question, k=3)
    sources = [{"source": h.chunk.source, "score": round(h.score, 3)} for h in hits]
    if not hits:
        return {"answer": "Aucun passage pertinent trouvé dans la base documentaire.", "sources": [], "mode": "none"}
    contexts = [(h.chunk.source, h.chunk.text) for h in hits]
    try:
        generated = llm.complete(question, contexts)
    except llm.LLMError:
        log.warning("LLM indisponible, repli extractif")
        generated = None
    if generated:
        return {"answer": generated, "sources": sources, "mode": "llm"}
    best = hits[0].chunk
    return {"answer": best.text[:600], "sources": sources, "mode": "extractive"}


def make_handler(retriever: TfidfRetriever, api_key: str | None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ragapp"
        sys_version = ""

        def log_message(self, fmt, *args):  # remplace le log stderr par défaut
            pass

        def _send(self, status: int, body: dict) -> None:
            raw = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            for k, v in SECURITY_HEADERS.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(raw)

        def _audit(self, status: int, started: float, rid: str) -> None:
            rec = logging.LogRecord("ragapp", logging.INFO, "", 0, "request", None, None)
            rec.extra_fields = {
                "request_id": rid, "method": self.command, "path": self.path.split("?")[0],
                "status": status, "duration_ms": round((time.time() - started) * 1000, 1),
            }
            log.handle(rec)

        def do_GET(self):
            started, rid = time.time(), uuid.uuid4().hex[:12]
            if self.path in ("/healthz", "/readyz"):
                status, body = 200, {"status": "ok", "chunks": len(retriever.chunks)}
            else:
                status, body = 404, {"error": "not found"}
            self._send(status, body)
            self._audit(status, started, rid)

        def do_POST(self):
            started, rid = time.time(), uuid.uuid4().hex[:12]
            status, body = self._handle_post()
            self._send(status, body)
            self._audit(status, started, rid)

        def _handle_post(self) -> tuple[int, dict]:
            if self.path != "/ask":
                return 404, {"error": "not found"}
            if api_key:
                provided = self.headers.get("X-API-Key", "")
                if not hmac.compare_digest(provided.encode(), api_key.encode()):
                    return 401, {"error": "unauthorized"}
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return 400, {"error": "bad content-length"}
            if length <= 0 or length > MAX_BODY:
                return 413, {"error": f"body must be 1..{MAX_BODY} bytes"}
            try:
                data = json.loads(self.rfile.read(length))
                question = str(data["question"]).strip()
            except (ValueError, KeyError, TypeError):
                return 400, {"error": "expected JSON {\"question\": \"...\"}"}
            if not question or len(question) > MAX_QUESTION:
                return 400, {"error": f"question must be 1..{MAX_QUESTION} chars"}
            try:
                return 200, answer(retriever, question)
            except Exception:  # noqa: BLE001
                log.exception("erreur interne")
                return 500, {"error": "internal error"}

    return Handler


def build_server(host: str = "0.0.0.0", port: int = 8080) -> ThreadingHTTPServer:
    retriever = TfidfRetriever.from_directory(DOCS_DIR)
    api_key = get_secret("APP_API_KEY", "app-api-key")
    return ThreadingHTTPServer((host, port), make_handler(retriever, api_key))


def main() -> None:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[h])
    port = int(os.getenv("PORT", "8080"))
    srv = build_server(port=port)
    log.info("ragapp démarrée sur le port %s", port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
