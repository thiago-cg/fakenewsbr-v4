"""Rotulagem de manchetes NEWS_* com a LLM local (Unsloth Studio).

Reusa a recuperacao de evidencia do `verify_news` (Google News RSS) e o prompt
anti-alucinacao do `llm_batch`, mas chama a LLM local (OpenAI-compativel) em
vez do OpenRouter. Processa em lotes com checkpoint retomavel:

    processed/local_verify_results.jsonl   (rid, verdict, confidence, motivo, raw)

Uso:
    python -m investigation.expansion.local_label --limit 40      # piloto
    python -m investigation.expansion.local_label --max-minutes 480 --workers-llm 4
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

from . import local_llm
from . import verify_news as vn

PROC = Path("investigation/expansion/processed")
RAW = Path("investigation/expansion/raw")
DEFAULT_CACHE = Path("FakenewsBR_v2_news_verification.cache.jsonl")
RESULTS = PROC / "local_verify_results.jsonl"

SYSTEM = (
    "Verifique a manchete usando SOMENTE as evidencias fornecidas. Responda "
    "APENAS com JSON: {\"verdict\":\"fake\"|\"true\"|\"unknown\","
    "\"confidence\":0-100}. fake = a evidencia refuta claramente; true = duas "
    "ou mais fontes independentes e reputaveis confirmam o mesmo evento com "
    "numeros e datas compativeis; qualquer outro caso = unknown. Nao use "
    "conhecimento interno. Se faltar evidencia, unknown."
)


def already_done(path: Path) -> set[int]:
    done = set()
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(int(json.loads(line)["rid"]))
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
    return done


def build_prompt(text: str, date_iso: str, items: list[dict]) -> str:
    ev = []
    for i, it in enumerate(items[:8]):
        fc = vn._factchecker(it)
        tag = f" [CHECADOR:{fc}]" if fc else ""
        ev.append(f"[{i}] {it.get('domain','')} ({str(it.get('pub',''))[:16]})"
                  f"{tag}: {str(it.get('title',''))[:160]}")
    return (f"MANCHETE: {text}\nDATA: {date_iso}\n\n"
            f"EVIDENCIAS (Google News):\n" + ("\n".join(ev) or "(nenhuma)"))


def verify_one(row, items, model: str, max_tokens: int) -> dict:
    prompt = build_prompt(str(row.text), str(getattr(row, "date_iso", "") or ""),
                          items)
    base = {"rid": int(row.rid), "text": str(row.text)[:220], "raw": ""}
    try:
        out = local_llm.chat(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": prompt}],
            model=model, temperature=0.0, max_tokens=max_tokens)
    except Exception as e:  # noqa: BLE001
        base.update({"verdict": "unknown", "confidence": 0.0,
                     "motivo": "", "erro": str(e)[:200]})
        return base
    obj = local_llm.parse_json(out) or {}
    verdict = str(obj.get("verdict", "unknown")).lower().strip()
    if verdict not in ("fake", "true", "unknown"):
        verdict = "unknown"
    try:
        conf = float(obj.get("confidence", 0.0))
        if conf > 1.0:
            conf = conf / 100.0
    except (TypeError, ValueError):
        conf = 0.0
    base.update({"verdict": verdict, "confidence": round(conf, 3),
                 "motivo": str(obj.get("motivo", ""))[:300],
                 "erro": "", "raw": out[:300] if not obj else ""})
    return base


def fetch_evidence(rows, cache: dict, cache_path: Path, workers: int,
                   delay: float) -> None:
    missing = [str(r.text)[:120] for r in rows
               if str(r.text)[:120] not in cache]
    if not missing:
        return
    lock = threading.Lock()
    last = [0.0]

    def one(q):
        with lock:
            wait = delay - (time.monotonic() - last[0])
            if wait > 0:
                time.sleep(wait)
            last[0] = time.monotonic()
        return q, vn.gnews(q, requests.Session())

    print(f"[local] buscando evidencia p/ {len(missing)} manchetes",
          flush=True)
    written = 0
    fcache = (cache_path.open("a", encoding="utf-8")
              if cache_path is not None else None)
    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for q, items in ex.map(one, missing):
                cache[q] = items
                if fcache is not None:
                    fcache.write(json.dumps({"q": q, "items": items},
                                            ensure_ascii=False) + "\n")
                    written += 1
                    if written % 200 == 0:
                        fcache.flush()
                        print(f"[local] evidencia {written}/{len(missing)}",
                              flush=True)
        if fcache is not None:
            fcache.flush()
    finally:
        if fcache is not None:
            fcache.close()


def run(v2: Path, limit: int, max_minutes: float, chunk: int,
        workers_llm: int, workers_fetch: int, model: str,
        max_tokens: int, fetch_delay: float, sample_seed: int) -> dict:
    news = vn.load_news(v2)
    news = news[news["text"].astype(str).map(vn.is_claim_like)]
    print(f"[local] {len(news):,} manchetes claim-like", flush=True)
    if limit:
        news = news.sample(n=min(limit, len(news)), random_state=sample_seed)
    done = already_done(RESULTS)
    news = news[~news["rid"].astype("int64").isin(done)]
    print(f"[local] {len(news):,} a processar ({len(done):,} ja feitos)",
          flush=True)

    cache: dict[str, list[dict]] = {}
    if DEFAULT_CACHE.exists():
        for line in DEFAULT_CACHE.open("r", encoding="utf-8"):
            try:
                r = json.loads(line)
                cache[r["q"]] = r["items"]
            except json.JSONDecodeError:
                continue

    PROC.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    total = 0
    with RESULTS.open("a", encoding="utf-8") as fout:
        for start in range(0, len(news), chunk):
            if (time.time() - t0) / 60 >= max_minutes:
                print("[local] orcamento de tempo atingido", flush=True)
                break
            batch = news.iloc[start:start + chunk]
            fetch_evidence(list(batch.itertuples(index=False)), cache,
                           DEFAULT_CACHE, workers_fetch, fetch_delay)
            with ThreadPoolExecutor(max_workers=workers_llm) as ex:
                futs = [ex.submit(verify_one, r,
                                  cache.get(str(r.text)[:120], []),
                                  model, max_tokens)
                        for r in batch.itertuples(index=False)]
                for fut in futs:
                    res = fut.result()
                    fout.write(json.dumps(res, ensure_ascii=False) + "\n")
                    fout.flush()
                    total += 1
            el = (time.time() - t0) / 60
            rate = total / max(el, 1e-6)
            print(f"[local] {start+len(batch)}/{len(news)} | {total} rotulados"
                  f" | {rate*60:.0f}/h | {el:.0f} min", flush=True)

    df = pd.read_json(RESULTS, lines=True) if RESULTS.exists() else pd.DataFrame()
    dist = df["verdict"].value_counts().to_dict() if len(df) else {}
    print(json.dumps({"total_resultados": int(len(df)),
                      "distribuicao": dist}, ensure_ascii=False, indent=1))
    return {"total": int(len(df)), "dist": dist}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v2", type=Path, default=Path("FakenewsBR_sanitized_v2.csv"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-minutes", type=float, default=480)
    ap.add_argument("--chunk", type=int, default=200)
    ap.add_argument("--workers-llm", type=int, default=4)
    ap.add_argument("--workers-fetch", type=int, default=4)
    ap.add_argument("--model", default=local_llm.DEFAULT_MODEL)
    ap.add_argument("--max-tokens", type=int, default=60)
    ap.add_argument("--fetch-delay", type=float, default=0.4)
    ap.add_argument("--sample-seed", type=int, default=42)
    a = ap.parse_args()
    run(a.v2, a.limit, a.max_minutes, a.chunk, a.workers_llm,
        a.workers_fetch, a.model, a.max_tokens, a.fetch_delay, a.sample_seed)


if __name__ == "__main__":
    main()
