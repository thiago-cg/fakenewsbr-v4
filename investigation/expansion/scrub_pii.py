"""Gera uma variante publica da v4 com PII mascarada.

Mascara e-mails, CPF e strings tipo telefone em `text`, `text_no_url`,
`text_clean` e `extracted_urls`. Nao altera o CSV de pesquisa.

Uso:
    python -m investigation.expansion.scrub_pii
    python -m investigation.expansion.scrub_pii --in FakenewsBR_sanitized_v4.csv \
        --out FakenewsBR_v4_public.csv
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
FONE = re.compile(r"(?:\+?55[\s.-]?)?(?:\(?\d{2}\)?[\s.-]?)?9?\d{4}[-\s]?\d{4}\b")

TEXT_COLS = ["text", "text_no_url", "text_clean", "extracted_urls"]


def scrub(s: str, counts: dict) -> str:
    if not isinstance(s, str) or not s:
        return s
    s, n = EMAIL.subn("[EMAIL]", s)
    counts["email"] = counts.get("email", 0) + n
    s, n = CPF.subn("[CPF]", s)
    counts["cpf"] = counts.get("cpf", 0) + n
    s, n = FONE.subn("[TELEFONE]", s)
    counts["telefone"] = counts.get("telefone", 0) + n
    return s


def run(inp: Path, out: Path) -> dict:
    df = pd.read_csv(inp, low_memory=False)
    counts: dict[str, int] = {}
    for c in TEXT_COLS:
        if c in df.columns:
            df[c] = df[c].map(lambda x: scrub(x, counts))
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"[scrub] {len(df):,} linhas -> {out}")
    print(f"[scrub] mascaras: {counts}")
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path,
                    default=Path("FakenewsBR_sanitized_v4.csv"))
    ap.add_argument("--out", type=Path,
                    default=Path("FakenewsBR_v4_public.csv"))
    a = ap.parse_args()
    run(a.inp, a.out)


if __name__ == "__main__":
    main()
