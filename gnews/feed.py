"""Google News RSS parsing + Google→publisher link resolution.

Everything here is pure/network-only (no browser), so it is fast and testable.

Pipeline
--------
1. ``parse_feed(xml)``      → items with *title*, *pubDate*, *google_url*
2. ``resolve_google_url()``   → real publisher URL (via the batchexecute RPC)
3. ``extract_description()``  → HTML link list taken from ``<description>``
4. ``fetch_article()``        → title / hero image / body text from the publisher
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

BATCH_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
GOOGLE_NEWS = "https://news.google.com"

#: دامنه‌هایی که «ناشر» نیستند و متن/تصویر معتبری ندارند
_JUNK_DOMAINS = ("consent.google.com", "news.google.com", "policies.google.com")

_ITEM_TAG = re.compile(r"<item>(.*?)</item>", re.S)
_LINK_TAG = re.compile(r"<link>(.*?)</link>", re.S)
_TITLE_TAG = re.compile(r"<title>(.*?)</title>", re.S)
_DATE_TAG = re.compile(r"<pubDate>(.*?)</pubDate>", re.S)
_DESC_TAG = re.compile(r"<description>(.*?)</description>", re.S)
_ANCHOR = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_FONT = re.compile(r"<font[^>]*>(.*?)</font>", re.S)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def strip_tags(raw: str | None) -> str:
    if not raw:
        return ""
    text = _TAG.sub(" ", html.unescape(raw))
    return _WS.sub(" ", text).strip()


def unescape(text: str) -> str:
    return html.unescape(text or "").strip()


def to_iso(pub_date: str | None) -> str | None:
    """RFC-822 (``Wed, 04 Nov 2026 15:10:54 GMT``) → ISO-8601 UTC."""
    if not pub_date:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            dt = datetime.strptime(pub_date.strip(), fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def is_junk_url(url: str | None) -> bool:
    return not url or any(domain in url for domain in _JUNK_DOMAINS)


# --------------------------------------------------------------------------- #
# 1) feed
# --------------------------------------------------------------------------- #
def parse_feed(xml_text: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Parse a Google News RSS document into ``(channel_meta, items)``.

    The regex-based item split is intentional: Google's feed is machine
    generated and flat, and this keeps us tolerant of stray ``&`` entities
    that make strict parsers give up on the whole document.
    """
    channel: dict[str, Any] = {}
    try:  # best effort metadata (title/link/lastBuildDate)
        root = ET.fromstring(xml_text)
        ch = root.find("channel")
        if ch is not None:
            channel = {
                "title": (ch.findtext("title") or "").strip(),
                "link": (ch.findtext("link") or "").strip(),
                "language": (ch.findtext("language") or "").strip(),
                "last_build": to_iso(ch.findtext("lastBuildDate")),
                "image": (ch.findtext("image/url") or "").strip() or None,
            }
    except ET.ParseError:
        pass

    items: list[dict[str, Any]] = []
    for position, block in enumerate(_ITEM_TAG.findall(xml_text), start=1):
        title = _TITLE_TAG.search(block)
        link = _LINK_TAG.search(block)
        date = _DATE_TAG.search(block)
        desc = _DESC_TAG.search(block)
        if not link:
            continue
        items.append(
            {
                "position": position,
                "title": unescape(title.group(1)) if title else None,
                "google_url": unescape(link.group(1)),
                "published_iso": to_iso(date.group(1)) if date else None,
                "google_description_html": unescape(desc.group(1)) if desc else "",
            }
        )
    return channel, items


def google_article_id(google_url: str) -> str | None:
    match = re.search(r"/articles/([^?]+)", google_url)
    return match.group(1) if match else None


# --------------------------------------------------------------------------- #
# 2) description → structured link list (با حفظ ترتیب، بدون آدرس سایت خودش)
# --------------------------------------------------------------------------- #
def extract_description(description_html: str) -> tuple[str, list[dict[str, str]]]:
    """Split Google's ``<description>`` into (plain_text, related_links).

    گوگل هر پوشش مرتبط را این‌طور می‌دهد::

        <li><a href="…">عنوان</a>&nbsp;&nbsp;<font color="#6f6f6f">ناشر</font></li>

    خروجی ``related_links`` = ``[{"title", "publisher", "url", "resolved_url"}]``
    به همان ترتیبی که در فید آمده است.
    """
    if not description_html:
        return "", []

    links: list[dict[str, str]] = []
    blocks = re.findall(r"<li[^>]*>(.*?)</li>", description_html, re.S) or [description_html]
    for block in blocks:
        anchor = _ANCHOR.search(block)
        if not anchor:
            continue
        font = _FONT.search(block)  # <font> بیرون از <a> است
        links.append(
            {
                "title": strip_tags(anchor.group(2)),
                "publisher": strip_tags(font.group(1)) if font else "",
                "url": unescape(anchor.group(1)),
                "resolved_url": None,
            }
        )

    plain = strip_tags(description_html)
    return plain, links


# --------------------------------------------------------------------------- #
# 3) Google News redirect → publisher URL
# --------------------------------------------------------------------------- #
class LinkResolver:
    """Resolves ``news.google.com/rss/articles/CBM…`` links to publisher URLs.

    Needs a cheap HTTP GET per link to read the ``data-n-a-id/ts/sg`` tokens,
    then one RPC call to ``batchexecute``. ~0.1s per link, no browser.
    """

    def __init__(self, timeout: int = 20, delay: float = 0.0, log=print) -> None:
        self.timeout = timeout
        self.delay = delay
        self.log = log
        self._cache: dict[str, str | None] = {}

    # -- internals ---------------------------------------------------------- #
    def _params(self, google_url: str) -> tuple[str, int, str] | None:
        page = self._get(google_url)
        if not page:
            return None
        aid = re.search(r'data-n-a-id="([^"]+)"', page)
        ts = re.search(r'data-n-a-ts="([^"]+)"', page)
        sig = re.search(r'data-n-a-sg="([^"]+)"', page)
        if not (aid and ts and sig):
            return None
        return aid.group(1), int(ts.group(1)), sig.group(1)

    def _get(self, url: str) -> str | None:
        try:
            from scrapling.fetchers import Fetcher

            return Fetcher.get(url, timeout=self.timeout).html_content or ""
        except Exception as exc:
            self.log(f"    ! resolve page failed: {exc}")
            return None

    def _rpc(self, aid: str, ts: int, sig: str) -> str | None:
        inner = json.dumps(
            [
                "garturlreq",
                [
                    [
                        "X",
                        "X",
                        ["X", "X"],
                        None,
                        None,
                        1,
                        1,
                        "US:en",
                        None,
                        1,
                        None,
                        None,
                        None,
                        None,
                        None,
                        0,
                        1,
                    ],
                    "X",
                    "X",
                    1,
                    [1, 1, 1],
                    1,
                    1,
                    None,
                    0,
                    0,
                    None,
                    0,
                ],
                aid,
                ts,
                sig,
            ]
        )
        payload = urllib.parse.urlencode(
            {"f.req": json.dumps([[["Fbv4je", inner, None, "generic"]]])}
        ).encode()
        request = urllib.request.Request(
            BATCH_URL,
            data=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "User-Agent": "Mozilla/5.0 (compatible; gnews-scraper/1.0)",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", "ignore")
        except Exception as exc:
            self.log(f"    ! batchexecute failed: {exc}")
            return None
        found = re.search(r'https?://[^"\\\s]+', body)
        return found.group(0) if found else None

    # -- public ------------------------------------------------------------- #
    def resolve(self, google_url: str, fallback: str | None = None) -> str | None:
        if google_url in self._cache:
            return self._cache[google_url]
        result: str | None = None
        params = self._params(google_url)
        if params:
            result = self._rpc(*params)
        if not result and fallback and not fallback.startswith(GOOGLE_NEWS):
            result = fallback
        self._cache[google_url] = result
        if self.delay:
            time.sleep(self.delay)
        return result


# --------------------------------------------------------------------------- #
# 4) publisher page → image + text
# --------------------------------------------------------------------------- #
def _image_candidates(html_text: str, meta: dict[str, str], base_url: str = "") -> list[str]:
    """همه‌ی تصویرهای محتمل صفحه، به‌ترتیب اولویت (og → twitter → JSON-LD → img)."""
    found: list[str] = []

    def push(value: str | None) -> None:
        if not value:
            return
        candidate = unescape(value).strip()
        if not candidate or candidate.startswith("data:"):
            return
        candidate = urllib.parse.urljoin(base_url, candidate)
        if candidate not in found:
            found.append(candidate)

    for key in (
        "og:image",
        "og:image:secure_url",
        "og:image:url",
        "twitter:image",
        "twitter:image:src",
        "image",
    ):
        push(meta.get(key))

    # JSON-LD: "image": "…" یا "image": {"url": "…"} یا لیست
    for block in re.findall(
        r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", html_text, re.S | re.I
    ):
        for match in re.finditer(r'"image"\s*:\s*(\{[^}]*\}|\[[^\]]*\]|"[^"]+")', block):
            raw = match.group(1)
            for url in re.findall(r'"(?:url|contentUrl)"\s*:\s*"([^"]+)"', raw) or re.findall(
                r'"(https?://[^"]+)"', raw
            ):
                push(url.replace("\\/", "/"))

    # <img> با فیلترهای کیفی (لوگو/آواتار/آیکون/اسپینر را رد کن)
    for tag in re.findall(r"<img\b[^>]*>", html_text, re.I):
        src = re.search(r"""(?:data-src|data-original|srcset|src)\s*=\s*["']([^"']+)""", tag, re.I)
        if not src:
            continue
        url = src.group(1).split(",")[0].strip().split(" ")[0]
        lowered = url.lower()
        if any(
            bad in lowered
            for bad in ("logo", "avatar", "icon", "sprite", "1x1", "spinner", "blank")
        ):
            continue
        if re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", lowered) is None and "image" not in lowered:
            continue
        dims = re.search(r'width\s*=\s*["\']?(\d+)', tag, re.I)
        if dims and int(dims.group(1)) < 200:
            continue
        push(url)

    return found


def extract_article(html_text: str, url: str = "") -> dict[str, Any]:
    """Pull title / images / body paragraphs out of a publisher page.

    همه‌ی تصویرهای محتمل در ``images`` برمی‌گردند (نه فقط اولی) تا اگر
    دانلود تصویر اصلی شکست خورد، بعدی‌ها امتحان شوند.
    """
    meta = _meta_map(html_text)
    title = meta.get("og:title") or _first(html_text, r"<title[^>]*>(.*?)</title>")
    images = _image_candidates(html_text, meta, base_url=url)
    description = (
        meta.get("og:description") or meta.get("description") or meta.get("twitter:description")
    )
    paragraphs = _paragraphs(html_text)

    published = (
        meta.get("article:published_time")
        or meta.get("article:modified_time")
        or meta.get("datepublished")
        or _first(html_text, r'"datePublished"\s*:\s*"([^"]+)"')
    )
    author = (
        meta.get("author")
        or meta.get("article:author")
        or _first(html_text, r'"author"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"')
    )
    section = meta.get("article:section")

    return {
        "site_name": meta.get("og:site_name") or _host(url),
        "final_url": url,
        "title": strip_tags(title) if title else None,
        "description": strip_tags(description) if description else None,
        "image": images[0] if images else None,
        "images": images,
        "text": "\n\n".join(paragraphs).strip(),
        "paragraphs": len(paragraphs),
        "published": published,
        "author": strip_tags(author) if author else None,
        "section": section,
    }


def _meta_map(html_text: str) -> dict[str, str]:
    """Collect ``<meta>`` pairs, tolerating apostrophes inside the content value."""
    out: dict[str, str] = {}
    for tag in re.findall(r"<meta\s+[^>]*>", html_text, re.I):
        key = re.search(r"""(?:property|name)\s*=\s*["']([^"']+)""", tag, re.I)
        val = re.search(r"""content\s*=\s*("([^"]*)"|'([^']*)')""", tag, re.I | re.S)
        if not (key and val):
            continue
        value = val.group(2) if val.group(2) is not None else val.group(3)
        out.setdefault(key.group(1).lower(), html.unescape(value or ""))
    return out


def _first(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.I | re.S)
    return match.group(1) if match else None


def _host(url: str) -> str | None:
    try:
        return urllib.parse.urlparse(url).netloc.replace("www.", "") or None
    except ValueError:
        return None


_BOILERPLATE = re.compile(
    r"(cookies?|subscribe|newsletter|sign in|sign up|advertisement|all rights reserved"
    r"|privacy policy|terms of (use|service)|share this|read more|follow us"
    r"|posts from this topic|newsletter|switch site|home page)",
    re.I,
)


def _paragraphs(html_text: str) -> list[str]:
    """Extract readable paragraphs.

    A page often contains several ``<article>`` elements (sidebar cards, related
    posts). We score each block by paragraph volume and keep the richest one,
    falling back to the whole document when that yields too little.
    """
    blocks = [
        match.group(1)
        for match in re.finditer(r"<article[^>]*>(.*?)</article>", html_text, re.S | re.I)
    ]
    blocks.sort(key=len, reverse=True)

    best: list[str] = []
    for scope in [*blocks[:3], html_text]:
        found = _paragraphs_in(scope)
        if len(found) > len(best):
            best = found
        if len(best) >= 3:  # good enough, stop early
            break
    return best[:40]


def _paragraphs_in(scope: str) -> list[str]:
    found: list[str] = []
    for chunk in re.findall(r"<p[^>]*>(.*?)</p>", scope, re.S | re.I):
        text = strip_tags(chunk)
        if len(text) < 60:  # skip captions / one-liners
            continue
        if text in found:  # de-duplicate
            continue
        if _BOILERPLATE.search(text[:160]):  # nav / consent / ads
            continue
        if text.count("|") > 3:  # menu rows
            continue
        if len(re.findall(r"<a\b", chunk, re.I)) >= 3 and len(text) < 220:
            continue  # nav / thumbnail grids
        found.append(text)
    return found


# --------------------------------------------------------------------------- #
def fetch_article(
    url: str, timeout: int = 25, dynamic: bool = False, content_only: bool = False
) -> dict[str, Any]:
    """Fetch a publisher page (HTTP first, stealth browser as fallback).

    ``content_only=True`` skips the browser even when the body looks empty —
    used by the cheap describe-only / candidate-hunting passes.
    """
    if not url or is_junk_url(url):
        return {"error": "no usable url", "final_url": url}

    try:
        from scrapling.fetchers import Fetcher

        page = Fetcher.get(url, timeout=timeout)
    except Exception as exc:
        return {"error": str(exc), "final_url": url}

    data = extract_article(page.html_content or "", url=page.url or url)
    data["status"] = page.status
    data["fetched_url"] = page.url or url

    # متن خیلی کوتاه + مجوز مرورگر → دوباره با مرورگر مخفی و ادغام نتایج
    if not content_only and len(data.get("text") or "") < 200 and dynamic:
        try:
            from scrapling.fetchers import StealthyFetcher

            page = StealthyFetcher.fetch(
                url, headless=True, network_idle=True, timeout=timeout * 3000
            )
            dynamic_data = extract_article(page.html_content or "", url=page.url or url)
            dynamic_data["status"] = page.status
            dynamic_data["fetched_url"] = page.url or url
            for key, value in dynamic_data.items():
                if value not in (None, "", [], 0) or key not in data:
                    data[key] = value
            data["dynamic"] = True
        except Exception as exc:
            data["dynamic_error"] = str(exc)
    return data


# --------------------------------------------------------------------------- #
# 5) candidate chain: main link first, then every link inside <description>
# --------------------------------------------------------------------------- #
def _same_url(url_a: str | None, url_b: str | None) -> bool:
    if not (url_a and url_b):
        return False
    return url_a.split("?")[0].rstrip("/") == url_b.split("?")[0].rstrip("/")


def candidate_pages(
    primary_url: str | None,
    related: list[dict[str, Any]],
    max_candidates: int = 4,
) -> list[dict[str, str]]:
    """ترتیب تلاش برای متن/تصویر: لینک اصلی، بعد لینک‌های داخل ``<description>``.

    قواعد: بدون آدرس تکراری، و از هر دامنه فقط یک تلاش (چون سایت‌های یک ناشر
    معمولاً همان بلاک/قالب را دارند). خروجی::

        [{"url": …, "publisher": …, "origin": "primary" | "related"}]
    """
    chain: list[dict[str, str]] = []
    seen_hosts: set[str] = set()

    if primary_url and not is_junk_url(primary_url):
        chain.append({"url": primary_url, "publisher": "", "origin": "primary"})
        seen_hosts.add(_host(primary_url) or "")

    for link in related:
        if len(chain) >= max_candidates:
            break
        url = link.get("resolved_url") or link.get("url")
        if is_junk_url(url) or any(_same_url(url, step["url"]) for step in chain):
            continue
        host = _host(url) or ""
        if host and host in seen_hosts:
            continue
        seen_hosts.add(host)
        chain.append({"url": url, "publisher": link.get("publisher") or "", "origin": "related"})

    return chain[:max_candidates]
