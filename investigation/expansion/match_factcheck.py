"""Casa as linhas da v2 contra o corpus ClaimReview (feed Data Commons).

Por que nao usar a API: `claims:search` e um *indice de checagens publicadas*
(parametros query/reviewPublisherSiteFilter), nao um verificador que recebe uma
frase e devolve fato/fake. A API nao checa uma alegacao; ela procura reviews ja
publicados. O feed do Data Commons e o dump em massa desse mesmo indice.

Estrategia (offline, cobre "todas" as linhas):
  1. indice exato de `claimReviewed` normalizado;
  2. indice invertido por palavra (>=4 letras, sem stopwords) para candidatos;
  3. confirma por Jaccard de palavras ou contencao >= `--threshold`.
Saida: `FakenewsBR_v2_factcheck_matches.csv` (soh linhas com match) com
rid, texto, claim casada, rating, label inferido, publisher, url, score e
`concorda` (com o rotulo atual da v2), alem de um resumo por dataset.

Para atualizar o indice com checagens novas (pos-snapshot do feed), rode antes
`python -m investigation.expansion.collect_gfc` com GOOGLE_FACTCHECK_API_KEY:
o `gfc.jsonl` gerado e incluido automaticamente.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from . import dedup as dd
from . import schema as sch

RAW = Path("investigation/expansion/raw")
STOP = set("""a o e de da do das dos em no na nos nas um uma para por com que se
sobre entre apos apos ate como mais menos muito pouco ja nao sim the of and to in
for on with is are was were this that from by as at be or an it its""".split())


def _tokens(text: str) -> list[str]:
    return [w for w in dd.normalize_text(text).split()
            if len(w) >= 4 and w not in STOP]


def load_index(paths: list[Path]) -> tuple[dict, dict, list]:
    """(exato: key->list[review], invertido: word->set[i], reviews: list)."""
    exact: dict[str, list[int]] = defaultdict(list)
    inv: dict[str, set[int]] = defaultdict(set)
    reviews: list[dict] = []
    for p in paths:
        if not p.exists():
            continue
        with p.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                claim = r.get("claimReviewed") or ""
                rating = r.get("rating") or ""
                label = sch.label_of_rating(rating)
                if label is None or not claim:
                    continue
                i = len(reviews)
                reviews.append({"claim": claim, "rating": rating,
                                "label": label,
                                "publisher": r.get("publisher") or r.get("dataset_name") or "",
                                "url": r.get("url") or ""})
                exact[dd.normalize_text(claim)].append(i)
                for w in set(_tokens(claim)):
                    inv[w].add(i)
    return exact, inv, reviews


def match_row(text: str, exact, inv, reviews, threshold: float) -> dict | None:
    key = dd.normalize_text(text)
    if key in exact:
        i = exact[key][0]
        return {**reviews[i], "score": 1.0}
    toks = set(_tokens(text))
    if not toks:
        return None
    cand: Counter[int] = Counter()
    for w in toks:
        for i in inv.get(w, ()):
            cand[i] += 1
    best, best_score = None, 0.0
    for i, shared in cand.most_common(50):
        if shared < 2:
            continue
        rt = set(_tokens(reviews[i]["claim"]))
        if not rt:
            continue
        inter = len(toks & rt)
        jac = inter / len(toks | rt)
        cont = inter / min(len(toks), len(rt))
        score = max(jac, cont)
        if score > best_score:
            best, best_score = i, score
    if best is None or best_score < threshold:
        return None
    return {**reviews[best], "score": round(best_score, 3)}


def run(v2: Path, out: Path, threshold: float) -> dict:
    v1 = pd.read_csv("FakenewsBR_sanitized.csv", low_memory=False, usecols=["rid"])
    df = pd.read_csv(v2, low_memory=False)
    new = df.iloc[len(v1):].copy()
    paths = [RAW / "feed.jsonl", RAW / "gfc.jsonl", RAW / "gfc_afp.jsonl"]
    exact, inv, reviews = load_index(paths)
    print(f"indice: {len(reviews):,} checagens publicadas")

    rows = []
    for r in new.itertuples(index=False):
        m = match_row(str(r.text_no_url), exact, inv, reviews, threshold)
        if m:
            rows.append({
                "rid": int(r.rid), "dataset_name": r.dataset_name,
                "label_v2": r.label, "text": str(r.text_no_url)[:200],
                "matched_claim": m["claim"][:200], "rating": m["rating"],
                "label_factcheck": m["label"], "publisher": m["publisher"],
                "url": m["url"], "score": m["score"],
                "concorda": int(r.label == m["label"]),
            })
    got = pd.DataFrame(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    got.to_csv(out, index=False)
    resumo = {
        "n_novas": int(len(new)),
        "n_casadas": int(len(got)),
        "cobertura_pct": round(len(got) / max(len(new), 1) * 100, 2),
        "concordancia_pct": round(float(got["concorda"].mean() * 100), 1)
        if len(got) else None,
        "por_dataset": got["dataset_name"].value_counts().to_dict() if len(got) else {},
        "por_score": got["score"].round(1).value_counts().sort_index().to_dict()
        if len(got) else {},
    }
    print(json.dumps(resumo, ensure_ascii=False, indent=1))
    out.with_suffix(".json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    return resumo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v2", type=Path, default=Path("FakenewsBR_sanitized_v2.csv"))
    ap.add_argument("--out", type=Path,
                    default=Path("FakenewsBR_v2_factcheck_matches.csv"))
    ap.add_argument("--threshold", type=float, default=0.5)
    a = ap.parse_args()
    run(a.v2, a.out, a.threshold)


if __name__ == "__main__":
    main()
