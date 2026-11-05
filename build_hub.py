#!/usr/bin/env python3
"""ساخت صفحه‌ی وب واحد از دو منبع مستقل (Perplexity + Google News).

داده‌ها و خروجی‌های هر منبع **کاملاً جدا** می‌مانند:
    output/perplexity_tech.json / .csv   +  output/images/…
    output/gnews.json / .csv             +  output/gnews-images/…

تنها چیزی که ترکیب می‌شود، نمای HTML هاب است (با سوییچر سه‌تایی و مرتب بر اساس تاریخ).

Examples
--------
    # فقط هاب را از داده‌های موجود بساز
    python build_hub.py

    # اول هر دو منبع را اسکرپ کن، بعد هاب را بساز
    python build_hub.py --refresh

    # مسیرهای دلخواه
    python build_hub.py --perplexity output/perplexity_tech.json \
                        --gnews output/gnews.json --out site/index.html
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone

from pdx.hub import build_hub


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the combined hub page from the two independent scrapers.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--no-archive", action="store_true", help="نسخه‌ی آرشیوی نساز")
    parser.add_argument("--out", default="site/index.html", help="hub HTML path")
    parser.add_argument("--dir", default="output", help="output dir used with --refresh")
    parser.add_argument(
        "--perplexity",
        default=None,
        help="path to perplexity JSON (default: <dir>/perplexity_tech.json)",
    )
    parser.add_argument(
        "--gnews", default=None, help="path to gnews JSON (default: <dir>/gnews.json)"
    )
    parser.add_argument(
        "--inline-limit",
        type=int,
        default=140,
        help="how many images per source get base64-inlined",
    )
    parser.add_argument("--refresh", action="store_true", help="run both scrapers first")
    parser.add_argument("--limit", type=int, default=10, help="items per source with --refresh")
    parser.add_argument("--no-images", action="store_true", help="with --refresh: skip images")
    parser.add_argument("--dynamic", action="store_true", help="with --refresh: browser fallback")
    parser.add_argument("--title", default=None, help="hub page title")
    return parser.parse_args(argv)


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"::warning::command failed ({result.returncode}): {' '.join(cmd)}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.refresh:
        common = ["--out", args.dir, "--limit", str(args.limit), "--site", ""]
        common = [part for part in common if part]
        perplexity_cmd = [
            sys.executable,
            "perplexity_tech_scraper.py",
            "--out",
            args.dir,
            "--limit",
            str(args.limit),
        ]
        gnews_cmd = [
            sys.executable,
            "gnews_scraper.py",
            "--out",
            args.dir,
            "--limit",
            str(args.limit),
            "--max-candidates",
            "4",
        ]
        if args.no_images:
            perplexity_cmd.append("--no-images")
            gnews_cmd.append("--no-images")
        if args.dynamic:
            gnews_cmd.append("--dynamic")
        run(perplexity_cmd)
        run(gnews_cmd)

    perplexity_json = args.perplexity or os.path.join(args.dir, "perplexity_tech.json")
    gnews_json = args.gnews or os.path.join(args.dir, "gnews.json")

    for path in (perplexity_json, gnews_json):
        if not os.path.exists(path):
            print(f"::warning::missing {path} — بخش مربوطه در هاب خالی می‌ماند")

    info = build_hub(
        perplexity_json if os.path.exists(perplexity_json) else None,
        gnews_json if os.path.exists(gnews_json) else None,
        args.out,
        inline_limit=args.inline_limit,
        title=args.title,
    )

    # کپی آرشیو تاریخ‌دار + .nojekyll برای GitHub Pages
    site_dir = os.path.dirname(args.out) or "."
    if os.path.isdir(site_dir) and not args.no_archive:
        token = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
        archive_dir = os.path.join(site_dir, "archive")
        os.makedirs(archive_dir, exist_ok=True)
        with open(args.out, encoding="utf-8") as fh:
            html = fh.read()
        with open(os.path.join(archive_dir, f"hub-{token}.html"), "w", encoding="utf-8") as fh:
            fh.write(html)
    if os.path.isdir(site_dir):
        open(os.path.join(site_dir, ".nojekyll"), "a").close()

    print(
        f"✅ hub → {info['path']} · {info['count']} خبر "
        f"(Perplexity {info['perplexity']} · G News {info['gnews']})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
