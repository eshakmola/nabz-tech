"""
Scrapling 0.5 - نمونه‌ی سریع (Quickstart demo)
اجرا:  python3 scrapling_demo.py
"""

import json

from scrapling.fetchers import Fetcher, StealthyFetcher

URL = "https://quotes.toscrape.com"


def demo_http():
    """۱) درخواست سریع HTTP با استتار TLS (curl_cffi) + پارس با CSS/XPath"""
    print("\n=== 1) Fetcher (سریع، بدون مرورگر) ===")
    page = Fetcher.get(URL, timeout=30)
    print("status:", page.status)

    rows = []
    for quote in page.css(".quote"):
        rows.append(
            {
                "text": quote.css(".text::text").get(),
                "author": quote.css(".author::text").get(),
                "tags": quote.css(".tag::text").getall(),
            }
        )
    for r in rows[:3]:
        print(f"  - {r['author']}: {r['text'][:60]}...  tags={r['tags']}")

    with open("quotes.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"  → {len(rows)} آیتم در quotes.json ذخیره شد")

    # مارک‌داون آماده برای RAG / LLM
    md = page.markdown()  # متن صفحه به‌صورت Markdown
    print("  markdown length:", len(md or ""))


def demo_stealth():
    """۲) مرورگر مخفی (Camoufox/patchright) برای سایت‌های سخت و Cloudflare"""
    print("\n=== 2) StealthyFetcher (مرورگر مخفی) ===")
    page = StealthyFetcher.fetch(
        "https://example.com",
        headless=True,
        network_idle=True,
        timeout=60000,
    )
    print("status:", page.status, "| title:", page.css("title::text").get())


if __name__ == "__main__":
    demo_http()
    demo_stealth()
    print("\nهمه چیز درست کار می‌کند ✅")
