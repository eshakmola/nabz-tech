#!/usr/bin/env python3
"""Perplexity Discover scraper — command line entry point.

Examples
--------
    python perplexity_tech_scraper.py                      # tech, all cards
    python perplexity_tech_scraper.py --limit 5 --no-images
    python perplexity_tech_scraper.py --category finance --out output/finance
    python perplexity_tech_scraper.py --site docs           # for GitHub Pages
    python perplexity_tech_scraper.py --from-json out/perplexity_tech.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

from pdx import (
    DEFAULT_CATEGORY,
    collect_items,
    render_csv,
    render_html,
    render_json,
    render_markdown,
)
from pdx.browser import category_url, download_image, fetch_api_payloads
from pdx.parser import CATEGORIES


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Perplexity Discover (image + summary + full report).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--category", default=DEFAULT_CATEGORY, choices=sorted(CATEGORIES), help="Discover category"
    )
    parser.add_argument("--limit", type=int, default=None, help="max articles (default: all)")
    parser.add_argument("--out", default="output", help="output directory")
    parser.add_argument("--no-images", action="store_true", help="skip hero images")
    parser.add_argument("--no-scroll", action="store_true", help="do not scroll the page")
    parser.add_argument(
        "--min-items",
        type=int,
        default=1,
        help="exit code 1 if fewer items were scraped (CI guard)",
    )
    parser.add_argument(
        "--max-age-hours", type=float, default=None, help="drop articles older than N hours"
    )
    parser.add_argument(
        "--site",
        default=None,
        metavar="DOCS_DIR",
        help="also write <DOCS_DIR>/index.html (+ archive copy) for GitHub Pages",
    )
    parser.add_argument(
        "--from-json",
        default=None,
        help="re-render outputs from a previously saved JSON file (no scraping)",
    )
    parser.add_argument("--quiet", action="store_true", help="less logging")
    return parser.parse_args(argv)


# --------------------------------------------------------------------------- #
def _rehydrate(path: str, out_dir: str, site: str | None = None) -> int:
    """Re-render every format from a saved JSON payload (no network)."""
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    items = payload.get("items") or []
    stamp = payload.get("scraped_at_utc")
    category = items[0].get("category", DEFAULT_CATEGORY) if items else DEFAULT_CATEGORY
    source = payload.get("source", category_url(category))
    _write_all(items, out_dir, category, source, stamp, site=site)
    print(f"✅ re-rendered {len(items)} items from {path}")
    return 0


def _write_all(items, out_dir, category, source, stamp, site=None) -> None:
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, f"perplexity_{category}")

    with open(base + ".json", "w", encoding="utf-8") as fh:
        fh.write(render_json(items, source=source, scraped_at=stamp))
    with open(base + ".csv", "w", encoding="utf-8", newline="") as fh:
        fh.write(render_csv(items))
    with open(base + ".md", "w", encoding="utf-8") as fh:
        fh.write(render_markdown(items, category=category, scraped_at=stamp, source=source))
    html = render_html(items, category=category, scraped_at=stamp)
    with open(base + ".html", "w", encoding="utf-8") as fh:
        fh.write(html)

    if site:
        os.makedirs(os.path.join(site, "archive"), exist_ok=True)
        with open(os.path.join(site, "index.html"), "w", encoding="utf-8") as fh:
            fh.write(html)
        token = (stamp or datetime.now(timezone.utc).isoformat())[:16].replace(":", "")
        archive = os.path.join(site, "archive", f"{category}-{token}.html")
        with open(archive, "w", encoding="utf-8") as fh:
            fh.write(html)
        open(os.path.join(site, ".nojekyll"), "a").close()
        print(f"  site: {site}/index.html (+ archive/{os.path.basename(archive)})")


def _filter_age(items: list[dict], max_age_hours: float | None) -> list[dict]:
    if not max_age_hours:
        return items
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_hours * 3600
    kept = []
    for item in items:
        iso = item.get("published_iso")
        if not iso:
            kept.append(item)
            continue
        try:
            ts = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
        except ValueError:
            kept.append(item)
            continue
        if ts >= cutoff:
            kept.append(item)
    for new_pos, item in enumerate(kept, 1):
        item["position"] = new_pos
    print(f"  age filter: kept {len(kept)}/{len(items)} (<= {max_age_hours}h)")
    return kept


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log = (lambda *_: None) if args.quiet else print

    if args.from_json:
        return _rehydrate(args.from_json, args.out, site=args.site)

    started = time.time()
    payloads, order = fetch_api_payloads(
        category=args.category,
        limit=args.limit,
        scroll=not args.no_scroll,
        log=log,
    )
    items = collect_items(payloads, order=order, category=args.category)
    log(f"  parsed articles: {len(items)} ({time.time() - started:.0f}s)")

    items = _filter_age(items, args.max_age_hours)

    if not args.no_images:
        log("→ downloading hero images …")
        for item in items:
            item["image_file"] = download_image(
                item.get("image_url"), item["slug"], directory=os.path.join(args.out, "images")
            )
        got = sum(1 for item in items if item.get("image_file"))
        log(f"  images: {got}/{len(items)}")

    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write_all(items, args.out, args.category, category_url(args.category), stamp, site=args.site)
    log(f"✅ {len(items)} articles → {args.out}/ ({time.time() - started:.0f}s total)")

    if len(items) < args.min_items:
        print(f"::error::only {len(items)} articles scraped (min {args.min_items})")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
