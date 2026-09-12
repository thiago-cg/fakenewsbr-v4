"""Planejador de coleta: modo `rules` (sem rede) e modo `llm` (LangChain).

O plano compara a cobertura ja coletada com as metas por era/rotulo/dialeto e
propoe cotas por fonte. Saida em `processed/collection_plan.json`.

Modo rules  : deterministico, nao precisa de chave.
Modo llm    : `langchain.agents.create_agent` com tools que consultam os
              mesmos dados e propõem um plano; usa OpenRouter
              (`OPENROUTER_API_KEY`), modelo `openai/gpt-5-nano` (sem `:batch`).

Tools do agente: coverage_gaps, list_sources, propose_quota,
estimate_llm_cost, gfc_search (so se houver GOOGLE_FACTCHECK_API_KEY).
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

RAW = Path("investigation/expansion/raw")
PROC = Path("investigation/expansion/processed")

# metas por era (linhas), alinhadas ao goal do usuario
GOALS = {
    "ate_2017": 30000,
    "2018_2022": 80000,
    "pos_gpt35": 80000,
}

SOURCE_KIND = {
    "boatos": ("veredito", "fake"), "efarsas": ("veredito", "fake/true"),
    "bereia": ("veredito", "fake/true"), "feed": ("veredito", "fake/true"),
    "g1": ("veredito", "fake/true"), "poligrafo": ("veredito", "fake/true"),
    "poder360": ("procedencia", "true"), "brasildefato": ("procedencia", "true"),
    "oeco": ("procedencia", "true"), "eco": ("procedencia", "true"),
    "cnnbrasil": ("procedencia", "true"),
}


def _count_lines(p: Path) -> int:
    try:
        with p.open("r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except FileNotFoundError:
        return 0


def list_sources() -> dict:
    out = {}
    for p in sorted(RAW.glob("*.jsonl")):
        kind, label = SOURCE_KIND.get(p.stem, ("?", "?"))
        out[p.stem] = {"lines": _count_lines(p), "tipo": kind, "rotulo": label}
    return out


def _years_of(path: Path) -> dict[str, int]:
    """Conta 2017 / 2018-2022 / 2023+ por date_iso, tolerante a ausencia."""
    eras = {"ate_2017": 0, "2018_2022": 0, "pos_gpt35": 0, "sem_data": 0}
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    d = json.loads(line).get("date_iso") or ""
                except json.JSONDecodeError:
                    continue
                if not d[:4].isdigit():
                    eras["sem_data"] += 1
                elif d < "2018-01-01":
                    eras["ate_2017"] += 1
                elif d < "2022-12-01":
                    eras["2018_2022"] += 1
                else:
                    eras["pos_gpt35"] += 1
    except FileNotFoundError:
        pass
    return eras


def coverage_by_era() -> dict:
    cov = {k: 0 for k in GOALS}
    for p in sorted(RAW.glob("*.jsonl")):
        y = _years_of(p)
        for k in GOALS:
            cov[k] += y.get(k, 0)
    return cov


# ------------------------------------------------------------------- tools
def coverage_gaps() -> dict:
    cov = coverage_by_era()
    return {k: {"atual": cov[k], "meta": GOALS[k],
                "deficit": max(0, GOALS[k] - cov[k])} for k in GOALS}


def propose_quota(source: str, from_year: int, max_rows: int, ratio: float) -> dict:
    """Quota validada para uma fonte WP (evita excesso de uma unica origem)."""
    src = list_sources().get(source, {})
    if src.get("tipo") == "procedencia":
        max_rows = min(max_rows, int(ratio * 80000))
    return {"source": source, "from_year": int(from_year),
            "max_rows": int(max_rows), "ok": max_rows > 0}


def estimate_llm_cost(n: int, chars: int = 800) -> dict:
    tin = (chars // 4 + 500) * n
    return {"requests": n, "usd": round(tin / 1e6 * 0.025 + 120 * n / 1e6 * 0.20, 4)}


def gfc_search(query: str) -> dict:
    key = os.environ.get("GOOGLE_FACTCHECK_API_KEY")
    if not key:
        return {"erro": "GOOGLE_FACTCHECK_API_KEY ausente"}
    import requests
    try:
        r = requests.get(
            "https://factchecktools.googleapis.com/v1alpha1/claims:search",
            params={"query": query, "languageCode": "pt", "pageSize": 10,
                    "key": key}, timeout=30)
        return {"status": r.status_code, "n": len(r.json().get("claims", []))}
    except Exception as e:  # noqa: BLE001
        return {"erro": str(e)}


# --------------------------------------------------------------- planner rules
def plan_rules() -> dict:
    gaps = coverage_gaps()
    srcs = list_sources()
    actions = []
    for k, g in gaps.items():
        if g["deficit"] <= 0:
            continue
        if k == "ate_2017":
            for s in ("oeco", "boatos", "efarsas"):
                if s in srcs:
                    actions.append({"action": "extend_history", "source": s,
                                    "deficit": g["deficit"]})
        else:
            for s in ("poder360", "brasildefato", "eco", "g1"):
                if s in srcs:
                    actions.append({"action": "collect", "source": s,
                                    "deficit": g["deficit"]})
    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "coverage": gaps,
        "sources": srcs,
        "acoes": actions,
        "llm": estimate_llm_cost(0),
    }


# ----------------------------------------------------------------- planner llm
def plan_llm():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("[plan] OPENROUTER_API_KEY ausente; caindo para rules")
        return plan_rules()
    try:
        from langchain.agents import create_agent
        from langchain_core.tools import tool
        from langchain_openai import ChatOpenAI
    except Exception as e:  # noqa: BLE001
        print(f"[plan] langchain indisponivel ({e}); caindo para rules")
        return plan_rules()

    @tool
    def t_coverage() -> dict:
        """Deficits de cobertura por era (atual, meta, deficit)."""
        return coverage_gaps()

    @tool
    def t_sources() -> dict:
        """Lista as fontes coletadas com volume e tipo."""
        return list_sources()

    @tool
    def t_quota(source: str, from_year: int, max_rows: int, ratio: float = 1.0) -> dict:
        """Valida uma cota de coleta para uma fonte."""
        return propose_quota(source, from_year, max_rows, ratio)

    @tool
    def t_cost(n: int) -> dict:
        """Estima custo do LLM para n requests."""
        return estimate_llm_cost(n)

    llm = ChatOpenAI(model="openai/gpt-5-nano",
                     base_url="https://openrouter.ai/api/v1", api_key=key,
                     temperature=0)
    agent = create_agent(llm, [t_coverage, t_sources, t_quota, t_cost])
    prompt = ("Voce planeja a expansao do dataset FakenewsBR. Use as tools para "
              "ver deficits e fontes e proponha um plano de coleta enxuto. "
              "Responda com JSON: {acoes:[{source, from_year, max_rows, motivo}], "
              "resumo}. Metas: 30k <=2017, 80k 2018-2022, 80k >=2022-12.")
    try:
        res = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
        text = res["messages"][-1].content
    except Exception as e:  # noqa: BLE001
        print(f"[plan] agente falhou ({e}); caindo para rules")
        return plan_rules()
    try:
        plan = json.loads(text)
        plan["coverage"] = coverage_gaps()
        return plan
    except json.JSONDecodeError:
        return {"resumo_llm": text, "coverage": coverage_gaps()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--planner", choices=["rules", "llm"], default="rules")
    ap.add_argument("--out", type=Path, default=PROC / "collection_plan.json")
    a = ap.parse_args()
    plan = plan_rules() if a.planner == "rules" else plan_llm()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[plan] {a.planner} -> {a.out}")
    print(json.dumps(plan.get("coverage", plan), ensure_ascii=False, indent=1)[:2000])


if __name__ == "__main__":
    main()
