"""Coleta por sitemap: G1 Fato ou Fake e Poligrafo.

Grava `raw/g1.jsonl` e `raw/poligrafo.jsonl` com um registro por artigo:
url, h1/title, og:title, veredito extraido do HTML e data.

Nao usa bs4/lxml: parser proprio com `html.parser`.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path

from .http import PoliteSession

RAW = Path("investigation/expansion/raw")

G1_INDEX = "https://g1.globo.com/sitemap/g1/sitemap.xml"
POLI_SITEMAPS = ["https://poligrafo.sapo.pt/fact_check-sitemap.xml"] + [
    f"https://poligrafo.sapo.pt/fact_check-sitemap{i}.xml" for i in range(2, 14)
]


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.h1: list[str] = []
        self.meta: dict[str, str] = {}
        self.jsonld: list[str] = []
        self._cur_h1: list[str] | None = None
        self._in_script_ld = False
        self._script_buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            key = a.get("property") or a.get("name") or ""
            if key.startswith("og:") or key == "description":
                self.meta[key] = a.get("content", "")
        if tag == "script" and a.get("type") == "application/ld+json":
            self._in_script_ld = True
            self._script_buf = []
        if tag == "h1":
            self._cur_h1 = []

    def handle_endtag(self, tag):
        if tag == "script" and self._in_script_ld:
            self._in_script_ld = False
            self.jsonld.append("".join(self._script_buf))
        if tag == "h1" and self._cur_h1 is not None:
            self.h1.append("".join(self._cur_h1).strip())
            self._cur_h1 = None

    def handle_data(self, data):
        if self._in_script_ld:
            self._script_buf.append(data)
        if self._cur_h1 is not None:
            self._cur_h1.append(data)


def parse_page(text: str) -> PageParser:
    p = PageParser()
    try:
        p.feed(text)
    except Exception:
        pass
    return p


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


def _sitemap_locs(sess: PoliteSession, url: str) -> list[str]:
    r = sess.get(url)
    if r is None or r.status_code != 200:
        return []
    return re.findall(r"<loc>\s*(.*?)\s*</loc>", r.text, flags=re.S | re.I)


def collect_g1(sess: PoliteSession, out: Path, from_year: int = 2018) -> int:
    locs = _sitemap_locs(sess, G1_INDEX)
    print(f"[g1] {len(locs)} sitemaps no indice", flush=True)
    daily = [u for u in locs if re.search(r"/(\d{4})/(\d{2})/(\d{2})_", u)]
    daily = [u for u in daily if int(re.search(r"/(\d{4})/", u).group(1)) >= from_year]
    print(f"[g1] {len(daily)} sitemaps diarios >= {from_year}", flush=True)
    # resume: pular sitemaps ja processados (marca por url do dia)
    resume_path = out.with_suffix(".resume.json")
    done = set(json.loads(resume_path.read_text(encoding="utf-8"))) if resume_path.exists() else set()
    n = 0
    with out.open("a", encoding="utf-8") as f:
        for i, sm in enumerate(daily):
            if sm in done:
                continue
            for art in _sitemap_locs(sess, sm):
                if "/fato-ou-fake/" not in art:
                    continue
                date_iso = ""
                m = re.search(r"/noticia/(\d{4})/(\d{2})/(\d{2})/", art)
                if m:
                    date_iso = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                r = sess.get(art)
                if r is None or r.status_code != 200:
                    continue
                pp = parse_page(r.text)
                h1 = next((h for h in pp.h1 if re.search(r"#?\s*(FAKE|FATO)", h, re.I)), "")
                rec = {"collector": "sitemap", "source": "g1", "kind": "g1",
                       "dataset_name": "FC_G1", "url": art, "date_iso": date_iso,
                       "h1": _clean(h1), "og_title": _clean(pp.meta.get("og:title", ""))}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
            done.add(sm)
            resume_path.write_text(json.dumps(sorted(done)), encoding="utf-8")
            if (i + 1) % 25 == 0:
                print(f"[g1] {i+1}/{len(daily)} sitemaps, {n} artigos", flush=True)
    print(f"[g1] {n} artigos gravados", flush=True)
    return n


def _poligrafo_verdict(html_text: str) -> str:
    m = re.search(
        r'fact-check-result[^>]*>(.*?)</div>', html_text,
        flags=re.S | re.I)
    if not m:
        return ""
    txt = re.sub(r"<[^>]+>", " ", m.group(1))
    txt = _clean(txt)
    return txt


def collect_poligrafo(sess: PoliteSession, out: Path, limit: int = 0,
                      workers: int = 1, delay: float = 0.5) -> int:
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    import requests as rq

    urls: list[str] = []
    for sm in POLI_SITEMAPS:
        locs = _sitemap_locs(sess, sm)
        if not locs:
            continue
        # sitemap pode apontar para sub-sitemaps (xml) ou para artigos
        subs = [u for u in locs if u.endswith(".xml")]
        arts = [u for u in locs if not u.endswith(".xml")]
        for s in subs:
            arts += [u for u in _sitemap_locs(sess, s) if not u.endswith(".xml")]
        print(f"[poligrafo] {sm.split('/')[-1]}: {len(arts)} artigos", flush=True)
        urls += arts
    urls = sorted(set(urls))
    if limit:
        urls = urls[:limit]
    resume_path = out.with_suffix(".resume.json")
    done = set(json.loads(resume_path.read_text(encoding="utf-8"))) if resume_path.exists() else set()
    todo = [u for u in urls if u not in done]
    print(f"[poligrafo] {len(todo)} URLs a coletar ({len(done)} ja feitas), "
          f"{workers} workers, delay={delay}s", flush=True)
    n = 0
    lock = threading.Lock()
    out.parent.mkdir(parents=True, exist_ok=True)
    f = out.open("a", encoding="utf-8")
    tls = threading.local()
    rate_lock = threading.Lock()
    next_at = [0.0]
    ua = {"User-Agent": "FakenewsBR-research/2.0 "
                        "(+https://github.com/thiago-cg/FakenewsBR; research)"}

    def _sess():
        s = getattr(tls, "s", None)
        if s is None:
            s = rq.Session()
            s.headers.update(ua)
            tls.s = s
        return s

    def one(art: str):
        with rate_lock:
            wait = next_at[0] - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            next_at[0] = time.monotonic() + delay
        try:
            r = _sess().get(art, timeout=(10, 25), allow_redirects=True)
        except rq.RequestException:
            return art, None
        if r.status_code != 200:
            return art, None
        verdict = _poligrafo_verdict(r.text)
        pp = parse_page(r.text)
        date_iso = ""
        for js in pp.jsonld:
            m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', js)
            if m:
                date_iso = m.group(1)[:10]
                break
        rec = {"collector": "sitemap", "source": "poligrafo",
               "kind": "poligrafo", "dataset_name": "FC_POLIGRAFO",
               "url": art, "date_iso": date_iso, "verdict": verdict,
               "og_title": _clean(pp.meta.get("og:title", "")),
               "h1": _clean(pp.h1[0] if pp.h1 else "")}
        return art, rec

    try:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            futs = {ex.submit(one, u): u for u in todo}
            for i, fut in enumerate(as_completed(futs)):
                art, rec = fut.result()
                if rec is not None:
                    with lock:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        done.add(art)
                        n += 1
                        if n % 50 == 0:
                            f.flush()
                            resume_path.write_text(json.dumps(sorted(done)),
                                                   encoding="utf-8")
                            print(f"[poligrafo] {i+1}/{len(todo)}, {n} artigos",
                                  flush=True)
    finally:
        f.close()
        resume_path.write_text(json.dumps(sorted(done)), encoding="utf-8")
    print(f"[poligrafo] {n} artigos gravados", flush=True)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, choices=["g1", "poligrafo"])
    ap.add_argument("--from-year", type=int, default=2018)
    ap.add_argument("--limit", type=int, default=0,
                    help="maximo de URLs no poligrafo (0 = sem limite)")
    ap.add_argument("--workers", type=int, default=1,
                    help="workers paralelos no poligrafo")
    ap.add_argument("--delay", type=float, default=1.0,
                    help="delay por host (robots crawl-delay tem precedencia)")
    a = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    sess = PoliteSession(delay=a.delay)
    if a.source == "g1":
        collect_g1(sess, RAW / "g1.jsonl", a.from_year)
    else:
        collect_poligrafo(sess, RAW / "poligrafo.jsonl", a.limit, a.workers,
                          a.delay)


if __name__ == "__main__":
    main()
