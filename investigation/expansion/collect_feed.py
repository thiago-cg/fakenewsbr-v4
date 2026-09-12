"""Coleta do feed ClaimReview (Data Commons) -> registros brutos.

Le `raw/datacommons_claimreview.json` (199 MB), filtra por whitelist de
publishers PT (`.br`/`.pt`/checadores) e grava `raw/feed.jsonl`.

O feed tem 93.436 DataFeedItem; cada `item` pode ser uma lista de ClaimReview
(alguns `item:null`). Nao acessa a rede.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

from .sources import feed_publisher

RAW = Path("investigation/expansion/raw")


def _domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    return (m.group(1) if m else "").lower().removeprefix("www.")


def _clean(s) -> str:
    if not isinstance(s, str):
        return ""
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def iter_items(feed: dict):
    for el in feed.get("dataFeedElement", []):
        if not isinstance(el, dict):
            continue
        item = el.get("item")
        if item is None:
            continue
        if isinstance(item, dict):
            item = [item]
        for cr in item:
            if isinstance(cr, dict) and cr.get("@type") == "ClaimReview":
                yield cr


def collect(feed_path: Path, out: Path) -> int:
    print(f"carregando feed {feed_path} ({feed_path.stat().st_size/1e6:.1f} MB)...",
          flush=True)
    feed = json.loads(feed_path.read_text(encoding="utf-8"))
    n = 0
    seen = set()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for cr in iter_items(feed):
            url = cr.get("url") or ""
            d = _domain(url)
            pub = feed_publisher(d)
            if not pub:
                continue
            ds, publisher, lang = pub
            claim = _clean(cr.get("claimReviewed"))
            rating = ""
            rr = cr.get("reviewRating")
            if isinstance(rr, dict):
                rating = _clean(rr.get("alternateName") or rr.get("ratingValue"))
            claimant = ""
            ir = cr.get("itemReviewed")
            if isinstance(ir, dict):
                a = ir.get("author")
                if isinstance(a, dict):
                    claimant = _clean(a.get("name"))
                elif isinstance(a, list) and a and isinstance(a[0], dict):
                    claimant = _clean(a[0].get("name"))
            author = ""
            au = cr.get("author")
            if isinstance(au, dict):
                author = _clean(au.get("name"))
            date = _clean(cr.get("datePublished"))[:10]
            key = (url, claim)
            if key in seen:
                continue
            seen.add(key)
            rec = {
                "collector": "feed", "source": "feed", "kind": "feed",
                "dataset_name": ds, "publisher": publisher, "lang_variant": lang,
                "url": url, "claimReviewed": claim, "rating": rating,
                "claimant": claimant, "review_author": author, "date_iso": date,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    print(f"feed: {n} registros PT gravados em {out}", flush=True)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", type=Path,
                    default=RAW / "datacommons_claimreview.json")
    ap.add_argument("--out", type=Path, default=RAW / "feed.jsonl")
    a = ap.parse_args()
    collect(a.feed, a.out)


if __name__ == "__main__":
    main()
