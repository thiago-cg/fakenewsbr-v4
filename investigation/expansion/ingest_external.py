"""Ingere corpora externos PT-BR checados (LIAR-BR e AVERITEC-BR, STIL 2025).

Mapeamento binario conservador:
  LIAR-BR:      false/pants-on-fire -> fake ; true/mostly-true -> true ;
                half-true/barely-true -> descarta
  AVERITEC-BR:  Refuted -> fake ; Supported -> true ;
                Not Enough Evidence / Conflicting -> descarta

Saida: `processed/records_ext_liarbr.jsonl` e `records_ext_averitecbr.jsonl`
no mesmo schema canonico (com `_provenance`), prontos para o merge com `--extra`.

Uso:
    python -m investigation.expansion.ingest_external
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import schema as sch

ROOT = Path(".")
EXT = ROOT / "external" / "automated-fact-checking-in-pt-br"
PROC = ROOT / "investigation" / "expansion" / "processed"

LIAR_MAP = {"false": ("fake", "Falso"), "pants-on-fire": ("fake", "Falso"),
            "true": ("true", "Verdadeiro"),
            "mostly-true": ("true", "Verdadeiro"),
            "half-true": (None, "Meia-verdade"),
            "barely-true": (None, "Pouco verdadeiro")}
AVERITEC_MAP = {"Refuted": ("fake", "Refutado"),
                "Supported": ("true", "Suportado"),
                "Not Enough Evidence": (None, "Evidência insuficiente"),
                "Conflicting Evidence/Cherrypicking": (None, "Evidência conflitante")}


def _record(text: str, label: str, rating: str, dataset: str,
            claimant: str, url: str, date_iso: str | None,
            key: str) -> dict | None:
    text = (text or "").strip()
    if len(text) < 15:
        return None
    rid = sch.make_rid(url or key, "claim", key)
    r = sch.Record(
        rid=rid, dataset_name=dataset, source_type="news",
        source_description=("LIAR-BR (STIL 2025, traduzido)" if dataset == "EXT_LIARBR"
                            else "AVERITEC-BR (STIL 2025, traduzido)"),
        label=label, date_iso=date_iso, url_review=url, text=text,
        factcheck_rating=rating, factcheck_claimant=claimant, factcheck_url=url,
        label_source="rating", text_role="claim", publisher=dataset.lower(),
        lang_variant="pt-BR", collector="external", source_url=url,
        collected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        mentions_ai=int(sch.mentions_ai(text)))
    try:
        r.finalize()
    except ValueError:
        return None
    row = r.csv_row()
    row["_provenance"] = r.prov_row("external")
    return row


def ingest_liar(out: Path) -> int:
    n = 0
    with out.open("w", encoding="utf-8") as f:
        for split in ["train", "valid", "test"]:
            p = EXT / "liar" / "pt-br" / "dataset" / f"{split}.jsonl"
            if not p.exists():
                continue
            for line in p.open("r", encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                label, rating = LIAR_MAP.get(str(d.get("label", "")).lower(),
                                             (None, ""))
                if label is None:
                    continue
                row = _record(d.get("statement", ""), label, rating,
                              "EXT_LIARBR", d.get("speaker", ""), "",
                              None, str(d.get("statement_ID", len(str(d)))))
                if row:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    n += 1
    return n


def ingest_averitec(out: Path) -> int:
    n = 0
    with out.open("w", encoding="utf-8") as f:
        for split in ["train", "dev"]:
            p = EXT / "averitec" / "pt-br" / "dataset" / f"{split}.json"
            if not p.exists():
                continue
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data = list(data.values())
            for i, d in enumerate(data):
                label, rating = AVERITEC_MAP.get(d.get("label"), (None, ""))
                if label is None:
                    continue
                date = pd.to_datetime(d.get("claim_date"), format="%d-%m-%Y",
                                      errors="coerce")
                date_iso = None if pd.isna(date) else date.strftime("%Y-%m-%d")
                url = (d.get("original_claim_url")
                       or d.get("fact_checking_article") or "")
                row = _record(d.get("claim", ""), label, rating,
                              "EXT_AVERITECBR", d.get("speaker", ""), url,
                              date_iso, f"{split}:{i}")
                if row:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proc", type=Path, default=PROC)
    a = ap.parse_args()
    a.proc.mkdir(parents=True, exist_ok=True)
    n1 = ingest_liar(a.proc / "records_ext_liarbr.jsonl")
    n2 = ingest_averitec(a.proc / "records_ext_averitecbr.jsonl")
    print(f"[external] LIAR-BR {n1} linhas | AVERITEC-BR {n2} linhas")


if __name__ == "__main__":
    main()
