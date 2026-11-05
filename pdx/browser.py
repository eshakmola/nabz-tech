"""Browser layer — the only module that needs Playwright/Patchright."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from .parser import BASE_URL, CATEGORIES, DEFAULT_CATEGORY

CARD_SELECTOR = 'a[href*="/discover/"]'
API_VERSION = os.getenv("PDX_API_VERSION", "2.18")

#: خواندن همه‌ی مقاله‌ها با fetch درون‌صفحه‌ای (همان کوکی/توکن Turnstile)
JS_BATCH_FETCH = """
async ([slugs, version]) => {
  const out = {};
  for (const slug of slugs) {
    try {
      const r = await fetch('/rest/article/' + slug + '?version=' + version + '&source=default',
                            {headers: {'accept': 'application/json'}});
      out[slug] = r.ok ? await r.json() : {error: 'HTTP ' + r.status};
    } catch (e) {
      out[slug] = {error: String(e)};
    }
  }
  return out;
}
"""


def category_url(category: str) -> str:
    return BASE_URL + CATEGORIES.get(category, f"/discover/{category}")


# --------------------------------------------------------------------------- #
def fetch_api_payloads(
    category: str = DEFAULT_CATEGORY,
    limit: int | None = None,
    scroll: bool = True,
    max_scrolls: int = 10,
    log: Callable[[str], None] = print,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Open the Discover page once, then batch-fetch every article JSON.

    Returns ``(payloads_by_slug, ordered_slugs)``.
    """
    from scrapling.fetchers import StealthySession

    url = category_url(category)
    holder: dict[str, Any] = {}

    def page_action(page):  # runs inside the browser context
        page.wait_for_timeout(2500)
        if scroll:
            last = -1
            for _ in range(max_scrolls):
                count = page.locator(CARD_SELECTOR).count()
                if limit and count >= limit:
                    break
                if count == last:
                    break
                last = count
                page.mouse.wheel(0, 4000)
                page.wait_for_timeout(1200)

        hrefs = page.eval_on_selector_all(
            CARD_SELECTOR, "els => els.map(e => e.getAttribute('href'))"
        )
        reserved = set(CATEGORIES) | {"top"}
        slugs: list[str] = []
        for href in hrefs:
            if not href or "?" in href or "/discover/" not in href:
                continue
            slug = href.rstrip("/").split("/")[-1]
            if slug in reserved:  # لینک خود دسته‌ها، نه یک خبر
                continue
            if slug not in slugs:
                slugs.append(slug)
        if limit:
            slugs = slugs[:limit]
        holder["slugs"] = slugs
        log(f"  cards found: {len(slugs)}")
        holder["api"] = page.evaluate(JS_BATCH_FETCH, [slugs, API_VERSION])
        log(f"  article payloads: {len(holder['api'])}")

    log(f"→ opening {url} with stealth browser …")
    with StealthySession(headless=True, solve_cloudflare=True, timeout=180_000) as session:
        response = session.fetch(
            url, network_idle=True, wait=3000, page_action=page_action, timeout=120_000
        )
    log(f"  HTTP {response.status} · {len(response.html_content or ''):,} chars of HTML")

    payloads = holder.get("api", {}) or {}
    order = holder.get("slugs", []) or []
    return payloads, order


# --------------------------------------------------------------------------- #
def download_image(
    image_url: str | None,
    slug: str,
    directory: str = "output/images",
    timeout: int = 30,
) -> str | None:
    """Download a hero image with the cheap HTTP fetcher (no browser needed)."""
    if not image_url:
        return None
    os.makedirs(directory, exist_ok=True)
    ext = os.path.splitext(urlparse(image_url).path)[1] or ".jpg"
    if len(ext) > 5:
        ext = ".jpg"
    path = os.path.join(directory, slug[:48] + ext)
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    try:
        from scrapling.fetchers import Fetcher

        response = Fetcher.get(image_url, timeout=timeout)
        body = getattr(response, "body", None)
        if not body:
            return None
        with open(path, "wb") as fh:
            fh.write(body)
        return path if os.path.getsize(path) > 1000 else None
    except Exception as exc:
        print(f"    ! image failed for {slug[:32]}: {exc}")
        return None
