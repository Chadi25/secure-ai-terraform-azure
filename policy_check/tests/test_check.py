"""Tests du vérificateur (unittest, compatible pytest)."""
from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "policy_check"))

import check  # noqa: E402

GOOD = '''
# commentaire avec "guillemets" et { accolades }
resource "azurerm_key_vault" "kv" {
  name                          = "kv-demo" // commentaire fin de ligne
  public_network_access_enabled = false
  purge_protection_enabled      = true
  enable_rbac_authorization     = true
  network_acls {
    default_action = "Deny"
    bypass         = "AzureServices"
  }
  tags = var.tags
}

resource "azurerm_container_registry" "acr" {
  name          = "acrdemo"
  admin_enabled = false
  tags          = { owner = "x", note = "a}b" }
}

resource "azurerm_network_security_rule" "ok" {
  direction               = "Inbound"
  access                  = "Allow"
  source_address_prefixes = ["203.0.113.10/32"]
}

resource "azurerm_container_app" "app" {
  secret {
    name                = "app-api-key"
    key_vault_secret_id = "${var.kv_uri}secrets/app-api-key"
  }
  ingress {
    external_enabled           = true
    allow_insecure_connections = false
    dynamic "ip_security_restriction" {
      for_each = var.cidrs
      content {
        action           = "Allow"
        ip_address_range = ip_security_restriction.value
      }
    }
  }
  tags = var.tags
}
'''

BAD = '''
resource "azurerm_key_vault" "kv" {
  public_network_access_enabled = true
  purge_protection_enabled      = false
  tags = {}
}

resource "azurerm_container_registry" "acr" {
  admin_enabled          = true
  anonymous_pull_enabled = true
}

resource "azurerm_network_security_group" "nsg" {
  tags = {}
  security_rule {
    direction             = "Inbound"
    access                = "Allow"
    source_address_prefix = "*"
  }
}

resource "azurerm_network_security_rule" "open" {
  direction               = "Inbound"
  access                  = "Allow"
  source_address_prefixes = ["10.0.0.0/8", "0.0.0.0/0"]
}

resource "azurerm_container_app" "app" {
  tags = {}
  ingress {
    external_enabled           = true
    allow_insecure_connections = true
  }
}

resource "azurerm_cognitive_account" "oai" {
  tags = {}
}

resource "azurerm_mssql_server" "db" {
  administrator_login_password = "P@ssw0rd-en-dur"
  tags = {}
}

variable "allowed" {
  default = ["0.0.0.0/0"]
}
'''


def _scan(content: str, name: str = "main.tf") -> tuple[set[str], int]:
    with tempfile.TemporaryDirectory() as d:
        Path(d, name).write_text(textwrap.dedent(content), encoding="utf-8")
        findings, n = check.run(Path(d))
    return {f.rule for f in findings if f.severity == "FAIL"}, n


class ParserTest(unittest.TestCase):
    def test_comments_and_strings(self):
        src = check.strip_comments('a = "x # pas un commentaire" # vrai\nb = 1 /* bloc */\n')
        self.assertIn('"x # pas un commentaire"', src)
        self.assertNotIn("vrai", src)
        self.assertNotIn("bloc", src)

    def test_nested_and_dynamic_blocks(self):
        blocks = check.parse_body(check.strip_comments(GOOD), 0, "t")[0].blocks
        app = [b for b in blocks if b.labels == ["azurerm_container_app", "app"]][0]
        ing = app.sub("ingress")[0]
        self.assertEqual(ing.attrs["external_enabled"], "true")
        self.assertEqual(len(ing.sub("ip_security_restriction")), 1)
        acr = [b for b in blocks if b.labels[0] == "azurerm_container_registry"][0]
        self.assertIn("a}b", acr.attrs["tags"])


class RulesTest(unittest.TestCase):
    def test_good_config_passes(self):
        fails, n = _scan(GOOD)
        self.assertEqual(fails, set())
        self.assertEqual(n, 4)

    def test_bad_config_is_caught(self):
        fails, _ = _scan(BAD)
        expected = {"KV001", "KV002", "KV003", "KV004", "ACR001", "ACR002", "NSG001",
                    "CA001", "CA002", "COG001", "COG002", "TAG001", "SEC001", "VAR001"}
        self.assertEqual(expected - fails, set(), f"règles non déclenchées : {expected - fails}")

    def test_secret_patterns_in_tfvars(self):
        fails, _ = _scan('conn = "DefaultEndpointsProtocol=https;AccountKey=' + "A" * 40 + '"\n',
                         "terraform.tfvars")
        self.assertIn("SEC002", fails)

    def test_repository_infra_is_compliant(self):
        findings, n = check.run(ROOT / "infra")
        fails = [f for f in findings if f.severity == "FAIL"]
        self.assertGreater(n, 20)
        self.assertEqual(fails, [], "\n".join(f"{f.rule} {f.file}:{f.line} {f.message}" for f in fails))

    def test_cli_exit_codes(self):
        self.assertEqual(check.main([str(ROOT / "infra")]), 0)
        with tempfile.TemporaryDirectory() as d:
            Path(d, "main.tf").write_text(BAD, encoding="utf-8")
            self.assertEqual(check.main([d]), 1)


if __name__ == "__main__":
    unittest.main()
