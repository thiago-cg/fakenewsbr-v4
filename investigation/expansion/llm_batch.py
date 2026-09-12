"""LLM batch (OpenRouter) para rotular/extrair o que a taxonomia nao cobre.

Modelo: `openai/gpt-5-nano:batch` (OpenRouter Batch API, ~50 % do preco).
Chave: `OPENROUTER_API_KEY` (definida pelo usuario no ambiente; nunca no chat).

Tarefas suportadas (campo `task` de cada request):
    verdict_claim : artigo sem taxonomia -> {verdict, claim, justification}
    correction    : achar a frase de correcao verbatim -> {correction}

Fluxo:
    prepare : monta os requests (json_schema strict) e grava
              `processed/llm_requests.jsonl`. Com `--dry-run` (default) so
              estima custo; sem `--dry-run` tambem ficam prontos para envio.
    submit  : envia em lotes de ate 2000 requests para
              `POST https://openrouter.ai/api/beta/batches`.
    collect : faz poll dos batches pendentes e anexa os resultados.

Estado persistente em `processed/llm_batches.json` (resume).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

RAW = Path("investigation/expansion/raw")
PROC = Path("investigation/expansion/processed")

OPENROUTER_BASE = "https://openrouter.ai/api"
MODEL = "openai/gpt-5-nano:batch"
# preco do catalogo openrouter (US$ / 1M tokens)
PRICE_IN = 0.025
PRICE_OUT = 0.20
BATCH_CHUNK = 2000
POLL_SECONDS = 60


# ------------------------------------------------------------------- schema
VERDICT_SCHEMA = {
    "name": "verdict_claim",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["verdict", "claim"],
        "properties": {
            "verdict": {"type": "string",
                        "enum": ["fake", "true", "hard", "unclear"]},
            "claim": {"type": "string",
                      "description": "alegacao central, 1 frase"},
            "justification": {"type": "string"},
        },
    },
}
CORRECTION_SCHEMA = {
    "name": "correction",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["correction"],
        "properties": {
            "correction": {"type": "string",
                           "description": "frase de correcao verbatim do artigo"},
        },
    },
}
VERIFY_SCHEMA = {
    "name": "verify_headline",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["is_claim", "verdict", "confidence", "evidence_idx"],
        "properties": {
            "is_claim": {"type": "boolean",
                         "description": "se a manchete e uma alegacao verificavel"},
            "verdict": {"type": "string",
                        "enum": ["fake", "true", "unknown"]},
            "confidence": {"type": "number"},
            "claim": {"type": "string"},
            "rationale": {"type": "string"},
            "evidence_idx": {"type": "array", "items": {"type": "integer"}},
        },
    },
}

SYSTEM = (
    "Voce verifica manchetes de noticias em portugues usando SOMENTE as "
    "evidencias fornecidas. Responda APENAS com JSON no schema pedido. "
    "Regras: (1) se a manchete nao for uma alegacao verificavel (opiniao, "
    "analise, pergunta, tema), marque is_claim=false e verdict=unknown; "
    "(2) verdict=fake somente se a evidencia refutar claramente a alegacao; "
    "(3) verdict=true somente se >=2 evidencias independentes e reputaveis "
    "confirmarem o mesmo evento, com numeros e datas compativeis; "
    "(4) em qualquer outro caso, verdict=unknown. Nunca use conhecimento "
    "interno: se a evidencia nao bastar, abstenha-se."
)


def custom_id(task: str, source: str, url: str) -> str:
    key = f"{task}|{source}|{url}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]


def _body(task: str, text: str, prompt: str | None = None) -> dict:
    if task == "verify_headline":
        schema = VERIFY_SCHEMA
    elif task == "verdict_claim":
        schema = VERDICT_SCHEMA
    else:
        schema = CORRECTION_SCHEMA
    instruction = {
        "verdict_claim": "Classifique a alegacao do artigo e extraia-a.",
        "correction": "Extraia, literalmente, a frase que corrige a "
                      "desinformacao neste artigo.",
        "verify_headline": "Verifique a manchete usando apenas as evidencias.",
    }[task]
    user = prompt if prompt is not None else f"{instruction}\n\n--- ARTIGO ---\n{text[:12000]}"
    return {
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
        "model": MODEL,
        "reasoning": {"effort": "minimal"},
        "response_format": {"type": "json_schema", "json_schema": schema},
        "max_tokens": 400,
    }


def estimate_tokens(text: str) -> int:
    """Estimativa grosseira: ~4 chars/token em PT + ~500 de overhead."""
    return len(text) // 4 + 500


# --------------------------------------------------------------- build tasks
def _iter_raw(folder: Path):
    for p in sorted(folder.glob("*.jsonl")):
        if p.name.startswith("llm_"):
            continue
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield p.stem, json.loads(line)


def build(folder: Path) -> list[dict]:
    """Seleciona artigos sem taxonomia (feed 'other', g1 multi-alegacao)."""
    from . import schema as sch
    from .sources import feed_publisher

    reqs: list[dict] = []
    seen: set[str] = set()
    for source, rec in _iter_raw(folder):
        task, text, url, pub, lang = None, "", "", "", "pt-BR"
        if source == "feed":
            cls = sch.rating_to_class(rec.get("rating"))
            if cls != "other":
                continue
            task, text, url = "verdict_claim", rec.get("claimReviewed", ""), rec.get("url", "")
            pub = rec.get("publisher", "")
        elif source == "g1":
            h1 = rec.get("h1", "")
            if not h1 or not re.search(r"fato ou fake|o que e fato|confira", h1, re.I):
                continue
            task, text, url = "verdict_claim", h1, rec.get("url", "")
            pub = "g1"
        if not task or not text:
            continue
        cid = custom_id(task, source, url)
        if cid in seen:
            continue
        seen.add(cid)
        reqs.append({"custom_id": cid, "task": task, "source": source,
                     "publisher": pub, "lang_variant": lang, "url": url,
                     "text": text})
    return reqs


def build_verify(args) -> list[dict]:
    """Monta requests de verificacao de manchetes NEWS_* com evidencia RSS."""
    import pandas as pd

    from .verify_news import _factchecker, gnews, is_claim_like

    v1 = pd.read_csv("FakenewsBR_sanitized.csv", usecols=["rid"])
    df = pd.read_csv(args.v2, low_memory=False)
    new = df.iloc[len(v1):].copy()
    new = new[new["dataset_name"].astype(str).str.startswith("NEWS_")]
    new = new[new["text"].astype(str).map(is_claim_like)]
    if args.limit:
        new = new.head(args.limit)

    cache: dict[str, list[dict]] = {}
    cp = Path(args.cache) if args.cache else None
    if cp and cp.exists():
        for line in cp.open("r", encoding="utf-8"):
            try:
                r = json.loads(line)
                cache[r["q"]] = r["items"]
            except json.JSONDecodeError:
                continue
    sess = requests.Session()

    # busca de evidencia: cache -> threads com rate limit global
    missing = [q for q in {str(r.text)[:120] for r in new.itertuples(index=False)}
               if q not in cache]
    if missing and not getattr(args, "dry_run", False):
        import concurrent.futures as cf
        import threading
        import time as _t
        lock = threading.Lock()
        last = [0.0]
        delay = float(getattr(args, "delay", 0.4))

        def one(q):
            with lock:
                wait = delay - (_t.monotonic() - last[0])
                if wait > 0:
                    _t.sleep(wait)
                last[0] = _t.monotonic()
            return q, gnews(q, requests.Session())

        workers = int(getattr(args, "workers", 4))
        print(f"[llm] buscando evidencia para {len(missing):,} manchetes "
              f"({workers} workers, {delay}s)", flush=True)
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            for k, (q, items) in enumerate(ex.map(one, missing)):
                cache[q] = items
                if (k + 1) % 500 == 0:
                    print(f"[llm] evidencia {k+1}/{len(missing)}", flush=True)
        if cp is not None:
            with cp.open("a", encoding="utf-8") as f:
                for q in missing:
                    f.write(json.dumps({"q": q, "items": cache[q]},
                                       ensure_ascii=False) + "\n")

    reqs = []
    for r in new.itertuples(index=False):
        q = str(r.text)[:120]
        items = cache.get(q, [])
        ev = ""
        for i, it in enumerate(items[:8]):
            fc = _factchecker(it)
            tag = f" [CHECADOR:{fc}]" if fc else ""
            ev += (f"[{i}] {it.get('domain','')} ({it.get('pub','')[:16]})"
                   f"{tag}: {it.get('title','')[:160]}\n")
        prompt = (
            f"MANCHETE: {r.text}\nDATA: {getattr(r, 'date_iso', '')}\n\n"
            f"EVIDENCIAS (Google News):\n{ev or '(nenhuma)'}\n"
            "Classifique a manchete conforme as regras do sistema.")
        reqs.append({"custom_id": custom_id("verify_headline", "news",
                                            str(r.rid)),
                     "task": "verify_headline", "source": "news",
                     "publisher": r.dataset_name, "lang_variant": "pt-BR",
                     "url": str(r.url_review), "text": str(r.text),
                     "rid": int(r.rid), "prompt": prompt})
    return reqs


def prepare(args) -> int:
    global MODEL
    if getattr(args, "model", None):
        MODEL = args.model
    if getattr(args, "task", "label") == "verify-news":
        reqs = build_verify(args)
        out = PROC / "llm_verify_requests.jsonl"
    else:
        reqs = build(args.raw_dir)
        out = PROC / "llm_requests.jsonl"
    PROC.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in reqs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tin = sum(estimate_tokens(r.get("prompt") or r.get("text", "")) for r in reqs)
    tout = 220 * len(reqs)
    cost = tin / 1e6 * PRICE_IN + tout / 1e6 * PRICE_OUT
    print(f"[llm] {len(reqs)} requests -> {out}")
    print(f"[llm] custo estimado {MODEL}: US$ {cost:.4f} "
          f"(in {tin/1e6:.3f}M tok, out {tout/1e6:.3f}M tok)")
    if getattr(args, "dry_run", False):
        print("[llm] --dry-run: nada enviado. Defina OPENROUTER_API_KEY e rode "
              "`pipeline llm-submit --task verify-news`.")
    return len(reqs)


# ------------------------------------------------------------------- submit
def _headers() -> dict:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit(
            "OPENROUTER_API_KEY nao definida. Defina a variavel de ambiente "
            "voce mesmo (nao cole a chave no chat) e rode de novo.")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"batches": {}}


def submit(args) -> int:
    req_p = (PROC / "llm_verify_requests.jsonl"
             if getattr(args, "task", "label") == "verify-news"
             else PROC / "llm_requests.jsonl")
    if not req_p.exists():
        print(f"rode `pipeline llm-prepare --task {getattr(args, 'task', 'label')}` antes")
        return 1
    reqs = [json.loads(l) for l in req_p.read_text(encoding="utf-8").splitlines() if l]
    state_p = PROC / "llm_batches.json"
    state = _load_state(state_p)
    headers = _headers()
    n_batches = 0
    for i in range(0, len(reqs), BATCH_CHUNK):
        chunk = reqs[i:i + BATCH_CHUNK]
        body = {
            "endpoint": "/v1/chat/completions",   # serializar antes de requests
            "model": MODEL,
            "requests": [{"custom_id": r["custom_id"],
                          "body": _body(r["task"], r.get("text", ""),
                                        r.get("prompt"))} for r in chunk],
        }
        # a ordem das chaves importa: endpoint e model ja vem antes
        r = requests.post(f"{OPENROUTER_BASE}/beta/batches", headers=headers,
                          data=json.dumps(body), timeout=120)
        if r.status_code >= 400:
            print(f"[llm] batch {i//BATCH_CHUNK} erro {r.status_code}: {r.text[:300]}")
            if MODEL.endswith(":batch") and "model" in r.text.lower():
                print("[llm] tentando slug sem ':batch'...")
                body["model"] = MODEL.removesuffix(":batch")
                r = requests.post(f"{OPENROUTER_BASE}/beta/batches", headers=headers,
                                  data=json.dumps(body), timeout=120)
        if r.status_code >= 400:
            print(f"[llm] falhou: {r.status_code} {r.text[:300]}")
            continue
        bid = r.json().get("id")
        state["batches"][bid] = {"n": len(chunk),
                                 "submitted_at": datetime.now(timezone.utc).isoformat()}
        n_batches += 1
        print(f"[llm] submetido batch {bid} ({len(chunk)} requests)")
    state_p.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    return n_batches


def collect(args) -> int:
    state_p = PROC / "llm_batches.json"
    state = _load_state(state_p)
    headers = _headers()
    out = (PROC / "llm_verify_results.jsonl"
           if getattr(args, "task", "label") == "verify-news"
           else PROC / "llm_results.jsonl")
    done = 0
    with out.open("a", encoding="utf-8") as f:
        for bid, meta in list(state["batches"].items()):
            if meta.get("collected"):
                continue
            r = requests.get(f"{OPENROUTER_BASE}/beta/batches/{bid}",
                             headers=headers, timeout=60)
            if r.status_code >= 400:
                print(f"[llm] {bid}: {r.status_code}")
                continue
            data = r.json()
            status = data.get("status")
            print(f"[llm] {bid}: {status}")
            if status in ("failed", "expired", "cancelled"):
                meta["collected"] = True
                continue
            if status != "completed":
                continue
            for res in data.get("results", []):
                cid = res.get("custom_id")
                body = (res.get("response") or {}).get("body") or {}
                content = ""
                choices = body.get("choices") or []
                if choices:
                    content = (choices[0].get("message") or {}).get("content", "")
                f.write(json.dumps({"custom_id": cid, "content": content,
                                    "error": res.get("error")}, ensure_ascii=False) + "\n")
                done += 1
            meta["collected"] = True
    state_p.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[llm] {done} resultados -> {out}")
    return done


def apply_labels(args) -> int:
    """Converte llm_verify_results.jsonl em FakenewsBR_v2_llm_labels.csv."""
    import pandas as pd
    res_p = PROC / "llm_verify_results.jsonl"
    req_p = PROC / "llm_verify_requests.jsonl"
    if not res_p.exists():
        print("sem resultados; rode llm-collect antes")
        return 1
    reqs = {}
    if req_p.exists():
        for line in req_p.open("r", encoding="utf-8"):
            r = json.loads(line)
            reqs[r["custom_id"]] = r
    rows = []
    for line in res_p.open("r", encoding="utf-8"):
        r = json.loads(line)
        base = reqs.get(r.get("custom_id"), {})
        try:
            obj = json.loads(r.get("content") or "{}")
        except json.JSONDecodeError:
            obj = {}
        rows.append({
            "rid": base.get("rid"), "text": base.get("text"),
            "verdict": obj.get("verdict", "unknown"),
            "is_claim": obj.get("is_claim"),
            "confidence": obj.get("confidence"),
            "claim": obj.get("claim", ""),
            "rationale": obj.get("rationale", ""),
            "evidence_idx": json.dumps(obj.get("evidence_idx", [])),
            "erro": r.get("error"),
        })
    df = pd.DataFrame(rows)
    out = Path("FakenewsBR_v2_llm_labels.csv")
    df.to_csv(out, index=False)
    dist = df["verdict"].value_counts().to_dict()
    print(f"[llm] {len(df):,} rotulos -> {out}")
    print(f"[llm] distribuicao: {dist} | "
          f"abstencao={dist.get('unknown', 0)}")
    return len(df)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", type=Path, default=RAW)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--task", choices=["label", "verify-news"], default="label")
    ap.add_argument("--v2", type=Path, default=Path("FakenewsBR_sanitized_v2.csv"))
    ap.add_argument("--cache", type=Path,
                    default=Path("FakenewsBR_v2_news_verification.cache.jsonl"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--delay", type=float, default=0.4)
    a = ap.parse_args()
    if a.submit:
        submit(a)
    elif a.collect:
        collect(a)
    elif a.apply:
        apply_labels(a)
    else:
        prepare(a)


if __name__ == "__main__":
    main()
