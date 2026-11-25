#!/usr/bin/env python3
"""Vérificateur de politiques de sécurité pour le code Terraform de ce dépôt.

Complément léger (sans dépendance) à Checkov/tfsec, utilisable hors ligne et en
pre-commit. Il lit les fichiers .tf avec un analyseur HCL simplifié (blocs,
attributs, chaînes, commentaires) et applique des règles ciblées sur les choix de
sécurité du projet. Il ne remplace PAS terraform validate ni Checkov : il ne résout
ni les variables ni les modules, il contrôle ce qui est écrit.

Usage :
    python3 policy_check/check.py infra/            # rapport texte, code retour 1 si échec
    python3 policy_check/check.py infra/ --json     # rapport JSON
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------- #
# Analyseur HCL simplifié
# --------------------------------------------------------------------------- #


def strip_comments(src: str) -> str:
    """Retire les commentaires #, // et /* */ en respectant les chaînes."""
    out: list[str] = []
    i, n = 0, len(src)
    in_str = False
    interp = 0  # profondeur ${ } à l'intérieur d'une chaîne
    while i < n:
        c = src[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if src.startswith("${", i):
                interp += 1
                out.append("{")
                i += 2
                continue
            if c == "}" and interp:
                interp -= 1
            elif c == '"' and not interp:
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
        elif c == "#" or src.startswith("//", i):
            while i < n and src[i] != "\n":
                i += 1
        elif src.startswith("/*", i):
            end = src.find("*/", i + 2)
            i = n if end == -1 else end + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


@dataclass
class Block:
    type: str
    labels: list[str]
    attrs: dict[str, str] = field(default_factory=dict)
    blocks: list["Block"] = field(default_factory=list)
    file: str = ""
    line: int = 0

    def sub(self, name: str) -> list["Block"]:
        """Blocs imbriqués statiques ET blocs `dynamic "name"` (leur `content`)."""
        found = [b for b in self.blocks if b.type == name]
        for d in self.blocks:
            if d.type == "dynamic" and d.labels and d.labels[0] == name:
                found.extend(b for b in d.blocks if b.type == "content")
        return found

    @property
    def address(self) -> str:
        return ".".join(self.labels) if self.labels else self.type


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")


def _skip_ws(s: str, i: int) -> int:
    while i < len(s) and s[i] in " \t\r\n":
        i += 1
    return i


def _read_string(s: str, i: int) -> int:
    """i pointe sur '"' ; renvoie l'index après la chaîne fermante."""
    i += 1
    interp = 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if s.startswith("${", i):
            interp += 1
            i += 2
            continue
        if c == "}" and interp:
            interp -= 1
        elif c == '"' and not interp:
            return i + 1
        i += 1
    raise ValueError("chaîne non fermée")


def _read_expr(s: str, i: int) -> int:
    """Lit une expression d'attribut jusqu'à la fin de ligne au niveau 0."""
    depth = 0
    while i < len(s):
        c = s[i]
        if c == '"':
            i = _read_string(s, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif c == "\n" and depth == 0:
            return i
        i += 1
    return i


def parse_body(s: str, i: int, file: str, base_line: int = 1) -> tuple[Block, int]:
    """Analyse un corps jusqu'à '}' (ou fin de texte). Renvoie (bloc, index après '}')."""
    body = Block("body", [], file=file)
    while True:
        i = _skip_ws(s, i)
        if i >= len(s):
            return body, i
        if s[i] == "}":
            return body, i + 1
        m = _IDENT.match(s, i)
        if not m:
            raise ValueError(f"{file}:{s.count(chr(10), 0, i) + 1}: syntaxe inattendue {s[i:i + 20]!r}")
        name, start = m.group(0), i
        i = _skip_ws(s, m.end())
        if i < len(s) and s[i] == "=" and not s.startswith("==", i):
            j = _read_expr(s, i + 1)
            body.attrs[name] = s[i + 1:j].strip()
            i = j
            continue
        labels: list[str] = []
        while i < len(s) and s[i] != "{":
            if s[i] == '"':
                j = _read_string(s, i)
                labels.append(s[i + 1:j - 1])
                i = _skip_ws(s, j)
            else:
                lm = _IDENT.match(s, i)
                if not lm:
                    raise ValueError(f"{file}: bloc mal formé près de {s[start:start + 40]!r}")
                labels.append(lm.group(0))
                i = _skip_ws(s, lm.end())
        child, i = parse_body(s, i + 1, file)
        child.type, child.labels = name, labels
        child.line = s.count("\n", 0, start) + 1
        body.blocks.append(child)


def parse_file(path: Path) -> list[Block]:
    text = strip_comments(path.read_text(encoding="utf-8"))
    root, _ = parse_body(text, 0, str(path))
    return root.blocks


# --------------------------------------------------------------------------- #
# Règles
# --------------------------------------------------------------------------- #


@dataclass
class Finding:
    rule: str
    severity: str  # FAIL | WARN
    file: str
    line: int
    resource: str
    message: str


def _is(value: str | None, literal: str) -> bool:
    return value is not None and value.strip().strip('"').lower() == literal


def _is_static(value: str | None) -> bool:
    return value is not None and re.fullmatch(r'(true|false|"[^"$]*"|-?\d+)', value.strip()) is not None


ANY_SOURCES = {"*", "0.0.0.0/0", "internet", "any", "::/0"}

# Types azurerm qui n'acceptent pas d'argument `tags`.
NON_TAGGABLE = {
    "azurerm_subnet",
    "azurerm_network_security_rule",
    "azurerm_subnet_network_security_group_association",
    "azurerm_role_assignment",
    "azurerm_monitor_diagnostic_setting",
    "azurerm_consumption_budget_resource_group",
    "azurerm_cognitive_deployment",
    "azurerm_key_vault_secret",
}

SECRET_ATTR = re.compile(
    r"(^|_)(password|passwd|secret|client_secret|api_key|access_key|primary_key|token|connection_string|sas)$"
)
SECRET_PATTERNS = [
    ("clé de compte de stockage", re.compile(r"AccountKey=[A-Za-z0-9+/=]{20,}")),
    ("clé privée", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jeton GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("clé de type OpenAI", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("clé d'accès AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("SAS Azure", re.compile(r"[?&]sig=[A-Za-z0-9%+/=]{20,}")),
]


def _addr(b: Block) -> str:
    return b.address


def check_resource(b: Block) -> list[Finding]:
    f: list[Finding] = []
    rtype = b.labels[0] if b.labels else ""

    def add(rule, sev, msg, line=None):
        f.append(Finding(rule, sev, b.file, line or b.line, _addr(b), msg))

    a = b.attrs

    if rtype == "azurerm_key_vault":
        if not _is(a.get("public_network_access_enabled"), "false"):
            add("KV001", "FAIL", "Key Vault : public_network_access_enabled doit valoir false")
        if not _is(a.get("purge_protection_enabled"), "true"):
            add("KV002", "FAIL", "Key Vault : purge_protection_enabled doit valoir true")
        if not (_is(a.get("enable_rbac_authorization"), "true") or _is(a.get("rbac_authorization_enabled"), "true")):
            add("KV003", "FAIL", "Key Vault : l'autorisation RBAC doit être activée")
        acls = b.sub("network_acls")
        if not acls or not _is(acls[0].attrs.get("default_action"), "deny"):
            add("KV004", "FAIL", "Key Vault : network_acls.default_action doit valoir \"Deny\"")

    if rtype == "azurerm_container_registry":
        if not _is(a.get("admin_enabled"), "false"):
            add("ACR001", "FAIL", "ACR : admin_enabled doit être explicitement false")
        if _is(a.get("anonymous_pull_enabled"), "true"):
            add("ACR002", "FAIL", "ACR : pull anonyme interdit")
        pna = a.get("public_network_access_enabled")
        if pna is not None and not _is_static(pna):
            add("ACR003", "WARN", f"ACR : accès public conditionnel ({pna}) — vérifier le SKU déployé")

    if rtype == "azurerm_network_security_rule":
        f.extend(_check_rule(a, b, b.line))
    if rtype == "azurerm_network_security_group":
        for r in b.sub("security_rule"):
            f.extend(_check_rule(r.attrs, b, r.line))

    if rtype == "azurerm_container_app":
        for ing in b.sub("ingress"):
            if _is(ing.attrs.get("allow_insecure_connections"), "true"):
                add("CA001", "FAIL", "Container App : HTTP non chiffré autorisé", ing.line)
            if _is(ing.attrs.get("external_enabled"), "true"):
                restrictions = ing.sub("ip_security_restriction")
                if not restrictions:
                    add("CA002", "FAIL", "Container App : entrée externe sans liste blanche IP", ing.line)
                for r in restrictions:
                    rng = (r.attrs.get("ip_address_range") or "").strip('"')
                    if rng in ANY_SOURCES:
                        add("CA003", "FAIL", f"Container App : plage autorisée trop large ({rng})", r.line)

    if rtype == "azurerm_cognitive_account":
        if not _is(a.get("local_auth_enabled"), "false"):
            add("COG001", "FAIL", "Cognitive/OpenAI : désactiver l'authentification par clé (local_auth_enabled = false)")
        if not _is(a.get("public_network_access_enabled"), "false"):
            add("COG002", "FAIL", "Cognitive/OpenAI : accès public à désactiver")

    if rtype.startswith("azurerm_") and rtype not in NON_TAGGABLE and "tags" not in a:
        add("TAG001", "FAIL", f"{rtype} : attribut tags manquant")

    f.extend(_check_secret_attrs(b, b))
    return f


def _check_rule(a: dict[str, str], owner: Block, line: int) -> list[Finding]:
    if not (_is(a.get("direction"), "inbound") and _is(a.get("access"), "allow")):
        return []
    sources: set[str] = set()
    if "source_address_prefix" in a:
        sources.add(a["source_address_prefix"].strip().strip('"').lower())
    lst = a.get("source_address_prefixes", "")
    sources.update(x.lower() for x in re.findall(r'"([^"]*)"', lst))
    bad = sources & ANY_SOURCES
    if bad:
        return [Finding("NSG001", "FAIL", owner.file, line, owner.address,
                        f"NSG : règle entrante Allow depuis {sorted(bad)} (Internet entier)")]
    return []


def _check_secret_attrs(b: Block, owner: Block) -> list[Finding]:
    out: list[Finding] = []
    for k, v in b.attrs.items():
        if SECRET_ATTR.search(k) and re.fullmatch(r'"[^"$]+"', v.strip()):
            out.append(Finding("SEC001", "FAIL", owner.file, b.line or owner.line, owner.address,
                               f"secret en dur dans l'attribut « {k} »"))
    for child in b.blocks:
        out.extend(_check_secret_attrs(child, owner))
    return out


def check_variables(b: Block) -> list[Finding]:
    default = b.attrs.get("default", "")
    if '"0.0.0.0/0"' in default:
        return [Finding("VAR001", "FAIL", b.file, b.line, f"var.{b.labels[0]}",
                        "valeur par défaut ouvrant à tout Internet (0.0.0.0/0)")]
    return []


def scan_secret_patterns(path: Path) -> list[Finding]:
    out: list[Finding] = []
    for no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        for label, rx in SECRET_PATTERNS:
            if rx.search(line):
                out.append(Finding("SEC002", "FAIL", str(path), no, "-", f"motif de secret détecté : {label}"))
    return out


def run(root: Path) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    tf_files = sorted(p for p in root.rglob("*.tf") if ".terraform" not in p.parts)
    other = sorted(p for pat in ("*.tfvars", "*.tfvars.example", "*.tfvars.json")
                   for p in root.rglob(pat) if ".terraform" not in p.parts)
    resources = 0
    for p in tf_files:
        for b in parse_file(p):
            if b.type == "resource":
                resources += 1
                findings.extend(check_resource(b))
            elif b.type == "variable":
                findings.extend(check_variables(b))
        findings.extend(scan_secret_patterns(p))
    for p in other:
        findings.extend(scan_secret_patterns(p))
    return findings, resources


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path", nargs="?", default="infra")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.path)
    if not root.exists():
        print(f"chemin introuvable : {root}", file=sys.stderr)
        return 2
    findings, resources = run(root)
    fails = [x for x in findings if x.severity == "FAIL"]
    if args.json:
        print(json.dumps({"resources": resources, "findings": [asdict(x) for x in findings],
                          "failed": len(fails)}, ensure_ascii=False, indent=2))
    else:
        for x in findings:
            print(f"[{x.severity}] {x.rule} {x.file}:{x.line} {x.resource} — {x.message}")
        print(f"\n{resources} ressources analysées, {len(fails)} échec(s), "
              f"{len(findings) - len(fails)} avertissement(s).")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
