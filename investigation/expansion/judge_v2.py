"""Juiz/critic da v2: checa o artefato real contra o contrato da v1.

Nao confia em resumo: abre o CSV, recomputa e reporta lacunas.
Saida: `v2_quality_report.md` e `.json`.

Checagens:
  1. v1 byte-a-byte preservada (hash rid+text_no_url).
  2. colunas exatamente as 23, na ordem.
  3. flags is_duplicated/is_null/too_short = 0; sem texto vazio; word_len>=3.
  4. rid unico e sem colisao com a v1.
  5. vazamento de léxico de checagem em linhas `true` por procedencia.
  6. duplicatas exatas (chave normalizada) remanescentes.
  7. composicao por era/rotulo/dataset e PT-PT.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from . import dedup as dd
from .extract import is_leaky
from .merge_and_audit import COLUMNS


def _era(s):
    ts = pd.to_datetime(s, errors="coerce")
    return pd.cut(ts, [pd.Timestamp("1900-01-01"), pd.Timestamp("2018-01-01"),
                       pd.Timestamp("2022-12-01"), pd.Timestamp("2100-01-01")],
                  labels=["ate_2017", "2018_2022", "pos_gpt35"])


def judge(v1_path: Path, v2_path: Path, prov_path: Path | None,
          out_md: Path) -> dict:
    v1 = pd.read_csv(v1_path, low_memory=False)
    v2 = pd.read_csv(v2_path, low_memory=False)
    n1 = len(v1)
    new = v2.iloc[n1:].copy()
    problems: list[str] = []

    # 1. v1 intacta
    h1 = dd.content_hash(zip(v1["rid"], v1["text_no_url"]))
    h2 = dd.content_hash(zip(v2["rid"].iloc[:n1], v2["text_no_url"].iloc[:n1]))
    if h1 != h2:
        problems.append("v1 ALTERADA (hash difere)")

    # 2. colunas
    if list(v2.columns) != COLUMNS:
        problems.append(f"colunas fora de ordem: {list(v2.columns)}")

    # 3. flags/limpeza
    for c in ("is_duplicated", "is_null", "too_short"):
        vals = pd.to_numeric(v2[c], errors="coerce").fillna(-1)
        if not (vals == 0).all():
            problems.append(f"{c} nao e 0 em {int((vals != 0).sum())} linhas")
    if (new["text"].astype(str).str.strip() == "").any():
        problems.append("texto vazio nas novas")
    wl = pd.to_numeric(new["word_len"], errors="coerce").fillna(0)
    if (wl < 3).any():
        problems.append(f"word_len<3 em {int((wl < 3).sum())} linhas novas")

    # 4. rid
    if v2["rid"].duplicated().any():
        problems.append(f"rid duplicado: {int(v2['rid'].duplicated().sum())}")
    if set(v2["rid"].iloc[:n1]) & set(new["rid"]):
        problems.append("rid de nova colide com a v1")

    # 5. vazamento em true por procedencia (mesmo criterio do extract)
    is_news = new["dataset_name"].astype(str).str.startswith("NEWS_")
    true_news = new[is_news & (new["label"] == "true")]
    leak = true_news["text"].astype(str).map(is_leaky)
    n_leak = int(leak.sum())
    if n_leak:
        problems.append(f"vazamento lexico em {n_leak} manchetes 'true'")

    # 6. duplicatas exatas remanescentes
    keys = v2["text_no_url"].astype(str).map(dd.normalize_text)
    dup_keys = int(keys.duplicated().sum())

    new["_era"] = _era(new["date_iso"])
    is_ptpt = new["url_review"].fillna("").str.contains(
        r"poligrafo|observador|eco\.sapo\.pt", case=False, regex=True)
    report = {
        "n_v1": n1,
        "n_v2": int(len(v2)),
        "n_new": int(len(new)),
        "problemas": problems,
        "ok": not problems,
        "exact_dups_remanescentes": dup_keys,
        "true_news_leak": n_leak,
        "label": new["label"].value_counts().to_dict(),
        "por_era": new["_era"].value_counts().to_dict(),
        "label_x_era": pd.crosstab(new["_era"], new["label"]).to_dict(),
        "ptpt": int(is_ptpt.sum()),
        "pct_ptpt": round(float(is_ptpt.mean() * 100), 2),
        "top_datasets": {k: int(v) for k, v in
                         new["dataset_name"].value_counts().head(15).items()},
    }
    if prov_path and Path(prov_path).exists():
        prov = pd.read_csv(prov_path, low_memory=False)
        report["mentions_ai"] = int(
            pd.to_numeric(prov["mentions_ai"], errors="coerce").fillna(0).sum())

    lines = ["# Juiz da v2 — qualidade e conformidade", "",
             f"- v1: {n1:,} linhas | v2: {len(v2):,} | novas: {len(new):,}",
             f"- **veredito: {'OK' if not problems else 'PROBLEMAS'}**", ""]
    if problems:
        lines += ["## Problemas", *[f"- {p}" for p in problems], ""]
    lines += [
        "## Composicao das novas",
        f"- rotulo: {report['label']}",
        f"- por era: {report['por_era']}",
        f"- PT-PT: {report['ptpt']:,} ({report['pct_ptpt']}%)",
        f"- mencoes a IA: {report.get('mentions_ai', 'n/d')}",
        f"- duplicatas exatas remanescentes: {dup_keys}",
        f"- vazamento lexico em manchetes true: {n_leak}",
        "",
        "## Datasets (top 15)",
        *[f"- {k}: {v:,}" for k, v in report["top_datasets"].items()],
    ]
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines), encoding="utf-8")
    out_md.with_suffix(".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1)[:3000])
    return report


def main():
    ap = argparse.ArgumentParser()
    root = Path(".")
    ap.add_argument("--v1", type=Path, default=root / "FakenewsBR_sanitized.csv")
    ap.add_argument("--v2", type=Path, default=root / "FakenewsBR_sanitized_v2.csv")
    ap.add_argument("--provenance", type=Path,
                    default=root / "FakenewsBR_v2_provenance.csv")
    ap.add_argument("--out", type=Path,
                    default=root / "investigation" / "expansion" / "v2_quality_report.md")
    a = ap.parse_args()
    judge(a.v1, a.v2, a.provenance, a.out)


if __name__ == "__main__":
    main()
