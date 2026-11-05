"""Parsing layer — pure functions, no network, no browser.

Everything in this module can be unit-tested against a saved JSON fixture.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

BASE_URL = "https://www.perplexity.ai"
DEFAULT_CATEGORY = "tech"

#: نگاشت دسته‌ها به مسیر Discover
CATEGORIES = {
    "top": "/discover",
    "tech": "/discover/tech",
    "finance": "/discover/finance",
    "sports": "/discover/sports",
    "arts": "/discover/arts",
    "health": "/discover/health",
}

_ENTITY_CHIP = re.compile(r"\[([^\]]+)\]\(pplx://[^)]*\)")
_CITATION = re.compile(r"\[(\d{1,2})\]")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def clean_markdown(text: str | None) -> str:
    """Remove Perplexity-internal artefacts from markdown text.

    * ``[Amazon](pplx://entity_chip/abc)`` -> ``Amazon``
    * inline citation markers ``[1]``      -> ````
    """
    if not text:
        return ""
    text = _ENTITY_CHIP.sub(r"\1", text)
    text = _CITATION.sub("", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def domain_of(url: str | None) -> str:
    if not url:
        return ""
    try:
        return urlparse(url).netloc.replace("www.", "")
    except ValueError:
        return ""


def _as_utc(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:  # API sometimes returns naive timestamps
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def humanize_age(iso: str | None, now: datetime | None = None) -> str | None:
    """``2026-11-04T10:00:00`` -> ``'2 hours ago'`` (English, like the site)."""
    dt = _as_utc(iso)
    if dt is None:
        return None
    now = now or datetime.now(timezone.utc)
    minutes = max(int((now - dt).total_seconds() // 60), 0)

    def unit(n: int, word: str) -> str:
        return f"{n} {word}{'' if n == 1 else 's'} ago"

    if minutes < 1:
        return "just now"
    if minutes < 60:
        return unit(minutes, "minute")
    if minutes < 1440:
        return unit(minutes // 60, "hour")
    if minutes < 43200:
        return unit(minutes // 1440, "day")
    return unit(minutes // 43200, "month")


# --------------------------------------------------------------------------- #
# article payload -> flat dict
# --------------------------------------------------------------------------- #
def parse_article(payload: dict[str, Any]) -> dict[str, Any]:
    """Turn one ``/rest/article/<slug>`` response into a flat, render-ready dict.

    ``payload`` is the JSON body of
    ``GET /rest/article/<slug>?version=2.18&source=default``.
    """
    entries: Iterable[dict] = payload.get("entries") or []
    entries = list(entries)
    if not entries:
        raise ValueError("payload has no entries")

    main = entries[0]
    info = main.get("article_info") or {}

    sections: list[dict[str, str]] = []
    sources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for entry in entries:
        raw = entry.get("text")
        try:
            body_payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except json.JSONDecodeError:
            continue

        body = clean_markdown(body_payload.get("answer"))
        if body:
            sections.append(
                {
                    "heading": (entry.get("query_str") or "").strip(),
                    "body": body,
                }
            )

        for wr in body_payload.get("web_results") or []:
            url = wr.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            sources.append(
                {
                    "name": wr.get("name"),
                    "domain": domain_of(url),
                    "url": url,
                    "date": (wr.get("meta_data") or {}).get("date"),
                }
            )

    images = main.get("featured_images") or []
    image_url = None
    image_credit = None
    if images:
        image_url = (images[0] or {}).get("image")
        image_credit = (images[0] or {}).get("author_url")

    return {
        "title": info.get("title") or main.get("thread_title"),
        "summary": clean_markdown(info.get("summary")) or None,
        "bullet_summary": clean_markdown(info.get("bullet_summary")) or None,
        "report_sections": sections,
        "report_chars": sum(len(s["body"]) for s in sections),
        "read_time_min": info.get("read_time"),
        "query": main.get("query_str"),
        "published_iso": main.get("updated_datetime"),
        "image_url": image_url,
        "image_credit": image_credit,
        "sources_count": len(sources),
        "sources": sources,
    }


def build_item(
    slug: str,
    payload: dict[str, Any],
    position: int = 1,
    category: str = DEFAULT_CATEGORY,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Merge article payload + card metadata into one flat record."""
    parsed = parse_article(payload)
    path = CATEGORIES.get(category, f"/discover/{category}")
    parsed.update(
        {
            "position": position,
            "slug": slug,
            "category": category,
            "url": f"{BASE_URL}{path}/{slug}",
            "published": humanize_age(parsed["published_iso"], now=now),
            "image_file": None,
        }
    )
    return parsed


def collect_items(
    api_payloads: dict[str, dict[str, Any]],
    order: Iterable[str] | None = None,
    category: str = DEFAULT_CATEGORY,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Build every item that does not carry an ``error`` key, preserving order."""
    slugs = list(order) if order is not None else list(api_payloads)
    items: list[dict[str, Any]] = []
    for slug in slugs:
        payload = api_payloads.get(slug) or {}
        if not payload or "error" in payload or not payload.get("entries"):
            continue
        items.append(
            build_item(
                slug,
                payload,
                position=len(items) + 1,
                category=category,
                now=now,
            )
        )
    return items
