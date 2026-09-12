"""Consolida as camadas de rotulagem em um unico artefato por rid.

Entradas (quando existirem):
  - proveniencia base: `FakenewsBR_v3_provenance.csv` (ou v2)
  - match de checador: `FakenewsBR_v2_factcheck_matches.csv`
  - corroboracao/semantico: `FakenewsBR_v2_news_verification.csv`
  - LLM local: `processed/local_verify_results.jsonl`

Saida: `FakenewsBR_v3_labels.csv` com
    rid, text, label_original, label_source, label_tier, auto_label,
    confidence, method, evidence
e resumo por tier/dataset em `investigation/expansion/labels_v3_report.md`.
`train_label` e derivado por politica: checker/external sempre; llm_local com
confianca >= 0.8; corroboracao apenas `true`; o resto fica sem rotulo de treino.

Uso:
    python -m investigation.expansion.apply_verification
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

PROC = Path("investigation/expansion/processed")

TIER_PRIORITY = {
    "v1": 1,            # linhas da v1 (rotulo da fonte, usadas no FT original)
    "checker": 1,       # rating de checador / dataset externo checado
    "checker_match": 2,  # match contra corpus ClaimReview (>= 0.9)
    "llm_local": 3,
    "corroborated": 4,
    "provenance": 9,
    "unknown": 10,
}


def load_base(path: Path, v2: Path) -> pd.DataFrame:
    if path.exists():
        prov = pd.read_csv(path, low_memory=False)
        v2df = pd.read_csv(v2, low_memory=False, usecols=["rid", "text", "label"])
        df = v2df.merge(prov, on="rid", how="left")
        df["label_source"] = df["label_source"].fillna("")
        return df
    v2df = pd.read_csv(v2, low_memory=False, usecols=["rid", "text", "label"])
    v2df["label_source"] = ""
    return v2df


def make_labels(base: pd.DataFrame, matches: Path, corrob: Path,
                local: Path) -> pd.DataFrame:
    df = base[["rid", "text", "label", "label_source"]].copy()
    df["label_tier"] = df["label_source"].map(
        {"rating": "checker", "provenance": "provenance"}).fillna("v1")
    df["auto_label"] = ""
    df["confidence"] = None
    df["method"] = ""
    df["evidence"] = ""

    if matches.exists():
        m = pd.read_csv(matches, low_memory=False)
        m = m[m["score"] >= 0.9]
        for r in m.itertuples(index=False):
            idx = df.index[df["rid"] == int(r.rid)]
            if len(idx) == 0 or r.concorda == 0:
                continue  # discordancias exigem revisao; nao sobrescreve
            i = idx[0]
            df.at[i, "label_tier"] = "checker_match"
            df.at[i, "auto_label"] = r.label_factcheck
            df.at[i, "confidence"] = float(r.score)
            df.at[i, "method"] = f"claimreview:{r.publisher}"
            df.at[i, "evidence"] = str(r.url)[:200]

    if local.exists():
        with local.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                idx = df.index[df["rid"] == int(r["rid"])]
                if len(idx) == 0:
                    continue
                i = idx[0]
                v = r.get("verdict")
                conf = float(r.get("confidence") or 0)
                if v in ("fake", "true") and conf >= 0.8:
                    # so promove se nao houver camada mais forte
                    if TIER_PRIORITY.get(df.at[i, "label_tier"], 99) > 3:
                        df.at[i, "label_tier"] = "llm_local"
                        df.at[i, "auto_label"] = v
                        df.at[i, "confidence"] = conf
                        df.at[i, "method"] = "llm_local"
                        df.at[i, "evidence"] = ""

    if corrob.exists():
        c = pd.read_csv(corrob, low_memory=False)
        c = c[c["auto_label"] == "true"]
        for r in c.itertuples(index=False):
            idx = df.index[df["rid"] == int(r.rid)]
            if len(idx) == 0:
                continue
            i = idx[0]
            if TIER_PRIORITY.get(df.at[i, "label_tier"], 99) > 4:
                df.at[i, "label_tier"] = "corroborated"
                df.at[i, "auto_label"] = "true"
                df.at[i, "confidence"] = None
                df.at[i, "method"] = "corroboracao"
                df.at[i, "evidence"] = str(getattr(r, "evidence", ""))[:200]

    train_ok = df["label_tier"].isin(
        ["v1", "checker", "checker_match", "corroborated"])
    train_ok |= (df["label_tier"] == "llm_local") & (
        pd.to_numeric(df["confidence"], errors="coerce") >= 0.8)
    df["train_label"] = None
    df.loc[train_ok, "train_label"] = df.loc[train_ok, "auto_label"].where(
        df.loc[train_ok, "auto_label"].isin(["fake", "true"]),
        df.loc[train_ok, "label"])
    return df


def report(df: pd.DataFrame, out: Path) -> dict:
    res = {
        "n": int(len(df)),
        "por_tier": df["label_tier"].value_counts().to_dict(),
        "com_train_label": int(df["train_label"].isin(["fake", "true"]).sum()),
        "train_fake": int((df["train_label"] == "fake").sum()),
        "train_true": int((df["train_label"] == "true").sum()),
        "por_dataset_novos": df[df["label_source"] == ""]["label_tier"]
        .value_counts().to_dict(),
    }
    lines = ["# Rotulagem v3 — camadas", "",
             f"- linhas: {res['n']:,}",
             f"- com rotulo de treino: {res['com_train_label']:,}",
             f"- treino fake/true: {res['train_fake']:,} / "
             f"{res['train_true']:,}",
             "", "## Por camada",
             *[f"- {k}: {v:,}" for k, v in res["por_tier"].items()]]
    out.write_text("\n".join(lines), encoding="utf-8")
    out.with_suffix(".json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path,
                    default=Path("FakenewsBR_v3_provenance.csv"))
    ap.add_argument("--v2", type=Path,
                    default=Path("FakenewsBR_sanitized_v3.csv"))
    ap.add_argument("--matches", type=Path,
                    default=Path("FakenewsBR_v2_factcheck_matches.csv"))
    ap.add_argument("--corrob", type=Path,
                    default=Path("FakenewsBR_v2_news_verification.csv"))
    ap.add_argument("--local", type=Path,
                    default=PROC / "local_verify_results.jsonl")
    ap.add_argument("--out", type=Path, default=Path("FakenewsBR_v3_labels.csv"))
    ap.add_argument("--report", type=Path,
                    default=Path("investigation/expansion/labels_v3_report.md"))
    a = ap.parse_args()
    base = load_base(a.base, a.v2)
    df = make_labels(base, a.matches, a.corrob, a.local)
    df.to_csv(a.out, index=False)
    res = report(df, a.report)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"[labels] -> {a.out}")


if __name__ == "__main__":
    main()
