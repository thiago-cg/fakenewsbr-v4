"""Coleta via Google Fact Check Tools API (`claims:search`).

IMPORTANTE: o endpoint `pages` do link original e CRUD do ClaimReview da
PROPRIA organizacao (OAuth `factchecktools`) e NAO le checagens de terceiros.
A leitura correta e `claims:search`, aqui com `reviewPublisherSiteFilter`
(itera a whitelist de checadores), sem `query` — `query` so e obrigatorio
quando nao ha filtro de publisher.

Requer `GOOGLE_FACTCHECK_API_KEY` no ambiente (definida pelo usuario).
Grava um registro canonico por linha (com `_provenance`) em `raw/gfc.jsonl`.

Uso:
    python -m investigation.expansion.collect_gfc --max-pages 50
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import schema as sch
from .sources import FEED_PUBLISHERS

API = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
RAW = Path("investigation/expansion/raw")
UA = "FakenewsBR-research/2.0"


def _get(params: dict, timeout: int = 30, retries: int = 5) -> dict:
    """GET com retry/backoff em 429/5xx (a API devolve 503 esporadico)."""
    import time

    import requests
    params = {**params, "key": os.environ["GOOGLE_FACTCHECK_API_KEY"]}
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(API, params=params, timeout=timeout,
                             headers={"User-Agent": UA})
        except requests.RequestException as e:
            last = e
            time.sleep(min(2 ** attempt, 20))
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504):
            last = f"HTTP {r.status_code}"
            time.sleep(min(2 ** attempt, 30))
            continue
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    raise RuntimeError(f"falhou apos {retries} tentativas: {last}")


def _records_from_claim(claim: dict) -> list[dict]:
    text = (claim.get("text") or "").strip()
    if not text:
        return []
    out = []
    for rev in claim.get("claimReview", []) or []:
        pub = (rev.get("publisher") or {})
        site = (pub.get("site") or "").lower().removeprefix("www.")
        rr = rev.get("reviewRating") or {}
        rating = (rev.get("textualRating")
                  or rr.get("textualRating")
                  or rr.get("ratingValue") or "")
        if not isinstance(rating, str):
            rating = str(rating)
        label = sch.label_of_rating(rating)
        if label is None:
            continue
        url = rev.get("url") or ""
        meta = FEED_PUBLISHERS.get(site) or FEED_PUBLISHERS.get(f"www.{site}")
        dataset = meta[0] if meta else "FC_GFC"
        publisher = meta[1] if meta else (pub.get("name") or site)
        lang = meta[2] if meta else "pt-BR"
        date = (rev.get("reviewDate") or "")[:10]
        rid = sch.make_rid(url or text, "claim", claim.get("text", "")[:80])
        r = sch.Record(
            rid=rid, dataset_name=dataset, source_type="news",
            source_description=publisher, label=label, date_iso=date or None,
            url_review=url, text=text, factcheck_rating=rating,
            factcheck_claimant=(claim.get("claimant") or ""),
            factcheck_url=url, label_source="rating", text_role="claim",
            publisher=publisher, lang_variant=lang, collector="gfc",
            source_url=url,
            collected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            mentions_ai=int(sch.mentions_ai(text)),
        )
        try:
            r.finalize()
        except ValueError:
            continue
        row = r.csv_row()
        row["_provenance"] = r.prov_row("gfc")
        out.append(row)
    return out


def collect(out: Path, sites: list[str], max_pages: int,
            max_age_days: int | None, page_size: int = 100,
            sleep_s: float = 0.5) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("a", encoding="utf-8") as f:
        for site in sites:
            token = None
            for _ in range(max_pages):
                params = {"reviewPublisherSiteFilter": site,
                          "languageCode": "pt", "pageSize": min(page_size, 100)}
                if max_age_days:
                    params["maxAgeDays"] = max_age_days
                if token:
                    params["pageToken"] = token
                try:
                    data = _get(params)
                except Exception as e:  # noqa: BLE001
                    print(f"[gfc] {site}: erro {e}")
                    break
                claims = data.get("claims", [])
                for c in claims:
                    for row in _records_from_claim(c):
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                        n += 1
                token = data.get("nextPageToken")
                print(f"[gfc] {site}: {len(claims)} claims, total {n}", flush=True)
                if not token:
                    break
                time.sleep(sleep_s)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=RAW / "gfc.jsonl")
    ap.add_argument("--site", action="append", default=None,
                    help="dominio; repetivel. Default: whitelist do feed.")
    ap.add_argument("--max-pages", type=int, default=50)
    ap.add_argument("--max-age-days", type=int, default=None)
    ap.add_argument("--sleep", dest="sleep_s", type=float, default=0.5)
    a = ap.parse_args()
    if "GOOGLE_FACTCHECK_API_KEY" not in os.environ:
        raise SystemExit("defina GOOGLE_FACTCHECK_API_KEY no ambiente")
    sites = a.site or sorted(FEED_PUBLISHERS.keys())
    n = collect(a.out, sites, a.max_pages, a.max_age_days,
                sleep_s=a.sleep_s)
    print(f"[gfc] {n} registros -> {a.out}")


if __name__ == "__main__":
    main()
