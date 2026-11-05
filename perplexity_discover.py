#!/usr/bin/env python3
"""اسکرپر سبک صفحه‌ی اصلی Discover (فقط تیتر/خلاصه/سن/تعداد منابع).

این اسکریپت مستقل و آموزشی است؛ برای نسخه‌ی کامل (تصویر + Summary + Report)
از ``perplexity_tech_scraper.py`` استفاده کنید.

    python perplexity_discover.py 15
"""

from __future__ import annotations

import csv
import json
import sys

from scrapling.fetchers import StealthyFetcher

URL = "https://www.perplexity.ai/discover"
CARD_LINK = 'a[href*="/discover/"]'


def fetch_page(max_cards: int = 15, headless: bool = True):
    """صفحه را با مرورگر مخفی باز می‌کند و در صورت نیاز اسکرول می‌کند."""

    def scroll(page):
        last = 0
        for _ in range(max_cards):
            count = len(page.locator(CARD_LINK).all())
            if count >= max_cards or count == last:
                break
            last = count
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(1200)
        page.wait_for_timeout(800)

    return StealthyFetcher.fetch(
        URL,
        headless=headless,
        network_idle=True,
        timeout=120_000,
        wait=2500,
        page_action=scroll,
        solve_cloudflare=True,
    )


def parse_cards(page) -> list[dict]:
    """کارت‌های خبری را از DOM رندرشده بیرون می‌کشد."""
    items, seen = [], set()
    for card in page.css(CARD_LINK):
        link = card.attrib.get("href")
        if not link or link in seen:
            continue
        seen.add(link)

        title = card.css('[data-testid="thread-title"] *::text').get()
        # نکته: زمان و تعداد منابع داخل <span> هستند → *::text لازم است
        meta = [
            t.strip()
            for t in card.css(
                'div[class*="font-sans text-xs font-medium text-secondary"] *::text'
            ).getall()
            if t and t.strip()
        ]
        sources = next((m for m in meta if "source" in m), None)

        items.append(
            {
                "title": title,
                "url": "https://www.perplexity.ai" + link,
                "slug": link.rsplit("/", 1)[-1],
                "age": next((m for m in meta if m.endswith("ago")), None),
                "sources": sources,
                "summary": card.css('div[class*="line-clamp-6"] *::text').get(),
                "image": card.css("img::attr(src)").get(),
            }
        )
    return items


def save(items: list[dict]) -> None:
    with open("perplexity_discover.json", "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=2)
    if items:
        with open("perplexity_discover.csv", "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(items[0]))
            writer.writeheader()
            writer.writerows(items)


def main() -> None:
    max_cards = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    print(f"→ واکشی {URL} با مرورگر مخفی …")
    page = fetch_page(max_cards)
    print(f"  HTTP {page.status} · {len(page.html_content):,} کاراکتر HTML")

    items = parse_cards(page)
    print(f"  خبر: {len(items)}")
    for item in items[:5]:
        print(f"   • {item['title']} ({item['age'] or '?'} · {item['sources'] or '?'})")

    save(items)
    print("\nذخیره شد: perplexity_discover.json / .csv")


if __name__ == "__main__":
    main()
