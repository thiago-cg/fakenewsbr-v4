"""Deduplicacao exata + quase-duplicata (MinHash LSH) para a expansao v2.

Duas camadas:

1. **Exata**: chave normalizada (minuscula, sem acento, so alfanumerico) do
   `text_no_url`. Igualdade -> duplicata.
2. **Quase**: assinatura MinHash (blake2b estavel) sobre shingles; textos com
   >= 20 palavras usam 3-shingles de palavra, textos curtos usam 5-gramas de
   caractere. LSH em bandas gera candidatos; o par candidato so e confirmado
   se a Jaccard exata (sobre os conjuntos de shingles) for >= `threshold`.

Precedencia (mantem a linha de maior prioridade):
    v1 (1) > rating/veredito (2) > procedencia (3) > data mais antiga (4).

Nao depende de sklearn/faiss; so numpy + stdlib.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np

# ----------------------------------------------------------------- normalizacao
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")


def normalize_text(s: str) -> str:
    """Minuscula, sem acento, apenas [a-z0-9 ] colapsado."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = _NON_ALNUM.sub(" ", s)
    return _WS.sub(" ", s).strip()


# --------------------------------------------------------------------- shingles
def _shingle_hashes(text: str) -> set[int]:
    words = normalize_text(text).split()
    if len(words) >= 20:
        grams = [" ".join(words[i:i + 3]) for i in range(len(words) - 2)]
    else:
        norm = normalize_text(text).replace(" ", "")
        if len(norm) < 5:
            grams = [norm] if norm else []
        else:
            grams = [norm[i:i + 5] for i in range(len(norm) - 4)]
    out = set()
    for g in grams:
        if not g:
            continue
        out.add(int.from_bytes(
            hashlib.blake2b(g.encode("utf-8"), digest_size=8).digest(), "little"))
    return out


def _raw_hashes(text: str) -> np.ndarray:
    """Hashes de shingle dobrados para uint32 (seguro para a aritmetica modular)."""
    hs = _shingle_hashes(text)
    if not hs:
        return np.zeros(0, dtype=np.uint64)
    arr = np.fromiter(hs, dtype=np.uint64, count=len(hs))
    return (arr ^ (arr >> np.uint64(32))) & np.uint64(0xFFFFFFFF)


# --------------------------------------------------------------- MinHash params
NUM_PERM = 64
BANDS = 8
ROWS = NUM_PERM // BANDS          # 8 -> limiar teorico (1/8)^(1/8) ~= 0,77
_PRIME = (1 << 31) - 1            # primo de Mersenne: a*h+b cabe em uint64
_RNG = np.random.default_rng(20260910)
_A = _RNG.integers(1, _PRIME - 1, size=NUM_PERM, dtype=np.uint64)
_B = _RNG.integers(0, _PRIME - 1, size=NUM_PERM, dtype=np.uint64)


def minhash(text: str) -> np.ndarray:
    """Assinatura MinHash de NUM_PERM posicoes (uint64)."""
    h = _raw_hashes(text)
    if h.size == 0:
        return np.full(NUM_PERM, _PRIME, dtype=np.uint64)
    a = _A[:, None]
    b = _B[:, None]
    hh = h[None, :]
    vals = (a * hh + b) % np.uint64(_PRIME)
    return vals.min(axis=1)


def jaccard(text_a: str, text_b: str) -> float:
    sa, sb = _shingle_hashes(text_a), _shingle_hashes(text_b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# ------------------------------------------------------------------- indice LSH
@dataclass
class Deduplicator:
    threshold: float = 0.90

    _buckets: dict[tuple[int, bytes], list[int]] = field(default_factory=dict)
    _texts: list[str] = field(default_factory=list)
    _keys: list[str] = field(default_factory=list)

    def _bands(self, sig: np.ndarray):
        for bidx in range(BANDS):
            chunk = sig[bidx * ROWS:(bidx + 1) * ROWS]
            yield (bidx, chunk.tobytes())

    def _candidates(self, text: str) -> set[int]:
        sig = minhash(text)
        cands: set[int] = set()
        for key in self._bands(sig):
            cands.update(self._buckets.get(key, ()))
        return cands

    def find_near(self, text: str, exclude: int | None = None) -> list[int]:
        """Candidatos indexados com igualdade normalizada ou Jaccard >= threshold."""
        key = normalize_text(text)
        out = []
        for i in self._candidates(text):
            if exclude is not None and i == exclude:
                continue
            if self._keys[i] == key or jaccard(text, self._texts[i]) >= self.threshold:
                out.append(i)
        return out

    def add(self, text: str) -> int:
        """Indexa `text`; retorna o indice local."""
        idx = len(self._texts)
        self._texts.append(text)
        self._keys.append(normalize_text(text))
        for key in self._bands(minhash(text)):
            self._buckets.setdefault(key, []).append(idx)
        return idx


# ------------------------------------------------------------------ utilidades
def content_hash(rows) -> str:
    """Hash estavel de uma sequencia de (rid, text_no_url) para asserts da v1."""
    h = hashlib.sha256()
    for rid, text in rows:
        h.update(str(int(rid)).encode())
        h.update(b"\x00")
        h.update(normalize_text(str(text)).encode("utf-8"))
        h.update(b"\x01")
    return h.hexdigest()
