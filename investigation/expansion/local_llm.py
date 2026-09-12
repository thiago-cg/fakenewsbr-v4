"""Cliente da LLM local (Unsloth Studio, API OpenAI-compativel).

- Base URL e chave vem de `LOCAL_LLM_BASE` / `LOCAL_LLM_KEY` ou dos arquivos
  em `%TEMP%/opencode/` gerados na configuracao.
- Sem dependencia nova: usa `requests`.
- Funcoes: `list_models()`, `chat()`, `chat_json()` (com parsing robusto de
  JSON e reparo de cercas), `health()`.
- Nunca gravar a chave no repositorio.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import requests

DEFAULT_BASE = "http://192.168.15.8:8888"
KEY_FILE = Path(os.environ.get("TEMP", ".")) / "opencode" / "unsloth_key.txt"
DEFAULT_MODEL = "openbmb/MiniCPM5-2B-GGUF"


def base_url() -> str:
    return os.environ.get("LOCAL_LLM_BASE", DEFAULT_BASE).rstrip("/")


def api_key() -> str:
    k = os.environ.get("LOCAL_LLM_KEY")
    if k:
        return k
    if KEY_FILE.exists():
        return KEY_FILE.read_text(encoding="utf-8").strip()
    raise SystemExit(
        "sem chave da LLM local: defina LOCAL_LLM_KEY ou gere o arquivo "
        f"{KEY_FILE}")


def _headers() -> dict:
    return {"Authorization": "Bearer " + api_key(),
            "Content-Type": "application/json"}


def health(timeout: int = 10) -> dict:
    try:
        r = requests.get(base_url() + "/v1/models", headers=_headers(),
                         timeout=timeout)
        return {"ok": r.status_code == 200, "status": r.status_code}
    except requests.RequestException as e:
        return {"ok": False, "error": str(e)}


def list_models(timeout: int = 15) -> list[str]:
    r = requests.get(base_url() + "/v1/models", headers=_headers(),
                     timeout=timeout)
    r.raise_for_status()
    return [m.get("id") for m in r.json().get("data", [])]


def chat(messages: list[dict], model: str = DEFAULT_MODEL,
         temperature: float = 0.0, max_tokens: int = 400,
         timeout: int = 300, retries: int = 3,
         enable_thinking: bool = False, extra: dict | None = None) -> str:
    body = {"model": model, "messages": messages, "temperature": temperature,
            "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": enable_thinking}}
    if extra:
        body.update(extra)
    last = None
    for attempt in range(retries):
        try:
            r = requests.post(base_url() + "/v1/chat/completions",
                              headers=_headers(), json=body, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(2 ** attempt, 20))
                continue
            r.raise_for_status()
            d = r.json()
            return (d.get("choices") or [{}])[0].get("message", {}).get(
                "content", "")
        except requests.RequestException as e:
            last = e
            time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"chat falhou: {last}")


def parse_json(text: str) -> dict | None:
    """Parsing robusto: JSON puro, cercas ```json, ou primeiro objeto {...}."""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I | re.S).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", t, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def chat_json(messages: list[dict], **kw) -> dict | None:
    return parse_json(chat(messages, **kw))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", action="store_true")
    ap.add_argument("--ping", action="store_true")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--prompt", default="Responda apenas: ok")
    a = ap.parse_args()
    if a.models:
        print("\n".join(list_models()))
    elif a.ping:
        t = time.time()
        out = chat([{"role": "user", "content": a.prompt}], model=a.model,
                   max_tokens=50)
        print(f"{time.time()-t:.1f}s | {out[:300]}")
    else:
        print(json.dumps(health(), ensure_ascii=False))
