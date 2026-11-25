"""Recherche documentaire TF-IDF minimaliste (numpy uniquement).

Volontairement simple : l'objet du projet est la sécurité du déploiement,
pas la qualité du RAG. Le moteur est remplaçable (FAISS, Azure AI Search...).
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_TOKEN = re.compile(r"[a-z0-9]{2,}")
_STOP = set(
    "le la les un une des de du et ou en au aux a est sont pour par sur dans avec "
    "ce ces cette qui que quoi ne pas plus se sa son ses leur leurs il elle on nous vous "
    "the of and or to in is are for on with by an be this that it as at from".split()
)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _stem(t: str) -> str:
    """Racinisation minimale du pluriel : secrets -> secret (acces, process inchangés)."""
    return t[:-1] if len(t) > 4 and t[-1] == "s" and t[-2] not in "seiu" else t


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall(_normalize(text)) if t not in _STOP]


@dataclass(frozen=True)
class Chunk:
    source: str
    text: str


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


def chunk_markdown(source: str, text: str, max_chars: int = 800) -> list[Chunk]:
    """Découpe par paragraphes, regroupés jusqu'à max_chars."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[Chunk] = []
    buf = ""
    for p in paras:
        if buf and len(buf) + len(p) > max_chars:
            chunks.append(Chunk(source, buf))
            buf = p
        else:
            buf = f"{buf}\n\n{p}" if buf else p
    if buf:
        chunks.append(Chunk(source, buf))
    return chunks


class TfidfRetriever:
    def __init__(self, chunks: list[Chunk]):
        if not chunks:
            raise ValueError("aucun document indexé")
        self.chunks = chunks
        docs = [tokenize(c.text) for c in chunks]
        vocab = sorted({t for d in docs for t in d})
        self.index = {t: i for i, t in enumerate(vocab)}
        n = len(docs)
        tf = np.zeros((n, len(vocab)), dtype=np.float32)
        for row, d in enumerate(docs):
            for t in d:
                tf[row, self.index[t]] += 1.0
        df = (tf > 0).sum(axis=0)
        self.idf = np.array([math.log((1 + n) / (1 + x)) + 1.0 for x in df], dtype=np.float32)
        m = tf * self.idf
        norms = np.linalg.norm(m, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.matrix = m / norms

    @classmethod
    def from_directory(cls, path: str | Path) -> "TfidfRetriever":
        chunks: list[Chunk] = []
        for f in sorted(Path(path).glob("*.md")):
            chunks.extend(chunk_markdown(f.name, f.read_text(encoding="utf-8")))
        return cls(chunks)

    def search(self, query: str, k: int = 3) -> list[Hit]:
        q = np.zeros(len(self.index), dtype=np.float32)
        for t in tokenize(query):
            i = self.index.get(t)
            if i is not None:
                q[i] += 1.0
        q *= self.idf
        norm = np.linalg.norm(q)
        if norm == 0:
            return []
        scores = self.matrix @ (q / norm)
        order = np.argsort(-scores)[:k]
        return [Hit(self.chunks[i], float(scores[i])) for i in order if scores[i] > 0]
