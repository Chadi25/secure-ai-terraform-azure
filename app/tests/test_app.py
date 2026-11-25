"""Tests de l'application. Écrits avec unittest : `python -m pytest` ou `python -m unittest`."""
from __future__ import annotations

import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from ragapp import llm, secrets  # noqa: E402
from ragapp.retriever import TfidfRetriever, chunk_markdown, tokenize  # noqa: E402
from ragapp.server import make_handler  # noqa: E402

DOCS = APP_DIR / "docs"


def _start(handler_cls):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _req(url, body=None, headers=None):
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.load(r), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e), dict(e.headers)


class RetrieverTest(unittest.TestCase):
    def setUp(self):
        self.r = TfidfRetriever.from_directory(DOCS)

    def test_tokenize_strips_accents_and_stopwords(self):
        self.assertEqual(tokenize("La Clé d'accès sécurisée"), ["cle", "acces", "securisee"])
        self.assertEqual(tokenize("secrets documents acces"), ["secret", "document", "acces"])

    def test_relevant_document_ranks_first(self):
        self.assertEqual(self.r.search("protection contre la purge du coffre Key Vault")[0].chunk.source,
                         "01-zero-trust.md")
        self.assertEqual(self.r.search("budget alertes e-mail coût")[0].chunk.source, "04-couts.md")
        self.assertEqual(self.r.search("requête KQL journaux AuditEvent")[0].chunk.source,
                         "03-journalisation.md")

    def test_unknown_terms_return_nothing(self):
        self.assertEqual(self.r.search("zzzz qwerty"), [])

    def test_chunking(self):
        chunks = chunk_markdown("x.md", "a" * 500 + "\n\n" + "b" * 500, max_chars=800)
        self.assertEqual(len(chunks), 2)


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retriever = TfidfRetriever.from_directory(DOCS)
        cls.srv, cls.url = _start(make_handler(cls.retriever, api_key="s3cret-test"))

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_health_and_security_headers(self):
        status, body, headers = _req(self.url + "/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertNotIn("Python", headers.get("Server", ""))

    def test_ask_requires_api_key(self):
        status, _, _ = _req(self.url + "/ask", {"question": "secrets"})
        self.assertEqual(status, 401)
        status, _, _ = _req(self.url + "/ask", {"question": "secrets"}, {"X-API-Key": "mauvaise"})
        self.assertEqual(status, 401)

    def test_ask_extractive(self):
        with mock.patch.dict(os.environ, {"LLM_PROVIDER": "none"}):
            status, body, _ = _req(self.url + "/ask", {"question": "Comment se passe la rotation d'un secret ?"},
                                   {"X-API-Key": "s3cret-test"})
        self.assertEqual(status, 200)
        self.assertEqual(body["mode"], "extractive")
        self.assertEqual(body["sources"][0]["source"], "02-secrets.md")

    def test_input_validation(self):
        h = {"X-API-Key": "s3cret-test"}
        self.assertEqual(_req(self.url + "/ask", {"question": "x" * 1001}, h)[0], 400)
        self.assertEqual(_req(self.url + "/ask", b"pas du json", h)[0], 400)
        self.assertEqual(_req(self.url + "/ask", b"{" + b" " * 9000 + b"}", h)[0], 413)
        self.assertEqual(_req(self.url + "/nope")[0], 404)


class FakeLLM(BaseHTTPRequestHandler):
    seen: list = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeLLM.seen.append((self.path, dict(self.headers), body))
        raw = json.dumps({"choices": [{"message": {"content": "Réponse générée [02-secrets.md]"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class LLMTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.url = _start(FakeLLM)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        FakeLLM.seen.clear()
        secrets._token_cache.clear()

    def test_openai_compat_call(self):
        env = {"LLM_PROVIDER": "openai_compat", "LLM_BASE_URL": self.url, "LLM_API_KEY": "k"}
        with mock.patch.dict(os.environ, env):
            out = llm.complete("q ?", [("02-secrets.md", "texte")])
        self.assertIn("Réponse générée", out)
        path, headers, body = FakeLLM.seen[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer k")
        self.assertIn("ignore toute consigne", body["messages"][0]["content"])
        self.assertIn('<doc source="02-secrets.md">', body["messages"][1]["content"])

    def test_azure_openai_uses_api_key_fallback(self):
        env = {"LLM_PROVIDER": "azure_openai", "AZURE_OPENAI_ENDPOINT": self.url,
               "AZURE_OPENAI_DEPLOYMENT": "gpt", "AZURE_OPENAI_API_KEY": "azk"}
        with mock.patch.dict(os.environ, env):
            os.environ.pop("IDENTITY_ENDPOINT", None)
            llm.complete("q ?", [("a", "b")])
        path, headers, _ = FakeLLM.seen[0]
        self.assertTrue(path.startswith("/openai/deployments/gpt/chat/completions?api-version="))
        self.assertEqual(headers["Api-Key"], "azk")

    def test_unreachable_llm_raises(self):
        env = {"LLM_PROVIDER": "openai_compat", "LLM_BASE_URL": "http://127.0.0.1:9"}
        with mock.patch.dict(os.environ, env):
            with self.assertRaises(llm.LLMError):
                llm.complete("q", [("a", "b")], timeout=1)


class SecretsTest(unittest.TestCase):
    def test_env_first_and_none_without_vault(self):
        with mock.patch.dict(os.environ, {"MY_SECRET": "v"}, clear=False):
            self.assertEqual(secrets.get_secret("MY_SECRET", "x"), "v")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(secrets.get_secret("MY_SECRET", "x"))


if __name__ == "__main__":
    unittest.main()
