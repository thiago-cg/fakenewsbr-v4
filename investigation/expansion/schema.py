"""Schema do FakenewsBR v2 + derivacoes compativeis com a v1.

Este modulo e a fonte unica de verdade para:

  - as 23 colunas do CSV final (mesma ordem da v1);
  - as 10 colunas do CSV de proveniencia;
  - a derivacao de `text_clean`, `text_no_url`, `extracted_urls`;
  - as metricas de estilo, identicas a `sanitize_dataset.py` (que gerou a v1);
  - o mapeamento de ratings PT -> {false_pure, hard, true_rating, other};
  - a geracao de `rid` (int64, sha1 de 15 hex, sem colisao pratica com a v1).

Regra de rotulo (herdada de `models/data.py::_rating_class`):
    false_pure -> fake     (Falso, Errado, Mentira, ...)
    hard       -> fake     (Enganoso, Distorcido, Sem contexto, ...)
    true_rating-> true     (Verdadeiro, Certo, ...)
    other      -> descarta (Explica, Contextualizando, Indeterminado, ...)
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

COLUMNS = [
    "rid", "dataset_name", "source_type", "source_description", "label",
    "date_iso", "url_review", "text", "text_clean", "text_no_url",
    "extracted_urls", "is_duplicated", "is_null", "too_short",
    "factcheck_rating", "factcheck_claimant", "factcheck_url",
    "char_len", "word_len", "num_exclamations", "num_questions",
    "num_ellipsis", "uppercase_word_ratio",
]

PROVENANCE_COLUMNS = [
    "rid", "label_source", "text_role", "publisher", "lang_variant",
    "collector", "source_url", "collected_at", "rating_norm", "mentions_ai",
]

# --------------------------------------------------------------------------
# Ratings -> classes canonicas
# --------------------------------------------------------------------------
# false_pure -> label=fake
FALSE_PURE = {
    "falso", "falsa", "errado", "errada", "mentira", "fake", "mentiroso",
    "montagem", "montagem.", "insustentavel", "sem registro", "satira",
    "manipulado", "manipulada", "pants on fire", "incorrect", "false",
    "falso.", "fake.", "errado.", "a sos", "impossivel", "forjado",
    "fabricado", "mentira.", "nao e verdade", "nao procede", "desmentido",
}
# hard -> label=fake (a v1 trata hard como fake)
HARD = {
    "enganoso", "enganosa", "enganador", "distorcido", "distorcida",
    "sem contexto", "fora de contexto", "descontextualizado",
    "descontextualizada", "exagerado", "exagerada", "impreciso", "imprecisa",
    "esticado", "nao_e_bem_assim", "nao e bem assim", "verdadeiro, mas",
    "verdadeiro mas", "verdadeiro, mas...", "subestimado", "superestimado",
    "pimenta na lingua", "pimenta na língua", "misleading", "missing context",
    "out of context", "unverified", "mixed", "exaggerated", "partly false",
    "half true", "mais ou menos", "parcialmente", "meia verdade",
}
# true_rating -> label=true
TRUE_RATING = {
    "verdadeiro", "verdadeira", "true", "certo", "certa", "correct",
    "praticamente certo", "praticamente verdadeiro", "verified", "comprovado",
    "comprovada", "accurate", "vdd", "verdade", "confirmado",
}
# other -> descarta (nao vira linha)
OTHER = {
    "explica", "explicacao", "contextualizando", "contexto", "ainda e cedo",
    "ainda é cedo", "indeterminado", "indeterminada", "de olho",
    "contraditorio", "contraditória", "contraditoria", "inconclusivo",
    "sem veredito", "nao avaliado", "em analise", "checando", "duvidoso",
    "suspeito", "questionavel", "aguardando", "unrated", "no rating",
}

# ratings que explicitamente sao "verdadeiro, mas ..." em PT -> hard
_VERDADEIRO_MAIS = re.compile(r"^\s*verdadeir[oa]\s*,?\s*mas\b", re.IGNORECASE)


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def normalize_rating(raw: str | None) -> str:
    """Normaliza o rating bruto: tira acento, caixa extra, pega token antes de ':'/'-'.

    Ratings do feed vem como "FALSO: explicacao longa" ou "Verdadeiro - texto".
    O veredito e o token inicial.
    """
    if not raw or not isinstance(raw, str):
        return ""
    s = raw.strip()
    # token antes do primeiro ':' ou ' - ' (mantendo hifens internos como "e-farsas")
    head = re.split(r":|\s[-–—]\s", s, maxsplit=1)[0].strip()
    # se sobrou algo muito curto, tenta o texto todo
    if len(head) < 3:
        head = s
    s = _strip_accents(head.lower())
    s = re.sub(r"[\.\!\?]+$", "", s).strip()
    return s


def rating_to_class(raw: str | None) -> str:
    """Classifica um rating bruto em false_pure | hard | true_rating | other."""
    k = normalize_rating(raw)
    if not k:
        return "other"
    if k in HARD or _VERDADEIRO_MAIS.match(k):
        return "hard"
    if k in FALSE_PURE:
        return "false_pure"
    if k in TRUE_RATING:
        return "true_rating"
    # prefixos comuns: "verdadeiro, mas..." ja coberto; "falso - ..." ja tokenizado
    if k.startswith("fals") or k.startswith("engan") or k.startswith("distorc"):
        return "false_pure" if k.startswith("fals") else "hard"
    if k.startswith("verdadeir") or k.startswith("cert"):
        return "true_rating"
    return "other"


def label_of_rating(raw: str | None) -> str | None:
    """Retorna 'fake' | 'true' | None (descarta)."""
    c = rating_to_class(raw)
    if c in ("false_pure", "hard"):
        return "fake"
    if c == "true_rating":
        return "true"
    return None


# --------------------------------------------------------------------------
# Derivacoes de texto (compatibilidade v1)
# --------------------------------------------------------------------------
# A v1 foi gerada pelo framework AKCIT-FN/fakenews-data:
#   text_no_url, extracted_urls = remove_urls(text)
#   text_clean = clean_for_factcheck(text_no_url)
# i.e. text_clean parte do texto SEM URL. Reproduzimos a semantica do
# framework (emoji -> aspas retas externas -> NFD sem marcas -> minusculas ->
# espacos), medida em 98,56% de paridade contra as 39.466 linhas da v1
# (o restante diferenca vem de demoji/urlextract exatos).
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_WS_RE = re.compile(r"\s+")
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"      # emojis/simbolos pictograficos
    "\U00002600-\U000027BF"      # misc symbols / dingbats
    "\U0001F1E6-\U0001F1FF"      # bandeiras
    "\U00002B00-\U00002BFF"      # setas/simbolos
    "\U0000FE00-\U0000FE0F"      # variation selectors
    "\U0000200D"                 # zero width joiner
    "]+", flags=re.UNICODE)
_OUTER_QUOTES = ("\"", "'")


def make_text_clean(text: str) -> str:
    """minúsculas + sem acento + espaços colapsados (semântica da v1).

    Aplicar SEMPRE ao `text_no_url` para reproduzir a v1 (ver `finalize`).
    """
    if not isinstance(text, str):
        return ""
    s = _EMOJI_RE.sub("", text)
    s = s.strip()
    if len(s) >= 2 and s[0] in _OUTER_QUOTES and s[-1] == s[0]:
        s = s[1:-1].strip()
    s = "".join(c for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn")
    return _WS_RE.sub(" ", s.lower()).strip()


def make_text_no_url(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return _URL_RE.sub("", text).strip()


def extract_urls(text: str) -> str:
    """Formato da v1: repr de lista Python (ex.: `['https://x']`)."""
    if not isinstance(text, str):
        return "[]"
    return repr(re.findall(r"https?://\S+", text))


def compute_metrics(text: str, text_clean: str | None = None) -> dict[str, int | float]:
    """Metricas identicas a sanitize_dataset.py.

    char_len/word_len usam `text_clean`; pontuacao e caixa usam `text`.
    """
    if text_clean is None:
        text_clean = make_text_clean(text)
    text_clean = text_clean or ""
    if not isinstance(text, str):
        text = ""
    words = re.findall(r"\b[A-Za-zÀ-ÖØ-öø-ÿ]+\b", text)
    n_words = len(words)
    upper = sum(1 for w in words if len(w) >= 3 and w.isupper())
    return {
        "char_len": len(text_clean),
        "word_len": len(text_clean.split()),
        "num_exclamations": len(re.findall(r"!", text)),
        "num_questions": len(re.findall(r"\?", text)),
        "num_ellipsis": len(re.findall(r"\.{3,}|\u2026", text)),
        "uppercase_word_ratio": (upper / n_words) if n_words else 0.0,
    }


# --------------------------------------------------------------------------
# rid
# --------------------------------------------------------------------------
def make_rid(url: str, text_role: str, i: int | str) -> int:
    """int64 estavel; 15 hex chars (~60 bits) evitam colisao com a v1 (<=51.204)."""
    key = f"{url or ''}|{text_role or ''}|{i}"
    h = hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()[:15]
    return int(h, 16)


def mentions_ai(text: str) -> bool:
    return bool(re.search(
        r"\b(ia|intelig[êe]ncia artificial|deepfake|deep fake|chatgpt|gpt|"
        r"dall-?e|midjourney|stable diffusion|gerad[oa] por (ia|computador)|"
        r"imagem gerada|v[íi]deo gerado|bot|algoritmo)\b",
        text or "", flags=re.IGNORECASE))


# --------------------------------------------------------------------------
# Registro canonico
# --------------------------------------------------------------------------
@dataclass
class Record:
    rid: int
    dataset_name: str
    source_type: str
    source_description: str
    label: str
    date_iso: str | None
    url_review: str
    text: str
    factcheck_rating: str = ""
    factcheck_claimant: str = ""
    factcheck_url: str = ""
    is_duplicated: int = 0
    is_null: int = 0
    too_short: int = 0
    label_source: str = "rating"
    text_role: str = "claim"
    publisher: str = ""
    lang_variant: str = "pt-BR"
    collector: str = ""
    source_url: str = ""
    collected_at: str = ""
    mentions_ai: int = 0

    def finalize(self) -> "Record":
        self.text = (self.text or "").strip()
        if not self.text:
            raise ValueError("texto vazio")
        # ordem do framework: text_no_url -> text_clean (compatibilidade v1)
        self.text_no_url = make_text_no_url(self.text)
        self.text_clean = make_text_clean(self.text_no_url)
        self.extracted_urls = extract_urls(self.text)
        m = compute_metrics(self.text, self.text_clean)
        for k, v in m.items():
            setattr(self, k, v)
        if not self.date_iso:
            self.date_iso = None
        return self

    @property
    def rating_norm(self) -> str:
        return normalize_rating(self.factcheck_rating)

    def csv_row(self) -> dict[str, Any]:
        return {c: getattr(self, c, "") for c in COLUMNS}

    def prov_row(self, collector: str) -> dict[str, Any]:
        return {
            "rid": self.rid,
            "label_source": self.label_source,
            "text_role": self.text_role,
            "publisher": self.publisher,
            "lang_variant": self.lang_variant,
            "collector": collector or self.collector,
            "source_url": self.source_url or self.url_review,
            "collected_at": self.collected_at,
            "rating_norm": self.rating_norm,
            "mentions_ai": int(self.mentions_ai),
        }
