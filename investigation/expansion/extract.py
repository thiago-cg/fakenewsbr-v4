"""Extracao: raw/*.jsonl -> processed/records.jsonl (registros canonicos).

Regras por fonte (ver `investigation/expansion/README.md`):
  - Boatos    : claim = texto apos "Boato -"; viral = 1o <blockquote>.
  - E-farsas  : veredito por categoria; claim = titulo sem "E verdade que".
  - Bereia    : veredito por tag.
  - G1        : h1 "E #FAKE que X" / "E #FATO ..."; multi-alegacao e pulado.
  - Poligrafo : veredito do span `fact-check-result`; claim = og:title sem sufixo.
  - Feed      : claimReviewed + rating; claimant do itemReviewed.author.
  - NEWS      : manchete (6-40 palavras), label true, label_source=provenance.

Filtro de vazamento: descarta fragmentos escritos pelo checador que citam
fake/falso/boato/etc. NAO se aplica a textos virais.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from . import schema as sch
from .sources import ALL_SOURCES

RAW = Path("investigation/expansion/raw")
PROC = Path("investigation/expansion/processed")

LEAK_RE = re.compile(
    r"\b(fake|falso|falsa|boato|mentira|mentiroso|farsa|verdadeiro|verdadeira|"
    r"enganoso|enganador|checagem|checado|fact[- ]?check|#fato|#fake|desment|"
    r"e falso|é falso|e fake|é fake)\b", re.IGNORECASE)


def norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", s or "")
                if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


def is_leaky(text: str) -> bool:
    return bool(LEAK_RE.search(text or ""))


def _first_sentence(s: str, max_len: int = 320) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    m = re.match(r"(.{20,%d}?[\.\!\?])(\s|$)" % max_len, s)
    if m:
        return m.group(1).strip(" .")
    return s[:max_len].strip(" .")


def _html_unescape(s: str) -> str:
    import html
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _record(rec: dict, text: str, label: str, text_role: str,
            dataset: str | None = None, rating: str = "",
            claimant: str = "", url_review: str | None = None,
            source_type: str | None = None) -> dict | None:
    text = (text or "").strip()
    if len(text) < 15:
        return None
    url = url_review or rec.get("link") or rec.get("url") or ""
    role = text_role
    rid = sch.make_rid(url, role, rec.get("id") or url)
    r = sch.Record(
        rid=rid,
        dataset_name=dataset or rec.get("dataset_name") or "FC_UNKNOWN",
        source_type=source_type or rec.get("source_type") or "news",
        source_description=rec.get("publisher") or rec.get("source") or "",
        label=label,
        date_iso=(rec.get("date_iso") or None),
        url_review=url,
        text=text,
        factcheck_rating=rating or rec.get("rating", ""),
        factcheck_claimant=claimant or rec.get("claimant", ""),
        factcheck_url=url,
        label_source=rec.get("label_source", "rating"),
        text_role=role,
        publisher=rec.get("publisher") or rec.get("source") or "",
        lang_variant=rec.get("lang_variant", "pt-BR"),
        collector=rec.get("collector", ""),
        source_url=url,
        collected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        mentions_ai=int(sch.mentions_ai(text)),
    )
    try:
        r.finalize()
    except ValueError:
        return None
    row = r.csv_row()
    row["_provenance"] = r.prov_row(rec.get("collector", ""))
    return row


# ------------------------------------------------------------------ fontes

def extract_feed(rec: dict) -> list[dict]:
    label = sch.label_of_rating(rec.get("rating"))
    if label is None:
        return []
    claim = rec.get("claimReviewed", "")
    if is_leaky(claim):
        return []
    out = _record(rec, claim, label, "claim", source_type="news")
    return [out] if out else []


def extract_boatos(rec: dict) -> list[dict]:
    out = []
    content = rec.get("content", "")
    title = rec.get("title", "")
    m = re.search(r"Boato\s*[–\-—:]\s*(.+)", content, flags=re.I | re.S)
    claim = _first_sentence(m.group(1) if m else "") or _first_sentence(title)
    if not is_leaky(claim):
        r = _record(rec, claim, "fake", "claim", dataset="FC_BOATOS",
                    rating="Falso", source_type="news")
        if r:
            out.append(r)
    # viral: 1o blockquote
    bh = re.search(r"<blockquote[^>]*>(.*?)</blockquote>", rec.get("content_html", ""),
                   flags=re.S | re.I)
    if bh:
        viral = _html_unescape(bh.group(1))
        viral = re.sub(r"^\s*vers[ãa]o\s*\d+\s*[:\-–]\s*", "", viral, flags=re.I)
        r = _record(rec, viral, "fake", "viral", dataset="FC_BOATOS_VIRAL",
                    rating="Falso", source_type="social media post")
        if r:
            out.append(r)
    return out


def extract_efarsas(rec: dict) -> list[dict]:
    cats = [norm(c) for c in rec.get("categories", [])]
    priority = [("falso", "Falso", "fake"), ("fora de contexto", "Fora de Contexto", "fake"),
                ("impreciso", "Impreciso", "fake"), ("indeterminado", "Indeterminado", None),
                ("verdadeiro", "Verdadeiro", "true")]
    verdict, rating, label = None, "", None
    for key, rat, lab in priority:
        if any(key == c or key in c for c in cats):
            verdict, rating, label = key, rat, lab
            break
    if verdict is None or label is None:
        return []
    title = rec.get("title", "")
    claim = re.sub(r"^(é|e|será|sera|sera que|é verdade que|e verdade que)\s*", "", title,
                   flags=re.I).strip(" ?!.")
    if is_leaky(claim):
        return []
    r = _record(rec, claim, label, "claim", dataset="FC_EFARSAS", rating=rating)
    return [r] if r else []


def extract_bereia(rec: dict) -> list[dict]:
    tags = [norm(t) for t in rec.get("tags", [])]
    cats = [norm(c) for c in rec.get("categories", [])]
    if not any(c == "checamos" or "checamos" in c for c in cats):
        return []
    verdict, rating, label = None, "", None
    for key, rat, lab in [("enganoso", "Enganoso", "fake"), ("falso", "Falso", "fake"),
                          ("impreciso", "Impreciso", "fake"),
                          ("verdadeiro", "Verdadeiro", "true")]:
        if any(key == t or key in t for t in tags):
            verdict, rating, label = key, rat, lab
            break
    if label is None:
        return []
    claim = rec.get("title", "").strip(" ?!.")
    if is_leaky(claim):
        return []
    r = _record(rec, claim, label, "claim", dataset="FC_BEREIA", rating=rating)
    return [r] if r else []


_G1_MULTI = re.compile(r"veja o que|o que é fato|o que e fato|#fato e #fake|"
                       r"fato ou fake|confira", re.I)


def extract_g1(rec: dict) -> list[dict]:
    h1 = rec.get("h1", "")
    if not h1 or _G1_MULTI.search(h1):
        return []
    if re.search(r"#?fake", h1, re.I):
        label, rating = "fake", "FAKE"
    elif re.search(r"#?fato", h1, re.I):
        label, rating = "true", "FATO"
    else:
        return []
    claim = re.sub(r"^[ée]\s*#?(fake|fato)\s*(que\s*)?", "", h1, flags=re.I).strip(" ?!.-")
    if not claim or is_leaky(claim):
        return []
    r = _record(rec, claim, label, "claim", dataset="FC_G1", rating=rating,
                source_type="news")
    return [r] if r else []


def extract_poligrafo(rec: dict) -> list[dict]:
    label = sch.label_of_rating(rec.get("verdict") or rec.get("og_title"))
    if label is None:
        return []
    title = rec.get("og_title") or rec.get("h1") or ""
    claim = re.sub(r"\s*[-|]\s*Pol[íi]grafo\s*$", "", title, flags=re.I).strip(" ?!.")
    if is_leaky(claim):
        return []
    r = _record(rec, claim, label, "claim", dataset="FC_POLIGRAFO",
                rating=rec.get("verdict", ""), source_type="news")
    return [r] if r else []


def extract_news(rec: dict) -> list[dict]:
    title = (rec.get("title") or "").strip()
    n_words = len(title.split())
    if n_words < 6 or n_words > 40:
        return []
    if is_leaky(title):
        return []
    r = _record(rec, title, "true", "headline",
                source_type="news headline", rating="",
                url_review=rec.get("link", ""))
    return [r] if r else []


EXTRACTORS = {
    "boatos": extract_boatos, "efarsas": extract_efarsas, "bereia": extract_bereia,
    "g1": extract_g1, "poligrafo": extract_poligrafo,
}
PORTAL_KEYS = {"poder360", "cnnbrasil", "brasildefato", "oeco", "eco"}


def extract_all(raw_dir: Path, out: Path) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    stats: dict[str, dict] = {}
    seen_rid = set()
    n = 0
    with out.open("w", encoding="utf-8") as fo:
        for path in sorted(raw_dir.glob("*.jsonl")):
            source = path.stem
            s = stats.setdefault(source, {"raw": 0, "kept": 0})
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # linha parcial (arquivo sendo escrito)
                    s["raw"] += 1
                    if source in ("feed", "gfc") or source.startswith("gfc"):
                        # gfc*.jsonl ja vem canonico (com _provenance) do
                        # collect_gfc; feed.jsonl vem bruto do collect_feed
                        if source.startswith("gfc") and "_provenance" in rec and rec.get("label") in ("fake", "true"):
                            rows = [rec]
                        else:
                            rows = extract_feed(rec)
                    elif source in EXTRACTORS:
                        rows = EXTRACTORS[source](rec)
                    elif source in PORTAL_KEYS:
                        rows = extract_news(rec)
                    else:
                        rows = []
                    for row in rows:
                        if row["rid"] in seen_rid:
                            continue
                        seen_rid.add(row["rid"])
                        fo.write(json.dumps(row, ensure_ascii=False) + "\n")
                        n += 1
                        s["kept"] += 1
            print(f"[extract] {source}: {s['kept']}/{s['raw']}", flush=True)
    print(f"[extract] total {n} registros -> {out}", flush=True)
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", type=Path, default=RAW)
    ap.add_argument("--out", type=Path, default=PROC / "records.jsonl")
    a = ap.parse_args()
    st = extract_all(a.raw_dir, a.out)
    print(json.dumps(st, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
