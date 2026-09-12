"""Minera frases de CORRECAO verbatim nos artigos de checadores (LLM local).

Para cada artigo de Boatos/E-farsas/Bereia, pede a LLM local a frase que
corrige a alegacao (a informacao verdadeira), com validacao anti-alucinacao:
a frase precisa aparecer (normalizada) no proprio artigo.

Saidas:
  processed/corrections_results.jsonl   (rid do artigo, correction, aceito)
  processed/records_corrections.jsonl   (linhas canonicas, label=true,
                                         dataset FC_<PUB>_CORRECAO)

Uso:
    python -m investigation.expansion.mine_corrections --pub efarsas --limit 60
    python -m investigation.expansion.mine_corrections --pub all --max-minutes 480
    python -m investigation.expansion.mine_corrections --build
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import local_llm
from . import schema as sch

RAW = Path("investigation/expansion/raw")
PROC = Path("investigation/expansion/processed")
RES = PROC / "corrections_results.jsonl"
OUT = PROC / "records_corrections.jsonl"

PUBS = {"boatos": "FC_BOATOS_CORRECAO", "efarsas": "FC_EFARSAS_CORRECAO",
        "bereia": "FC_BEREIA_CORRECAO"}

SYSTEM = (
    "Voce recebe o texto de um artigo de checagem de fatos que desmente uma "
    "alegacao. Extraia LITERALMENTE a UNICA frase do artigo que informa o que "
    "e verdade (a correcao do boato), copiada sem reescrever. A frase deve ser "
    "uma afirmacao factual sobre o caso (ex.: 'o video foi gravado em 2014 em "
    "outro pais'), e NAO pode ser: titulo, pergunta, opiniao, anuncio, pedido "
    "para seguir/assinar/clicar, nome de podcast/ranking, biografia de autor "
    "ou frase generica. Se nao houver uma correcao clara, responda vazio. "
    "Responda APENAS JSON: {\"correction\":\"<frase verbatim>\"}."
)

NOISE = (
    "clique", "assine", "leia ", "leia-", "siga", "curta", "compartilhe",
    "ranking", "podcast", "publicidade", "patrocin", "veja tambem",
    "veja também", "inscreva", "canal", "newsletter", "whatsapp do",
    "e-mail", "email", "contato", "copyright", "todos os direitos",
    "fomos ", "nosso ", "nossa ", "entrevist", "apresentador",
    "episodio", "episódio", "programa ", "abaixo", "acima", "confira",
)

MARKERS = (
    "na verdade", "nao e verdade", "não é verdade", "e falso", "é falso",
    "e mentira", "é mentira", "nao procede", "não procede", "esclarece",
    "explica que", "segundo o", "segundo a", "de acordo com", "trata-se de",
    "o video", "o vídeo", "a imagem", "a foto", "foi gravado", "foi filmado",
    "nao passa de", "não passa de", "informacao falsa", "informação falsa",
    "e verdade que", "é verdade que", "a verdade e", "a verdade é",
)


def _html(s: str) -> str:
    import html
    return html.unescape(s or "")


def _norm(s: str) -> str:
    from .dedup import normalize_text
    return normalize_text(s)


def article_text(rec: dict) -> str:
    return str(rec.get("content") or "").strip()


def focus_excerpt(text: str) -> str:
    """Prioriza a conclusao do artigo (onde fica a correcao)."""
    low = text.lower()
    idx = max(low.rfind("conclusão"), low.rfind("conclusao"))
    if idx >= 0:
        return text[idx:idx + 2500]
    return text[-2500:]


def critic(correction: str, excerpt: str) -> bool:
    """Segunda passada: a frase realmente corrige o boato?"""
    prompt = (
        "Trecho de um artigo de checagem:\n" + excerpt[:1800] +
        "\n\nFRASE EXTRAIDA:\n" + correction[:400] +
        "\n\nEssa frase informa o que e verdade e corrige o boato do artigo? "
        "Responda apenas SIM ou NAO.")
    try:
        out = local_llm.chat(
            [{"role": "system",
              "content": "Responda apenas SIM ou NAO, sem explicar."},
             {"role": "user", "content": prompt}],
            temperature=0.0, max_tokens=8)
    except Exception:  # noqa: BLE001
        return False
    return out.strip().lower().startswith("s")


def validate(correction: str, article: str) -> bool:
    c_raw = _html(correction).strip()
    c = _norm(c_raw)
    if len(c) < 40 or len(c) > 600:
        return False
    if c_raw.endswith("?"):
        return False
    if any(n in c for n in NOISE):
        return False
    a = _norm(article)
    if not a:
        return False
    if c not in a:
        ct = set(c.split())
        at = set(a.split())
        if not ct or len(ct & at) / len(ct) < 0.9:
            return False
    pos = a.find(c)
    has_marker = any(m in c for m in MARKERS)
    in_last_half = pos >= len(a) / 2 if pos >= 0 else False
    return has_marker or in_last_half


def load_articles(pub: str) -> list[dict]:
    p = RAW / f"{pub}.jsonl"
    out = []
    if not p.exists():
        return out
    for line in p.open("r", encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if article_text(d):
            d["_pub"] = pub
            out.append(d)
    return out


def already_done() -> set[str]:
    done = set()
    if RES.exists():
        for line in RES.open("r", encoding="utf-8"):
            try:
                done.add(str(json.loads(line).get("key")))
            except json.JSONDecodeError:
                continue
    return done


def run(pub: str, limit: int, max_minutes: float, workers: int,
        max_tokens: int) -> int:
    articles = load_articles(pub) if pub != "all" else sum(
        (load_articles(p) for p in PUBS), [])
    done = already_done()

    def key_of(a):
        return f"{a.get('_pub', pub)}:{a.get('id')}"

    todo = [a for a in articles if key_of(a) not in done]
    if limit:
        todo = todo[:limit]
    print(f"[corr] {len(todo):,} artigos a processar (pub={pub})", flush=True)
    PROC.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    n_ok = 0
    lock = threading.Lock()

    def one(a):
        key = key_of(a)
        full = _html(article_text(a))
        excerpt = focus_excerpt(full)
        try:
            out = local_llm.chat(
                [{"role": "system", "content": SYSTEM},
                 {"role": "user", "content": f"--- ARTIGO ---\n{excerpt[:3000]}"}],
                temperature=0.0, max_tokens=max_tokens)
        except Exception as e:  # noqa: BLE001
            return {"key": key, "correction": "", "accepted": 0,
                    "erro": str(e)[:200]}
        obj = local_llm.parse_json(out) or {}
        corr = _html(str(obj.get("correction", ""))).strip()
        ok = bool(corr) and validate(corr, full) and critic(corr, excerpt)
        return {"key": key, "rid_src": a.get("id"), "correction": corr,
                "accepted": int(ok), "erro": ""}

    with RES.open("a", encoding="utf-8") as f:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for res in ex.map(one, todo):
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
                f.flush()
                n_ok += res["accepted"]
                if int((time.time() - t0) / 60) > max_minutes:
                    print("[corr] orcamento de tempo atingido", flush=True)
                    break
    print(f"[corr] aceitas: {n_ok} de {len(todo)} ({time.time()-t0:.0f}s)",
          flush=True)
    return n_ok


def build() -> int:
    """Converte correcoes aceitas em linhas canonicas para o merge."""
    if not RES.exists():
        print("sem resultados")
        return 0
    # mapa artigo -> metadados por publicacao
    meta = {}
    for pub in PUBS:
        for a in load_articles(pub):
            meta[f"{a.get('_pub', pub)}:{a.get('id')}"] = a
    n = 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for line in RES.open("r", encoding="utf-8"):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not r.get("accepted"):
                continue
            key = str(r.get("key"))
            pub = key.split(":")[0]
            a = meta.get(key, {})
            corr = _html(r.get("correction", "")).strip()
            if not corr:
                continue
            url = a.get("link", "")
            rid = sch.make_rid(url, "correction", key)
            rec = sch.Record(
                rid=rid, dataset_name=PUBS.get(pub, "FC_CORRECAO"),
                source_type="news", source_description=f"{pub}-correcao",
                label="true", date_iso=a.get("date_iso") or None,
                url_review=url, text=corr, factcheck_rating="Correcao",
                factcheck_claimant="", factcheck_url=url,
                label_source="correction", text_role="correction",
                publisher=pub, lang_variant="pt-BR", collector="correction",
                source_url=url,
                collected_at=datetime.now(timezone.utc).isoformat(
                    timespec="seconds"),
                mentions_ai=int(sch.mentions_ai(corr)))
            try:
                rec.finalize()
            except ValueError:
                continue
            row = rec.csv_row()
            row["_provenance"] = rec.prov_row("correction")
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    print(f"[corr] {n} linhas de correcao -> {OUT}")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pub", choices=["boatos", "efarsas", "bereia", "all"],
                    default="efarsas")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-minutes", type=float, default=480)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-tokens", type=int, default=160)
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args()
    if a.build:
        build()
    else:
        run(a.pub, a.limit, a.max_minutes, a.workers, a.max_tokens)


if __name__ == "__main__":
    main()
