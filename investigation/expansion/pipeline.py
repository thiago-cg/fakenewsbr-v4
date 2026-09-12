"""CLI unico do pipeline de expansao.

Estagios:
    plan          planeja a coleta (regras ou agente LLM) -> collection_plan.json
    collect       coleta bruta das fontes sem chave (feed, WP, sitemaps)
    extract       raw/*.jsonl -> processed/records.jsonl
    dedup         inspeciona duplicatas contra a v1 (relatorio)
    merge         records.jsonl + v1 -> FakenewsBR_sanitized_v2.csv + auditoria
    llm-prepare   monta os requests do LLM (dry-run; grava e estima custo)
    llm-submit    submete os batches ao OpenRouter (exige OPENROUTER_API_KEY)
    llm-collect   baixa resultados dos batches e anexa aos records
    all           collect -> extract -> merge

Uso:
    python -m investigation.expansion.pipeline collect --news-max-ratio 3
    python -m investigation.expansion.pipeline extract
    python -m investigation.expansion.pipeline merge
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "investigation" / "expansion" / "raw"
PROC = ROOT / "investigation" / "expansion" / "processed"
LOGS = ROOT / "investigation" / "expansion" / "logs"

WP_SOURCES = ["boatos", "efarsas", "bereia", "poder360", "cnnbrasil",
              "brasildefato", "oeco", "eco"]
SITEMAP_SOURCES = ["g1", "poligrafo"]


def _py(module: str, *args) -> int:
    cmd = [sys.executable, "-m", module, *map(str, args)]
    print("[pipeline]", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT))


# ------------------------------------------------------------------- estagios
def stage_collect(args):
    """Coleta em serie; cada fonte loga em logs/<fonte>.out.log."""
    LOGS.mkdir(parents=True, exist_ok=True)
    if "feed" in args.only or not args.only:
        _py("investigation.expansion.collect_feed")
    for src in WP_SOURCES:
        if args.only and src not in args.only:
            continue
        extra = ["--source", src]
        if args.from_year:
            extra += ["--from", args.from_year]
        if args.pages_per_year:
            extra += ["--pages-per-year", args.pages_per_year]
        _py("investigation.expansion.collect_wp", *extra)
    for src in SITEMAP_SOURCES:
        if args.only and src not in args.only:
            continue
        _py("investigation.expansion.collect_sitemap", "--source", src)
    return 0


def stage_extract(args):
    return _py("investigation.expansion.extract",
               "--raw-dir", RAW, "--out", PROC / "records.jsonl")


def stage_merge(args):
    return _py(
        "investigation.expansion.merge_and_audit",
        "--records", PROC / "records.jsonl",
        "--original", ROOT / "FakenewsBR_sanitized.csv",
        "--out", ROOT / "FakenewsBR_sanitized_v2.csv",
        "--provenance", ROOT / "FakenewsBR_v2_provenance.csv",
        "--report", ROOT / "investigation" / "expansion" / "audit_v2.md",
        "--news-max-ratio", args.news_max_ratio,
        *(["--no-near"] if args.no_near else []),
    )


def stage_plan(args):
    if args.planner == "llm":
        return _py("investigation.expansion.langchain_agent", "--planner", "llm")
    return _py("investigation.expansion.langchain_agent", "--planner", "rules")


def stage_llm(args):
    sub = {"llm-prepare": ["--dry-run"], "llm-submit": [],
           "llm-collect": ["--collect"], "llm-apply": ["--apply"]}[args.stage]
    extra = ["--task", args.task] if args.task else []
    return _py("investigation.expansion.llm_batch", *sub, *extra)


def stage_all(args):
    rc = stage_collect(args)
    if rc:
        return rc
    rc = stage_extract(args)
    if rc:
        return rc
    return stage_merge(args)


STAGES = {
    "plan": stage_plan, "collect": stage_collect, "extract": stage_extract,
    "merge": stage_merge, "all": stage_all,
    "llm-prepare": stage_llm, "llm-submit": stage_llm,
    "llm-collect": stage_llm, "llm-apply": stage_llm,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=sorted(STAGES))
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--from-year", type=int, default=None)
    ap.add_argument("--pages-per-year", type=int, default=None)
    ap.add_argument("--news-max-ratio", type=float, default=3.0)
    ap.add_argument("--no-near", action="store_true")
    ap.add_argument("--planner", choices=["rules", "llm"], default="rules")
    ap.add_argument("--task", choices=["label", "verify-news"], default=None)
    a = ap.parse_args()
    a.stage = a.stage  # noqa
    fn = STAGES[a.stage]
    try:
        rc = fn(a)
    except KeyboardInterrupt:
        print("[pipeline] interrompido", file=sys.stderr)
        rc = 130
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
