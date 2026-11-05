"""Google News → per-item enrichment and rendering.

نسخه‌ی ۱.۲ (بازگردانده‌شده):
  * یک تصویر شاخص برای هر خبر
  * زنجیره‌ی fallback: لینک اصلی، بعد تا ``MAX_CANDIDATES`` لینک داخل description
  * چیدمان HTML: تصویر بزرگ + DESCRIPTION + ARTICLE TEXT + لیست لینک‌های مرتبط
"""

from __future__ import annotations

import base64
import csv
import io
import json
import os
from datetime import datetime, timezone
from typing import Any

from pdx.render import _CSS, _esc

from .feed import (
    LinkResolver,
    candidate_pages,
    extract_description,
    fetch_article,
    google_article_id,
)

MIN_TEXT_CHARS = 200  # کمتر از این یعنی «متن کامل خبر نداریم»
MAX_CANDIDATES = 4  # لینک اصلی + حداکثر ۳ لینک از description (پیش‌فرض v1.2)

CSV_COLUMNS = [
    "position",
    "title",
    "publisher",
    "published_iso",
    "image",
    "description",
    "url",
    "image_source",
    "text_chars",
    "text_source",
    "google_url",
    "related_links",
]


# --------------------------------------------------------------------------- #
# enrichment
# --------------------------------------------------------------------------- #
def enrich_item(
    item: dict[str, Any],
    resolver: LinkResolver,
    with_text: bool = True,
    with_image: bool = True,
    dynamic: bool = False,
    max_candidates: int = MAX_CANDIDATES,
    log=print,
) -> dict[str, Any]:
    """Resolve the real URL and pull image/text/description for one RSS item.

    زنجیره‌ی تلاش (به‌ترتیب):
      1. لینک اصلی (تگ ``<link>`` که به ناشر باز شده)
      2. اگر متن کامل نداشت یا تصویر نداشت → لینک‌های داخل ``<description>``
         یکی‌یکی امتحان می‌شوند تا هم متن کامل و هم تصویر پیدا شود.
    """
    plain, related = extract_description(item.pop("google_description_html", ""))

    # ۱) باز کردن لینک اصلی
    real_url = resolver.resolve(item["google_url"])

    # ۲) باز کردن لینک‌های «پوشش مرتبط» داخل description
    for link in related:
        if link.get("url"):
            link["resolved_url"] = resolver.resolve(link["url"]) or None

    chain = candidate_pages(real_url, related, max_candidates=max_candidates)

    need_text = with_text
    need_image = with_image
    primary_article: dict[str, Any] | None = None  # نتیجه‌ی لینک اصلی (برای متادیتا)
    chosen: dict[str, Any] | None = None
    text_article: dict[str, Any] | None = None
    best_partial: tuple[int, dict[str, Any], dict[str, Any]] | None = None
    image_url: str | None = None
    image_source: str | None = None
    tried: list[dict[str, Any]] = []

    for step in chain:
        url = step["url"]
        if not need_text and not need_image:
            break
        log(f"    · trying [{step['origin']}] {url[:70]}")
        article = fetch_article(url, dynamic=dynamic)
        if step["origin"] == "primary" or (
            primary_article is None and article.get("status") == 200
        ):
            primary_article = article

        status = article.get("status")
        chars = len(article.get("text") or "")
        found_image = article.get("image")
        tried.append(
            {
                "url": url,
                "origin": step["origin"],
                "status": status,
                "text_chars": chars,
                "image": bool(found_image),
            }
        )

        if need_image and found_image:
            image_url = found_image
            image_source = url
            need_image = False
            log(f"      + image ← {step['origin']}")

        if chars and (best_partial is None or chars > best_partial[0]):
            best_partial = (chars, article, step)

        if need_text and chars >= MIN_TEXT_CHARS:
            text_article = article
            chosen = step
            need_text = False
            log(f"      + text ({chars} chars) ← {step['origin']}")

    # اگر هیچ صفحه‌ای متن کامل نداد، بهترین متن جزئی را نگه دار
    if text_article is None and best_partial is not None:
        _, text_article, chosen = best_partial
        log(f"      ! only partial text ({best_partial[0]} chars) from {chosen['url'][:60]}")

    # متادیتای ناشر/دیسکریپشن: اول از صفحه‌ای که متن کامل داد، بعد اولین صفحه‌ی موفق
    source_article = text_article or primary_article or {}

    publisher = (
        source_article.get("site_name") or (related[0]["publisher"] if related else None) or None
    )

    item.update(
        {
            "resolved_url": real_url,
            "url": (chosen or {}).get("url") or real_url or item["google_url"],
            "publisher": publisher,
            "article_id": google_article_id(item["google_url"]),
            "description": source_article.get("description") or plain or None,
            "description_plain": plain or None,
            "related_links": related,
            "image_url": image_url if with_image else None,
            "image_source": image_source,
            "image_candidates": (source_article.get("images") or [])[:6],
            "image_file": None,
            "text": (source_article.get("text") or "") if with_text else "",
            "text_chars": len(source_article.get("text") or "") if with_text else 0,
            "text_source": (chosen or {}).get("url"),
            "text_from_related": bool(chosen and chosen.get("origin") == "related"),
            "published_source": source_article.get("published"),
            "author": source_article.get("author"),
            "fetch_status": source_article.get("status"),
            "tried": tried,
            "dynamic": bool(source_article.get("dynamic")),
        }
    )
    return item


def collect_items(
    items: list[dict[str, Any]],
    with_text: bool = True,
    with_image: bool = True,
    dynamic: bool = False,
    delay: float = 0.0,
    limit: int | None = None,
    max_candidates: int = MAX_CANDIDATES,
    log=print,
) -> list[dict[str, Any]]:
    resolver = LinkResolver(delay=delay, log=log)
    todo = items[:limit] if limit else items
    out: list[dict[str, Any]] = []
    for item in todo:
        log(f"  [{item['position']:2d}] {item['title'][:70] if item['title'] else '—'}")
        enriched = enrich_item(
            item,
            resolver,
            with_text=with_text,
            with_image=with_image,
            dynamic=dynamic,
            max_candidates=max_candidates,
            log=log,
        )
        chars = enriched.get("text_chars") or 0
        state = "ok" if chars >= MIN_TEXT_CHARS else ("partial" if chars else "desc-only")
        origin = "related" if enriched.get("text_from_related") else "primary"
        log(
            f"      → {state} · {chars} chars ({origin}) · "
            f"img: {'yes' if enriched.get('image_url') else 'no'} · "
            f"tries: {len(enriched.get('tried') or [])}"
        )
        out.append(enriched)
    for position, item in enumerate(out, start=1):
        item["position"] = position
    return out


# --------------------------------------------------------------------------- #
# image download
# --------------------------------------------------------------------------- #
def download_image(
    image_url: str | None, item_id: str, directory: str = "output/images"
) -> str | None:
    """دانلود تصویر شاخص؛ اگر آدرس اول شکست خورد بقیه‌ی کاندیدها امتحان می‌شوند."""
    return download_image_chain([image_url] if image_url else [], item_id, directory)[0]


def download_image_chain(
    urls: list[str | None], item_id: str, directory: str = "output/images"
) -> tuple[str | None, str | None]:
    """امتحان کردن چند آدرس تصویر به‌ترتیب.

    returns ``(local_path, used_url)`` — اگر همه شکست بخورند ``(None, None)``.
    """
    candidates = [u for u in dict.fromkeys(urls) if u]
    if not candidates:
        return None, None
    os.makedirs(directory, exist_ok=True)

    from scrapling.fetchers import Fetcher

    for url in candidates:
        lowered = url.lower().split("?")[0]
        ext = next(
            (cand for cand in (".png", ".webp", ".jpeg", ".jpg", ".gif") if lowered.endswith(cand)),
            ".jpg",
        )
        slug = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in (item_id or "item"))
        path = os.path.join(directory, slug[:60] + ext)
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            return path, url
        try:
            response = Fetcher.get(url, timeout=25)
            body = getattr(response, "body", None)
            if not body or len(body) < 1000:
                continue
            with open(path, "wb") as fh:
                fh.write(body)
            return path, url
        except Exception as exc:
            print(f"    ! image candidate failed ({url[:60]}): {exc}")
            continue
    return None, None


# --------------------------------------------------------------------------- #
# render
# --------------------------------------------------------------------------- #
def render_json(items: list[dict], feed: dict, scraped_at: str | None = None) -> str:
    payload = {
        "source": feed.get("link"),
        "feed_title": feed.get("title"),
        "scraped_at_utc": scraped_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(items),
        "items": items,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_csv(items: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for item in items:
        row = {k: item.get(k) for k in CSV_COLUMNS}
        row["image"] = item.get("image_file") or item.get("image_url")
        row["related_links"] = len(item.get("related_links") or [])
        writer.writerow(row)
    return "\ufeff" + buf.getvalue()


def render_markdown(
    items: list[dict], feed: dict, scraped_at: str | None = None, with_text: bool = True
) -> str:
    stamp = scraped_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# {feed.get('title') or 'Google News'}",
        "",
        f"*{len(items)} items · scraped {stamp}*",
        "",
        f"Source: <{feed.get('link') or ''}>",
    ]
    for item in items:
        lines += ["", "---", "", f"## {item['position']}. {item['title']}", ""]
        meta = [item.get("publisher"), (item.get("published_iso") or "")[:16].replace("T", " ")]
        lines.append("*" + " · ".join(m for m in meta if m) + "*")
        image = item.get("image_file") or item.get("image_url")
        if image:
            lines += ["", f"![{item['title']}]({image})"]
        if item.get("description"):
            lines += ["", item["description"].strip()]
        if item.get("related_links"):
            lines += ["", "**Related coverage**"]
            for link in item["related_links"][:8]:
                href = link.get("resolved_url") or link["url"]
                lines.append(f"- [{link['title']}]({href}) — {link['publisher']}")
        if with_text and item.get("text"):
            excerpt = "\n\n".join(item["text"].split("\n\n")[:6])
            lines += ["", "### Article text", "", excerpt]
        lines += ["", f"<{item['url']}>"]
    return "\n".join(lines) + "\n"


def _esc_attr(value: Any) -> str:
    return _esc(value).replace("\n", " ")


def _mime(path: str) -> str:
    lowered = path.lower()
    if lowered.endswith(".png"):
        return "image/png"
    if lowered.endswith(".webp"):
        return "image/webp"
    if lowered.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


INLINE_MAX_WIDTH = 900
INLINE_MAX_BYTES = 120_000


def _b64(path: str) -> str:
    """Base64 of an image, downscaled first when it is large (Pillow optional)."""
    if os.path.getsize(path) <= INLINE_MAX_BYTES:
        with open(path, "rb") as fh:
            return base64.b64encode(fh.read()).decode()
    try:
        from PIL import Image

        with Image.open(path) as image:
            image = image.convert("RGB")
            if image.width > INLINE_MAX_WIDTH:
                ratio = INLINE_MAX_WIDTH / image.width
                image = image.resize((INLINE_MAX_WIDTH, int(image.height * ratio)))
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=72, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode()
    except Exception:
        with open(path, "rb") as fh:
            return base64.b64encode(fh.read()).decode()


def _thumb_html(item: dict) -> str:
    path = item.get("image_file")
    if path and os.path.exists(path):
        return (
            f'<img class="thumb" alt="{_esc_attr(item["title"])}" '
            f'src="data:{_mime(path)};base64,{_b64(path)}">'
        )
    if item.get("image_url"):
        return (
            f'<img class="thumb" alt="{_esc_attr(item["title"])}" '
            f'src="{_esc_attr(item["image_url"])}" loading="lazy">'
        )
    return '<div class="thumb-empty">بدون تصویر</div>'


_EXTRA_CSS = """
.summary p,.summary ul,details p,.title,.meta,.tag{unicode-bidi:plaintext;text-align:start}
.grid>*{min-width:0}
body{overflow-x:hidden}
p,li,summary,details p,.title,.meta{overflow-wrap:anywhere;word-break:break-word}
ul.related{margin:0;padding-inline-start:18px;font-size:13px;line-height:1.8;color:#b9c6dc}
ul.related a{color:#b9c6dc;text-decoration:none}
ul.related a:hover{text-decoration:underline;color:#fff}
ul.related .pub{color:#7d8aa3;font-size:11px;margin-inline-start:6px}
"""


def render_html(
    items: list[dict], feed: dict, scraped_at: str | None = None, with_text: bool = True
) -> str:
    stamp = scraped_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    title = feed.get("title") or "Google News"

    cards = []
    for item in items:
        related = "".join(
            f'<li><a href="{_esc_attr(link.get("resolved_url") or link["url"])}">'
            f"{_esc(link['title'])}</a>"
            f'<span class="pub">{_esc(link["publisher"])}</span></li>'
            for link in (item.get("related_links") or [])[:6]
        )
        text = ""
        if with_text and item.get("text"):
            paragraphs = item["text"].split("\n\n")[:6]
            text = "".join(f"<p>{_esc(p)}</p>" for p in paragraphs)
            if item.get("text_chars", 0) > sum(len(p) for p in paragraphs):
                text += (
                    "<details><summary>ادامه‌ی متن</summary>"
                    + "".join(f"<p>{_esc(p)}</p>" for p in item["text"].split("\n\n")[6:])
                    + "</details>"
                )

        cards.append(
            f"""
      <article class="card">
        {_thumb_html(item)}
        <div class="meta">#{item["position"]} · {_esc(item.get("publisher") or "")} ·
          {_esc((item.get("published_iso") or "")[:16].replace("T", " "))}</div>
        <h3 class="title">{_esc(item["title"])}</h3>
        {f'<div class="summary"><div class="label">DESCRIPTION</div><p>{_esc(item["description"])}</p></div>' if (item.get("description") or "").strip() else ""}
        {f'<div class="report"><div class="label">ARTICLE TEXT</div>{text}</div>' if text else ""}
        {f'<ul class="related">{related}</ul>' if related else ""}
        <div class="foot"><a href="{_esc_attr(item["url"])}">خواندن اصل خبر ↗</a></div>
      </article>"""
        )

    return f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<style>{_CSS}{_EXTRA_CSS}</style>
</head>
<body>
  <div class="wrap">
    <h1>{_esc(title)}</h1>
      <div class="lede" style="font-size:11.5px;letter-spacing:2.2px;text-transform:uppercase;color:#7d8aa3;margin:2px 0 16px">نبض فناوری · نمای تک‌منبع</div>

    <p class="lede">{len(items)} خبر · استخراج‌شده در {stamp} · لینک‌های Google News به آدرس ناشر باز شد</p>
    <div class="grid">{"".join(cards)}
    </div>
  </div>
</body>
</html>
"""
