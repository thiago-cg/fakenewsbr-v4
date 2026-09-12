"""Merges the expansion records into FakenewsBR_sanitized_v2.csv + audit.

Regras centrais:
  - a v1 (`FakenewsBR_sanitized.csv`) e copiada INTACTA (mesmos valores, mesmas
    linhas). Nunca e re-sanitizada nem deduplicada. Um assert por hash de
    conteudo confirma isso;
  - as linhas novas passam por dedup exata + quase-duplicata contra a v1 e
    entre si (precedencia: v1 > rating > procedencia > data mais antiga);
  - cota de manchetes (`NEWS_*`) por era controlada por `--news-max-ratio`;
  - saem `FakenewsBR_sanitized_v2.csv` (23 colunas) e
    `FakenewsBR_v2_provenance.csv` (metadados das linhas novas), alem de
    `audit_v2.md/json`.

Uso:
    python -m investigation.expansion.merge_and_audit \
        --records investigation/expansion/processed/records.jsonl \
        --original FakenewsBR_sanitized.csv \
        --out FakenewsBR_sanitized_v2.csv
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from . import dedup as dd

COLUMNS = [
    "rid", "dataset_name", "source_type", "source_description", "label",
    "date_iso", "url_review", "text", "text_clean", "text_no_url",
    "extracted_urls", "is_duplicated", "is_null", "too_short",
    "factcheck_rating", "factcheck_claimant", "factcheck_url",
    "char_len", "word_len", "num_exclamations", "num_questions",
    "num_ellipsis", "uppercase_word_ratio",
]

PROV_COLUMNS = [
    "rid", "label_source", "text_role", "publisher", "lang_variant",
    "collector", "source_url", "collected_at", "rating_norm", "mentions_ai",
]

GPT_CUTOFF = pd.Timestamp("2022-12-01")
ERA_2018 = pd.Timestamp("2018-01-01")


# --------------------------------------------------------------------- carga
def load_records(path: Path | list[Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Le um ou mais JSONL canonicos; retorna (linhas_v2, proveniencia)."""
    paths = [path] if isinstance(path, (str, Path)) else list(path)
    rows, prov = [], []
    for p in paths:
        p = Path(p)
        if not p.exists():
            continue
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                pr = r.pop("_provenance", {}) or {}
                rows.append(r)
                prov.append({c: pr.get(c, "") for c in PROV_COLUMNS})
    df = pd.DataFrame(rows)
    pf = pd.DataFrame(prov)
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = ""
    for c in PROV_COLUMNS:
        if c not in pf.columns:
            pf[c] = ""
    df = df[COLUMNS].copy()
    df["_label_source"] = pf["label_source"].values
    return df, pf[PROV_COLUMNS]


def _era(date_iso) -> str:
    ts = pd.to_datetime(date_iso, errors="coerce")
    if pd.isna(ts):
        return "sem_data"
    if ts < ERA_2018:
        return "ate_2017"
    if ts < GPT_CUTOFF:
        return "2018_2022"
    return "pos_gpt35"


# --------------------------------------------------------------------- dedup
def _priority(label_source) -> int:
    """Menor = mais prioritario. Rating vence procedencia."""
    return 1 if str(label_source) == "rating" else 2


def dedup_new(df: pd.DataFrame, v1_texts: list[str],
              conflict_path: Path | None, near: bool = True) -> pd.DataFrame:
    """Remove duplicatas contra a v1 e entre as novas, com log de conflitos.

    Espera a coluna auxiliar `_label_source` (rating|provenance).
    """
    if df.empty:
        return df
    df = df.copy()
    df["_key"] = df["text_no_url"].astype(str).map(dd.normalize_text)
    df["_date"] = pd.to_datetime(df["date_iso"], errors="coerce")

    # v1 indexada (exata + LSH)
    v1_keys = {dd.normalize_text(t) for t in v1_texts}
    v1_dedup = dd.Deduplicator()
    for t in v1_texts:
        v1_dedup.add(t)

    if "_label_source" in df.columns:
        df["_prio"] = df["_label_source"].map(_priority)
    else:
        df["_prio"] = 1
    df = df.sort_values(["_prio", "_date"], kind="stable",
                        na_position="last").reset_index(drop=True)

    accepted = dd.Deduplicator()
    keep_idx: list[int] = []
    conflicts = Counter()
    conflict_rows: list[dict] = []

    for i, row in df.iterrows():
        key = row["_key"]
        text = str(row["text_no_url"])
        reason = None
        # 1) exato contra v1
        if key in v1_keys:
            reason = "dup_v1_exata"
        elif near:
            hits = v1_dedup.find_near(text)
            if hits:
                reason = "dup_v1_near"
        if reason is None and near:
            hits = accepted.find_near(text)
            if hits:
                reason = "dup_nova_near"
        elif reason is None:
            # modo exato-somente
            pass

        if reason is not None:
            conflicts[reason] += 1
            conflict_rows.append({"rid": row["rid"], "reason": reason,
                                  "label": row["label"], "text": text[:200]})
            continue
        accepted.add(text)
        keep_idx.append(i)

    out = df.loc[keep_idx].drop(columns=["_key", "_prio", "_date"])
    if conflict_path is not None and conflict_rows:
        conflict_path.parent.mkdir(parents=True, exist_ok=True)
        with conflict_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["rid", "reason", "label", "text"])
            w.writeheader()
            w.writerows(conflict_rows)
    out.attrs["conflicts"] = dict(conflicts)
    return out.reset_index(drop=True)


def apply_news_quota(df: pd.DataFrame, ratio: float) -> pd.DataFrame:
    """Limita NEWS_* por era face ao numero de linhas FC_* da mesma era."""
    if ratio is None or df.empty:
        return df
    df = df.copy()
    df["_era"] = df["date_iso"].map(_era)
    is_news = df["dataset_name"].astype(str).str.startswith("NEWS_")
    keep = []
    for era, grp in df.groupby("_era", sort=False):
        n_fc = int((~grp["dataset_name"].astype(str).str.startswith("NEWS_")).sum())
        cap = int(ratio * max(n_fc, 1))
        g_news = grp[is_news.reindex(grp.index)]
        g_other = grp[~is_news.reindex(grp.index)]
        if len(g_news) > cap:
            g_news = g_news.sample(n=cap, random_state=42)
        keep.append(pd.concat([g_other, g_news]))
    out = pd.concat(keep).drop(columns=["_era"]).reset_index(drop=True)
    return out


# --------------------------------------------------------------------- audit
def _composition(df: pd.DataFrame) -> dict:
    d = df.copy()
    d["_era"] = d["date_iso"].map(_era)
    is_verdict = ~d["dataset_name"].astype(str).str.startswith("NEWS_")
    return {
        "n": int(len(d)),
        "label": d["label"].value_counts().to_dict(),
        "veredito_vs_procedencia": {
            "veredito": int(is_verdict.sum()),
            "procedencia": int((~is_verdict).sum()),
        },
        "por_era": {k: int(v) for k, v in d["_era"].value_counts().items()},
        "label_por_era": {
            k: v for k, v in pd.crosstab(d["_era"], d["label"]).to_dict().items()
        },
        "top_datasets": {k: int(v) for k, v in
                         d["dataset_name"].value_counts().head(20).items()},
    }


def audit(df: pd.DataFrame, n_v1: int, provenance: pd.DataFrame | None,
          conflicts: dict) -> dict:
    new = df.iloc[n_v1:]
    comp = _composition(new)
    is_ptpt = (
        new["url_review"].fillna("").str.contains(
            r"poligrafo|observador|eco\.sapo\.pt|publico\.pt|dn\.pt|rtp\.pt",
            case=False, regex=True)
    )
    out = {
        "n_total": int(len(df)),
        "n_v1": int(n_v1),
        "n_new": int(len(new)),
        "composicao_new": comp,
        "ptpt_new": int(is_ptpt.sum()),
        "pct_ptpt_new": round(float(is_ptpt.mean() * 100), 2) if len(new) else 0.0,
        "dedup_conflitos": conflicts,
        "mentions_ai": int(provenance["mentions_ai"].astype(str).eq("1").sum())
        if provenance is not None and len(provenance) else 0,
    }
    return out


def report_md(a: dict) -> str:
    c = a["composicao_new"]
    lines = [
        "# Auditoria FakenewsBR v2", "",
        f"- v1 intacta: {a['n_v1']:,} linhas",
        f"- novas: {a['n_new']:,} linhas",
        f"- total v2: {a['n_total']:,} linhas", "",
        "## Composicao das novas",
        f"- rotulo: {c['label']}",
        f"- veredito vs procedencia: {c['veredito_vs_procedencia']}",
        f"- por era: {c['por_era']}",
        f"- PT-PT: {a['ptpt_new']:,} ({a['pct_ptpt_new']}%)",
        f"- mencoes a IA: {a['mentions_ai']:,}", "",
        "## Datasets (top 20)",
        *[f"- {k}: {v:,}" for k, v in c["top_datasets"].items()], "",
        "## Conflitos de dedup", "```",
        json.dumps(a["dedup_conflitos"], ensure_ascii=False, indent=1),
        "```",
    ]
    return "\n".join(lines)


# ----------------------------------------------------------------------- main
def run(records: Path, original: Path, out: Path, prov_out: Path,
        report: Path, news_ratio: float | None, near: bool = True,
        extras: list[Path] | None = None) -> dict:
    df_v1 = pd.read_csv(original, low_memory=False)
    n_v1 = len(df_v1)
    for c in COLUMNS:
        if c not in df_v1.columns:
            raise SystemExit(f"v1 sem coluna {c}")
    v1_rids = set(int(x) for x in df_v1["rid"])
    v1_hash = dd.content_hash(zip(df_v1["rid"], df_v1["text_no_url"]))
    print(f"v1: {n_v1:,} linhas; hash={v1_hash[:16]}")

    df_new, prov = load_records([records, *(extras or [])])
    print(f"novas brutas: {len(df_new):,}")
    df_new = df_new[df_new["label"].isin(["fake", "true"])].copy()
    df_new = df_new[df_new["text_no_url"].astype(str).str.strip() != ""].copy()
    # paridade com a v1: flags sempre 0 e word_len minimo 3
    for c in ("is_duplicated", "is_null", "too_short"):
        df_new[c] = 0
    wl = pd.to_numeric(df_new["word_len"], errors="coerce").fillna(0)
    df_new = df_new[wl >= 3].copy()
    # nunca colidir rid com a v1
    df_new = df_new[~df_new["rid"].astype("int64").isin(v1_rids)].copy()

    if news_ratio is not None:
        before = len(df_new)
        df_new = apply_news_quota(df_new, news_ratio)
        print(f"cota NEWS ({news_ratio}x): {before:,} -> {len(df_new):,}")

    v1_texts = df_v1["text_no_url"].astype(str).tolist()
    df_new = dedup_new(df_new, v1_texts,
                       conflict_path=report.parent / "conflicts_v2.csv", near=near)
    print(f"apos dedup: {len(df_new):,}")
    conflicts = df_new.attrs.get("conflicts", {})
    # proveniencia so das linhas que realmente entraram na v2
    kept_rids = set(df_new["rid"].astype("int64"))
    prov = prov[prov["rid"].astype("int64").isin(kept_rids)].reset_index(drop=True)

    # monta v2 com a v1 intacta na frente
    df_v2 = pd.concat([df_v1[COLUMNS], df_new[COLUMNS]], ignore_index=True)

    # assert v1 intacta
    after_hash = dd.content_hash(zip(df_v2["rid"].iloc[:n_v1],
                                     df_v2["text_no_url"].iloc[:n_v1]))
    if after_hash != v1_hash:
        raise SystemExit("ERRO: a v1 foi alterada!")
    assert len(set(df_v2["rid"])) == len(df_v2), "rid duplicado na v2"

    out.parent.mkdir(parents=True, exist_ok=True)
    df_v2.to_csv(out, index=False)
    prov_out.parent.mkdir(parents=True, exist_ok=True)
    prov.to_csv(prov_out, index=False)
    print(f"salvo {out} ({len(df_v2):,} linhas)")

    a = audit(df_v2, n_v1, prov, conflicts)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.with_suffix(".json").write_text(
        json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")
    report.write_text(report_md(a), encoding="utf-8")
    print(report_md(a))
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", type=Path,
                    default=Path("investigation/expansion/processed/records.jsonl"))
    ap.add_argument("--original", type=Path, default=Path("FakenewsBR_sanitized.csv"))
    ap.add_argument("--out", type=Path, default=Path("FakenewsBR_sanitized_v2.csv"))
    ap.add_argument("--provenance", type=Path,
                    default=Path("FakenewsBR_v2_provenance.csv"))
    ap.add_argument("--report", type=Path,
                    default=Path("investigation/expansion/audit_v2.md"))
    ap.add_argument("--news-max-ratio", type=float, default=3.0)
    ap.add_argument("--no-near", action="store_true")
    ap.add_argument("--extra", nargs="*", type=Path, default=[])
    a = ap.parse_args()
    run(a.records, a.original, a.out, a.provenance, a.report,
        a.news_max_ratio, near=not a.no_near, extras=a.extra)


if __name__ == "__main__":
    main()
