#!/usr/bin/env python3
"""Google News RSS scraper.

برای هر آیتم فید:
  • تیتر از تگ <title> خوانده می‌شود
  • لینک داخل تگ <link> (ریدایرکت گوگل) به آدرس واقعی ناشر باز می‌شود
  • تصویر شاخص و متن خبر از صفحه‌ی ناشر استخراج می‌شود
  • <description> گوگل (فهرست لینک‌های پوشش مرتبط) پارس و لینک‌هایش نیز باز می‌شود

Examples
--------
    python gnews_scraper.py                       # فید پیش‌فرض (Technology)
    python gnews_scraper.py --limit 5
    python gnews_scraper.py --feed "https://news.google.com/rss/search?q=AI&hl=en-US&gl=US&ceid=US:en"
    python gnews_scraper.py --no-text             # فقط لینک/تصویر/دیسکریپشن
    python gnews_scraper.py --site site           # + خروجی GitHub Pages
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone

from gnews import (
    collect_items,
    download_image_chain,
    extract_description,
    parse_feed,
    render_csv,
    render_html,
    render_json,
    render_markdown,
)

DEFAULT_FEED = (
    "https://news.google.com/rss/topics/"
    "CAAqKggKIiRDQkFTRlFvSUwyMHZNRGRqTVhZU0JXVnVMVlZUR2dKVlV5Z0FQAQ"
    "?hl=en-US&gl=US&ceid=US:en"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape a Google News RSS feed: resolve links, fetch image + text.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--feed", default=DEFAULT_FEED, help="RSS feed URL")
    parser.add_argument("--feed-file", default=None, help="read the RSS XML from a local file")
    parser.add_argument("--limit", type=int, default=10, help="max items (0 = all)")
    parser.add_argument("--out", default="output", help="output directory")
    parser.add_argument("--no-text", action="store_true", help="skip article body extraction")
    parser.add_argument("--no-images", action="store_true", help="skip hero images")
    parser.add_argument(
        "--describe-only",
        action="store_true",
        help="do not open publisher pages (google description only)",
    )
    parser.add_argument(
        "--dynamic", action="store_true", help="use a stealth browser when a page yields no text"
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=4,
        help="pages to try per item (1 = primary only)",
    )
    parser.add_argument("--delay", type=float, default=0.3, help="seconds between requests")
    parser.add_argument("--min-items", type=int, default=1, help="CI guard")
    parser.add_argument(
        "--site",
        default=None,
        metavar="DOCS_DIR",
        help="write <DOCS_DIR>/index.html + archive copy for GitHub Pages",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def load_feed(args) -> str:
    if args.feed_file:
        with open(args.feed_file, encoding="utf-8") as fh:
            return fh.read()
    from scrapling.fetchers import Fetcher

    response = Fetcher.get(args.feed, timeout=30)
    if response.status != 200 or not response.body:
        raise SystemExit(f"::error::feed fetch failed (HTTP {response.status})")
    return response.body.decode("utf-8", "ignore")


def write_all(items, feed, out_dir, with_text, scraped_at, site=None) -> None:
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, "gnews")

    with open(base + ".json", "w", encoding="utf-8") as fh:
        fh.write(render_json(items, feed, scraped_at))
    with open(base + ".csv", "w", encoding="utf-8", newline="") as fh:
        fh.write(render_csv(items))
    with open(base + ".md", "w", encoding="utf-8") as fh:
        fh.write(render_markdown(items, feed, scraped_at, with_text=with_text))
    html = render_html(items, feed, scraped_at, with_text=with_text)
    with open(base + ".html", "w", encoding="utf-8") as fh:
        fh.write(html)

    if site:
        os.makedirs(os.path.join(site, "archive"), exist_ok=True)
        with open(os.path.join(site, "index.html"), "w", encoding="utf-8") as fh:
            fh.write(html)
        token = (scraped_at or datetime.now(timezone.utc).isoformat())[:16].replace(":", "")
        with open(
            os.path.join(site, "archive", f"gnews-{token}.html"), "w", encoding="utf-8"
        ) as fh:
            fh.write(html)
        open(os.path.join(site, ".nojekyll"), "a").close()
        print(f"  site: {site}/index.html (+ archive/gnews-{token}.html)")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log = (lambda *_: None) if args.quiet else print
    started = time.time()

    log("→ reading feed …")
    xml_text = load_feed(args)
    feed, items = parse_feed(xml_text)
    log(
        f"  {feed.get('title') or 'feed'} · {len(items)} items · last build {feed.get('last_build')}"
    )

    if args.describe_only:
        for item in items:
            plain, related = extract_description(item.pop("google_description_html", ""))
            item["description"] = plain or None
            item["related_links"] = related
            item["url"] = item["google_url"]
            item["resolved_url"] = None
            item["image_url"] = None
            item["image_file"] = None
            item["text"] = ""
            item["text_chars"] = 0
            item["publisher"] = related[0]["publisher"] if related else None
        rows = items[: args.limit] if args.limit else items
        for position, item in enumerate(rows, start=1):
            item["position"] = position
    else:
        limit = args.limit or None
        log(f"→ resolving links + fetching pages (limit={limit or 'all'}) …")
        rows = collect_items(
            items,
            with_text=not args.no_text,
            with_image=not args.no_images,
            dynamic=args.dynamic,
            delay=args.delay,
            limit=limit,
            max_candidates=args.max_candidates,
            log=log,
        )

        if not args.no_images:
            log("→ downloading hero images (with fallback candidates) …")
            for item in rows:
                candidates = [item.get("image_url"), *(item.get("image_candidates") or [])]
                path, used = download_image_chain(
                    candidates,
                    item.get("article_id") or item["google_url"][-24:],
                    directory=os.path.join(args.out, "gnews-images"),
                )
                item["image_file"] = path
                if used and used != item.get("image_url"):
                    item["image_url"] = used
                    item["image_source"] = used
            got = sum(1 for it in rows if it.get("image_file"))
            log(f"  images: {got}/{len(rows)}")

    scraped_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_all(rows, feed, args.out, not args.no_text, scraped_at, site=args.site)
    log(f"✅ {len(rows)} items → {args.out}/ ({time.time() - started:.0f}s)")

    if len(rows) < args.min_items:
        print(f"::error::only {len(rows)} items (min {args.min_items})")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
