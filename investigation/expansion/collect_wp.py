"""Coleta WP REST (WordPress) para checadores e portais.

Grava registros brutos em `raw/<source>.jsonl` e um cursor de resume em
`raw/<source>.resume.json` (ultima pagina por intervalo). WP REST limita
`per_page` a 100. Para portais, a coleta e estratificada por ano usando
`after`/`before`; dentro do ano pagina linearmente (`page`) ate o teto
de paginas por ano (`--pages-per-year`).

Uso:
    python -m investigation.expansion.collect_wp --source boatos
    python -m investigation.expansion.collect_wp --source poder360 --from 2018 --to 2025
"""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .http import PoliteSession
from .sources import ALL_SOURCES, Source

RAW = Path("investigation/expansion/raw")
FIELDS = "id,date,date_gmt,link,title,content,categories,tags,excerpt"
FIELDS_PORTAL = "id,date,date_gmt,link,title,categories,tags"


def _load_categories(sess: PoliteSession, src: Source) -> dict[int, str]:
    out: dict[int, str] = {}
    page = 1
    while True:
        data, code = sess.get_json(
            f"{src.base_url}/categories",
            params={"per_page": 100, "page": page, "_fields": "id,name"})
        if not data:
            break
        for c in data:
            out[c["id"]] = c["name"]
        if len(data) < 100:
            break
        page += 1
    return out


def _load_tags(sess: PoliteSession, src: Source) -> dict[int, str]:
    out: dict[int, str] = {}
    page = 1
    while True:
        data, code = sess.get_json(
            f"{src.base_url}/tags",
            params={"per_page": 100, "page": page, "_fields": "id,name"})
        if not data:
            break
        for t in data:
            out[t["id"]] = t["name"]
        if len(data) < 100:
            break
        page += 1
    return out


def _strip_html(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&nbsp;?", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def collect_source(src: Source, from_year: int, to_year: int,
                   pages_per_year: int | None, sess: PoliteSession,
                   max_pages_total: int | None = None) -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    out_path = RAW / f"{src.key}.jsonl"
    resume_path = RAW / f"{src.key}.resume.json"
    resume = {}
    if resume_path.exists():
        resume = json.loads(resume_path.read_text(encoding="utf-8"))

    print(f"[{src.key}] carregando taxonomias...", flush=True)
    cats = _load_categories(sess, src)
    # portais nao usam tags na extracao (manchete) e alguns tem milhares de
    # paginas de tags (Poder360: 2222, Brasil de Fato: 663) -> pular.
    tags = _load_tags(sess, src) if src.kind == "wp_checker" else {}
    print(f"[{src.key}] {len(cats)} categorias, {len(tags)} tags", flush=True)

    n_written = 0
    total_pages = 0
    out = out_path.open("a", encoding="utf-8")
    try:
        for year in range(from_year, to_year + 1):
            key = str(year)
            start_page = int(resume.get(key, 1))
            page = start_page
            while True:
                if pages_per_year is not None and page - start_page >= pages_per_year:
                    break
                if max_pages_total is not None and total_pages >= max_pages_total:
                    break
                params = {
                    "per_page": 100, "page": page,
                    "_fields": FIELDS if src.kind == "wp_checker" else FIELDS_PORTAL,
                    "after": f"{year}-01-01T00:00:00",
                    "before": f"{year}-12-31T23:59:59",
                    "orderby": "date", "order": "asc",
                }
                data, code = sess.get_json(f"{src.base_url}/posts", params=params)
                if not data:
                    if code == 400:
                        # WP devolve 400 quando page > total de paginas
                        break
                    if code in (401, 403, 404):
                        print(f"[{src.key}] {code} em {src.base_url}", flush=True)
                        break
                    time.sleep(3)
                    break
                for p in data:
                    title = _strip_html((p.get("title") or {}).get("rendered", ""))
                    content_html = (p.get("content") or {}).get("rendered", "")
                    content = _strip_html(content_html)
                    date_iso = (p.get("date") or "")[:10]
                    if not date_iso and p.get("date_gmt"):
                        date_iso = (p.get("date_gmt") or "")[:10]
                    rec = {
                        "collector": "wp", "source": src.key,
                        "kind": src.kind, "dataset_name": src.dataset_name,
                        "source_type": src.source_type,
                        "label_source": src.label_source,
                        "lang_variant": src.lang_variant,
                        "id": p.get("id"), "date": p.get("date"),
                        "date_iso": date_iso, "link": p.get("link"),
                        "title": title, "content": content,
                        "content_html": content_html,
                        "categories": [cats.get(c, str(c)) for c in (p.get("categories") or [])],
                        "tags": [tags.get(t, str(t)) for t in (p.get("tags") or [])],
                    }
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n_written += 1
                total_pages += 1
                resume[key] = page + 1
                resume_path.write_text(json.dumps(resume), encoding="utf-8")
                if len(data) < 100:
                    break
                page += 1
                if total_pages % 20 == 0:
                    print(f"[{src.key}] ano {year} pag {page} total {n_written}",
                          flush=True)
            if total_pages and max_pages_total and total_pages >= max_pages_total:
                break
    finally:
        out.close()
    print(f"[{src.key}] {n_written} posts gravados em {out_path}", flush=True)
    return n_written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, choices=sorted(ALL_SOURCES))
    ap.add_argument("--from", dest="from_year", type=int, default=2010)
    ap.add_argument("--to", dest="to_year", type=int,
                    default=datetime.now(timezone.utc).year)
    ap.add_argument("--pages-per-year", type=int, default=None)
    ap.add_argument("--max-pages-total", type=int, default=None)
    a = ap.parse_args()
    src = ALL_SOURCES[a.source]
    if src.kind not in ("wp_checker", "wp_portal"):
        raise SystemExit(f"fonte {a.source} nao e WP REST")
    sess = PoliteSession()
    ok, why = sess.allows(src.base_url)
    if not ok:
        raise SystemExit(f"fonte {a.source} bloqueada: {why}")
    collect_source(src, a.from_year, a.to_year, a.pages_per_year, sess,
                   a.max_pages_total)


if __name__ == "__main__":
    main()
