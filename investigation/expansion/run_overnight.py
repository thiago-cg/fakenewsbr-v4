"""Runner autonomo: espera a coleta estabilizar, extrai, faz merge e audita.

Feito para rodar em background durante a noite. Nao depende de mim estar
olhando: escreve `workbench.md` com o progresso e, ao final, roda
`extract` + `merge_and_audit` + a suite de testes.

Criterio de parada:
  - nenhum processo `collect_*` ativo E nenhum `raw/*.jsonl` alterado nos
    ultimos `--stale-minutes`; ou
  - `--max-minutes` atingido; ou
  - a v2 ja tem `--target-rows` linhas.

Uso:
    python -m investigation.expansion.run_overnight --max-minutes 300
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "investigation" / "expansion" / "raw"
PROC = ROOT / "investigation" / "expansion" / "processed"
WORKBENCH = ROOT / "investigation" / "expansion" / "workbench.md"


def _collect_running() -> int:
    ps = ("(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
          "Where-Object { $_.CommandLine -like '*investigation.expansion.collect*' }"
          ").Count")
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            timeout=60)
        return int((out or b"0").strip() or 0)
    except Exception:
        return 0


def _raw_state() -> dict[str, float]:
    return {p.name: p.stat().st_mtime for p in RAW.glob("*.jsonl")}


def _records_count() -> int:
    p = PROC / "records.jsonl"
    if not p.exists():
        return 0
    with p.open("r", encoding="utf-8", errors="ignore") as f:
        return sum(1 for _ in f)


def _v2_count() -> int:
    p = ROOT / "FakenewsBR_sanitized_v2.csv"
    if not p.exists():
        return 0
    try:
        import pandas as pd
        return len(pd.read_csv(p, usecols=["rid"], low_memory=False))
    except Exception:
        return 0


def _write_workbench(status: str, extra: str = "", raw: dict | None = None):
    raw = raw if raw is not None else _raw_state()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for p in sorted(RAW.glob("*.jsonl")):
        try:
            lines = sum(1 for _ in p.open("r", encoding="utf-8", errors="ignore"))
        except OSError:
            lines = 0
        rows.append(f"| {p.stem} | {lines:,} | {p.stat().st_size/1e6:.1f} | "
                    f"{datetime.fromtimestamp(p.stat().st_mtime):%H:%M:%S} |")
    text = f"""# Workbench — expansão FakenewsBR

Atualizado: {now}
Status: **{status}**

- registros extraídos: {_records_count():,}
- linhas na v2: {_v2_count():,}
- processos de coleta ativos: {_collect_running()}
{extra}

## Raw

| fonte | linhas | MB | mtime |
|---|---:|---:|---|
{chr(10).join(rows)}
"""
    WORKBENCH.write_text(text, encoding="utf-8")


def _py(module: str, *args) -> int:
    return subprocess.call([sys.executable, "-m", module, *map(str, args)],
                           cwd=str(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-minutes", type=float, default=300)
    ap.add_argument("--stale-minutes", type=float, default=20)
    ap.add_argument("--check-seconds", type=float, default=180)
    ap.add_argument("--target-rows", type=int, default=200000)
    ap.add_argument("--news-max-ratio", type=float, default=6.0)
    ap.add_argument("--near", action="store_true", default=True)
    a = ap.parse_args()

    start = time.time()
    while True:
        elapsed = (time.time() - start) / 60
        state = _raw_state()
        stale = (time.time() - max(state.values())) / 60 if state else 999
        running = _collect_running()
        _write_workbench(
            f"coletando (ativo={running}, stale={stale:.1f} min, "
            f"v2={_v2_count():,}, t={elapsed:.0f} min)", raw=state)
        if _v2_count() >= a.target_rows and running == 0:
            break
        if elapsed >= a.max_minutes:
            break
        if running == 0 and stale >= a.stale_minutes:
            break
        time.sleep(a.check_seconds)

    _write_workbench("extraindo (coleta encerrada)")
    _py("investigation.expansion.extract")
    _write_workbench("merge + auditoria")
    _py("investigation.expansion.merge_and_audit",
        "--news-max-ratio", a.news_max_ratio)
    _write_workbench("testes")
    _py("unittest", "discover", "-s", "investigation/expansion/tests", "-t", ".")
    _write_workbench("concluido", extra=f"\n- linhas na v2: {_v2_count():,}")


if __name__ == "__main__":
    main()
