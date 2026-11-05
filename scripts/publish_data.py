#!/usr/bin/env python3
"""Publish the two sources as a combined, date-sorted JSON feed for the Cloudflare Worker.

Outputs (all separate per source + one combined view for the API):

    data/perplexity_tech.json   ← فقط پروکسپلکسیتی
    data/gnews.json             ← فقط گوگل‌نیوز
    data/hub.json               ← نمای ترکیبی (مرتب بر اساس تاریخ) که ورکر می‌خواند

اختیاری: با ``--kv`` همین داده‌ها در Cloudflare KV نوشته می‌شوند
(نیازمند ``CLOUDFLARE_API_TOKEN`` و ``CLOUDFLARE_ACCOUNT_ID`` و ``--namespace``).

    python scripts/publish_data.py --dir output
    python scripts/publish_data.py --dir output --kv --namespace <KV_ID>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

CF_API = "https://api.cloudflare.com/client/v4"


# --------------------------------------------------------------------------- #
def _load(path: str | None) -> dict[str, Any]:
    if not path or not os.path.exists(path):
        return {"items": []}
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    return doc if isinstance(doc, dict) else {"items": doc}


def perplexity_items(doc: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for it in doc.get("items") or []:
        category = it.get("category") or doc.get("category") or "tech"
        out.append(
            {
                "source": "perplexity",
                "source_label": "Perplexity",
                "title": (it.get("title") or "").strip(),
                "url": it.get("url") or "",
                "publisher": f"Perplexity · {category}",
                "ts": it.get("published_iso") or None,
                "summary": it.get("summary") or "",
                "bullets": it.get("bullet_summary") or "",
                "sections": it.get("report_sections") or [],
                "text": "",
                "sources_count": it.get("sources_count") or 0,
                "sources": [
                    {"domain": s.get("domain") or "", "url": s.get("url") or ""}
                    for s in (it.get("sources") or [])
                ],
                "image": None,
                "read_time": it.get("read_time_min"),
                "lang": "en",
            }
        )
    return out


def gnews_items(doc: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for it in doc.get("items") or []:
        related = it.get("related_links") or []
        out.append(
            {
                "source": "gnews",
                "source_label": "G News",
                "title": (it.get("title") or "").strip(),
                "url": it.get("resolved_url") or it.get("url") or "",
                "publisher": it.get("publisher") or "",
                "ts": it.get("published_iso") or None,
                "summary": it.get("description") or "",
                "bullets": "",
                "sections": [],
                "text": (it.get("text") or "")[:1500],
                "sources_count": len(related),
                "sources": [
                    {
                        "domain": link.get("publisher") or "",
                        "url": link.get("resolved_url") or link.get("url") or "",
                    }
                    for link in related[:8]
                ],
                "image": None,
                "read_time": None,
                "lang": "en",
            }
        )
    return out


def combine(perplexity: list[dict], gnews: list[dict]) -> list[dict]:
    merged = [*perplexity, *gnews]
    merged.sort(key=lambda e: e.get("ts") or "", reverse=True)
    for index, entry in enumerate(merged, start=1):
        entry["order"] = index
    return merged


# --------------------------------------------------------------------------- #
def _cf_request(method: str, url: str, token: str, payload: Any = None) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:  # pragma: no cover - network path
        return json.loads(exc.read().decode() or "{}")


def push_kv(account: str, namespace: str, token: str, values: dict[str, Any]) -> list[str]:
    pushed = []
    for key, value in values.items():
        body = json.dumps(value, ensure_ascii=False)
        result = _cf_request(
            "PUT",
            f"{CF_API}/accounts/{account}/storage/kv/namespaces/{namespace}/values/{key}",
            token,
            body,
        )
        if result.get("success"):
            pushed.append(key)
        else:
            print(f"  ! KV {key}: {result.get('errors')}", file=sys.stderr)
    return pushed


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish combined JSON for Cloudflare Workers")
    parser.add_argument("--dir", default="output", help="پوشه‌ای که اسکرپرها در آن نوشته‌اند")
    parser.add_argument("--perplexity", help="مسیر perplexity_tech.json")
    parser.add_argument("--gnews", help="مسیر gnews.json")
    parser.add_argument("--out", default="data", help="پوشه‌ی خروجی (پیش‌فرض data)")
    parser.add_argument("--kv", action="store_true", help="نوشتن در Cloudflare KV")
    parser.add_argument("--namespace", default=os.environ.get("CF_KV_NAMESPACE", ""))
    parser.add_argument("--account", default=os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""))
    args = parser.parse_args(argv)

    pj = args.perplexity or os.path.join(args.dir, "perplexity_tech.json")
    gj = args.gnews or os.path.join(args.dir, "gnews.json")

    perplexity = perplexity_items(_load(pj))
    gnews = gnews_items(_load(gj))
    merged = combine(perplexity, gnews)

    os.makedirs(args.out, exist_ok=True)
    targets = {
        "perplexity_tech.json": perplexity,
        "gnews.json": gnews,
        "hub.json": merged,
    }
    for name, payload in targets.items():
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)

    print(
        f"✅ data → {args.out}/ · {len(merged)} خبر "
        f"(Perplexity {len(perplexity)} · G News {len(gnews)}) · "
        f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}"
    )

    if args.kv:
        token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
        if not (token and args.account and args.namespace):
            print(
                "! --kv نیازمند CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID + --namespace",
                file=sys.stderr,
            )
            return 2
        pushed = push_kv(
            args.account,
            args.namespace,
            token,
            {
                "hub:perplexity": perplexity,
                "hub:gnews": gnews,
                "hub:all": merged,
            },
        )
        print(f"✅ KV updated: {', '.join(pushed) or '—'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
