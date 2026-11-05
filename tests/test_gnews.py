"""Unit tests for the Google News layer (no browser, no network)."""

from __future__ import annotations

import json
import os

import pytest

from gnews.feed import (
    candidate_pages,
    extract_article,
    extract_description,
    google_article_id,
    is_junk_url,
    parse_feed,
    strip_tags,
    to_iso,
)
from gnews.render import render_csv, render_html, render_json, render_markdown

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def read(name: str) -> str:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def feed():
    return parse_feed(read("gnews_feed.xml"))


# --------------------------------------------------------------------------- #
# feed parsing
# --------------------------------------------------------------------------- #
def test_feed_metadata(feed):
    channel, items = feed
    assert channel["title"] == "Technology - Latest - Google News"
    assert channel["language"] == "en-US"
    assert channel["last_build"].startswith("2026-11-04T")
    assert len(items) == 3


def test_items_have_title_link_and_date(feed):
    _, items = feed
    first = items[0]
    assert first["title"].endswith("- Gizmodo")
    assert "/rss/articles/CBM" in first["google_url"]
    assert first["published_iso"].endswith("+00:00")
    assert first["position"] == 1


def test_google_article_id():
    url = "https://news.google.com/rss/articles/CBMiABC123?oc=5"
    assert google_article_id(url) == "CBMiABC123"
    assert google_article_id("https://example.com/x") is None


def test_to_iso_rfc822():
    assert to_iso("Wed, 04 Nov 2026 15:10:54 GMT") == "2026-11-04T15:10:54+00:00"
    assert to_iso("garbage") is None
    assert to_iso(None) is None


def test_strip_tags_and_entities():
    assert strip_tags("a &amp; b&nbsp;<b>c</b>") == "a & b c"


# --------------------------------------------------------------------------- #
# description → related links
# --------------------------------------------------------------------------- #
def test_description_links_keep_title_and_publisher(feed):
    _, items = feed
    plain, links = extract_description(items[0]["google_description_html"])
    assert len(links) == 5
    assert links[0]["title"].startswith("Nintendo’s Switch 2")
    assert links[0]["publisher"] == "Gizmodo"
    assert links[1]["publisher"] == "The Verge"
    assert all(link["url"].startswith("https://news.google.com/rss/articles/") for link in links)
    assert links[0]["resolved_url"] is None
    assert "Gizmodo" in plain


def test_description_empty_input():
    assert extract_description("") == ("", [])
    assert extract_description("<ol></ol>")[1] == []


# --------------------------------------------------------------------------- #
# publisher page extraction
# --------------------------------------------------------------------------- #
PAGE = """<html><head>
<meta property="og:title" content="Nintendo&#39;s Switch 2 Situation">
<meta property="og:description" content="Owning a physical title could be a luxury.">
<meta property="og:image" content="https://gizmodo.com/app/uploads/DSC00618.jpg">
<meta property="og:site_name" content="Gizmodo">
</head><body><article>
<p>Short.</p>
<p>Macronix, which makes the ROM chips in Switch 1 and Switch 2 game memory cards,
   is quitting the consumer business entirely, according to a new report.</p>
<p>Analysts expect cartridge prices to rise through 2027 as a direct consequence.</p>
</article></body></html>"""


def test_extract_article_pulls_meta_and_paragraphs():
    data = extract_article(PAGE, url="https://gizmodo.com/nintendos-switch-2")
    assert data["title"] == "Nintendo's Switch 2 Situation"
    assert data["description"].startswith("Owning a physical")
    assert data["image"].endswith("DSC00618.jpg")
    assert data["site_name"] == "Gizmodo"
    assert data["paragraphs"] == 2  # short <p> skipped
    assert "Macronix" in data["text"]


def test_extract_article_handles_quotes_inside_meta():
    page = '<meta name="description" content=\'he said "no" twice\'>'
    assert extract_article(page)["description"] == 'he said "no" twice'


def test_extract_article_without_meta():
    data = extract_article(
        "<html><body><p>only a paragraph that is long enough to pass the sixty char filter.</p></body></html>"
    )
    assert data["title"] is None
    assert data["paragraphs"] == 1


def test_junk_urls():
    assert is_junk_url("https://consent.google.com/x")
    assert is_junk_url(None)
    assert not is_junk_url("https://www.theverge.com/tech/1024")


def test_resolver_parses_tokens_from_article_page():
    from gnews.feed import LinkResolver

    page = read("gnews_article_page.html")
    resolver = LinkResolver()
    resolver._get = lambda url: page  # no network
    params = resolver._params("https://news.google.com/rss/articles/X?oc=5")
    assert params is not None
    aid, ts, sig = params
    assert aid.startswith("CBM")
    assert isinstance(ts, int)
    assert len(sig) > 10


# --------------------------------------------------------------------------- #
# render
# --------------------------------------------------------------------------- #
@pytest.fixture()
def enriched():
    return [
        {
            "position": 1,
            "title": "Nintendo's Switch 2 Game Card Situation Just Became Dire - Gizmodo",
            "publisher": "Gizmodo",
            "published_iso": "2026-11-04T15:10:54+00:00",
            "url": "https://gizmodo.com/nintendos-switch-2-game-cards-matronix-2000834832",
            "google_url": "https://news.google.com/rss/articles/CBMiABC?oc=5",
            "resolved_url": "https://gizmodo.com/nintendos-switch-2-game-cards-matronix-2000834832",
            "description": "Physical games could become a luxury.",
            "text": "Para one is long enough.\n\nPara two is also long enough.",
            "text_chars": 55,
            "image_url": "https://gizmodo.com/app/uploads/x.jpg",
            "image_file": None,
            "related_links": [
                {
                    "title": "Nintendo is losing a supplier",
                    "publisher": "The Verge",
                    "url": "https://news.google.com/rss/articles/CBMiDEF?oc=5",
                    "resolved_url": "https://www.theverge.com/tech/1",
                }
            ],
        }
    ]


def test_render_json_and_csv(enriched):
    data = json.loads(render_json(enriched, {"title": "Tech", "link": "https://news.google.com/x"}))
    assert data["count"] == 1 and data["feed_title"] == "Tech"

    csv_text = render_csv(enriched)
    assert csv_text.startswith("\ufeff")
    header = csv_text.splitlines()[0].lstrip("\ufeff").split(",")
    assert header[:3] == ["position", "title", "publisher"]
    assert ",1," in csv_text or csv_text.count("\n") == 2


def test_render_markdown_uses_resolved_related_links(enriched):
    md = render_markdown(enriched, {"title": "Tech"}, with_text=True)
    assert "## 1. Nintendo" in md
    assert "https://www.theverge.com/tech/1" in md  # resolved, not google
    assert "### Article text" in md
    assert "**Related coverage**" in md


def test_render_html_contains_image_and_links(enriched):
    html = render_html(enriched, {"title": "Tech"})
    assert 'dir="rtl"' in html
    assert "DESCRIPTION" in html and "ARTICLE TEXT" in html
    assert "https://gizmodo.com/app/uploads/x.jpg" in html
    assert "https://www.theverge.com/tech/1" in html


def test_render_html_escapes(enriched):
    enriched[0]["title"] = "<script>x</script>"
    assert "<script>x" not in render_html(enriched, {"title": "T"})


# --------------------------------------------------------------------------- #
# candidate chain + fallback behaviour
# --------------------------------------------------------------------------- #
def test_candidate_pages_order_and_dedupe():
    related = [
        {
            "publisher": "The Verge",
            "url": "https://news.google.com/a",
            "resolved_url": "https://www.theverge.com/x",
        },
        {
            "publisher": "Gizmodo",
            "url": "https://news.google.com/b",
            "resolved_url": "https://gizmodo.com/y",
        },
        {
            "publisher": "Verge dup",
            "url": "https://news.google.com/c",
            "resolved_url": "https://www.theverge.com/other",
        },
        {"publisher": "Unresolved", "url": "https://news.google.com/d", "resolved_url": None},
    ]
    chain = candidate_pages("https://eurogamer.net/z", related, max_candidates=4)
    assert [step["origin"] for step in chain] == ["primary", "related", "related"]
    assert [step["url"] for step in chain] == [
        "https://eurogamer.net/z",
        "https://www.theverge.com/x",
        "https://gizmodo.com/y",
    ]


def test_candidate_pages_without_primary_and_with_cap():
    related = [
        {"publisher": "A", "url": "https://news.google.com/a", "resolved_url": "https://a.com/1"},
        {"publisher": "B", "url": "https://news.google.com/b", "resolved_url": "https://b.com/1"},
        {"publisher": "C", "url": "https://news.google.com/c", "resolved_url": "https://c.com/1"},
    ]
    assert len(candidate_pages(None, related, max_candidates=2)) == 2
    assert candidate_pages(None, [], 4) == []


def test_extract_article_collects_multiple_image_candidates():
    page = """<html><head>
      <meta property="og:image" content="/img/hero.jpg">
      <script type="application/ld+json">{"image": {"url": "https://x.com/ld.jpg"}}</script>
    </head><body>
      <img src="/logo.svg" width="300">
      <img data-src="https://x.com/inline.png" width="800">
      <p>A paragraph that is definitely longer than sixty characters so it survives.</p>
    </body></html>"""
    data = extract_article(page, url="https://x.com/post")
    assert data["images"][0] == "https://x.com/img/hero.jpg"  # og, made absolute
    assert "https://x.com/ld.jpg" in data["images"]  # JSON-LD
    assert "https://x.com/inline.png" in data["images"]  # lazy-loaded <img>
    assert all("logo" not in url for url in data["images"])  # junk filtered


def test_extract_article_meta_extras():
    page = """<meta property="og:title" content="T">
      <meta property="article:published_time" content="2026-11-04T10:00:00Z">
      <meta name="author" content="Jane Doe">
      <meta property="article:section" content="Tech">"""
    data = extract_article(page)
    assert data["published"] == "2026-11-04T10:00:00Z"
    assert data["author"] == "Jane Doe"
    assert data["section"] == "Tech"


def test_enrich_item_falls_back_to_description_link(monkeypatch):
    """Atlas: اگر لینک اصلی متن کافی ندارد، اولین لینک description امتحان شود."""
    from gnews import render as render_mod

    calls = []

    def fake_fetch(url, timeout=25, dynamic=False, content_only=False):
        calls.append(url)
        if "blocked.example" in url:
            return {
                "error": None,
                "status": 403,
                "text": "",
                "image": "/img/og.jpg",
                "images": ["https://blocked.example/img/og.jpg"],
                "fetched_url": url,
            }
        return {
            "status": 200,
            "text": "Full article body. " * 20,
            "image": "https://fallback.example/hero.jpg",
            "images": ["https://fallback.example/hero.jpg"],
            "fetched_url": url,
            "site_name": "Fallback News",
            "description": "fallback description",
        }

    monkeypatch.setattr(render_mod, "fetch_article", fake_fetch)

    class FakeResolver:
        def resolve(self, url, fallback=None):
            mapping = {
                "https://news.google.com/main": "https://blocked.example/story",
                "https://news.google.com/rel": "https://fallback.example/story",
            }
            return mapping.get(url)

    item = {
        "title": "T",
        "google_url": "https://news.google.com/main",
        "google_description_html": (
            '<ol><li><a href="https://news.google.com/rel">Other</a>'
            '&nbsp;&nbsp;<font color="#6f6f6f">Fallback News</font></li></ol>'
        ),
    }
    out = render_mod.enrich_item(item, FakeResolver(), log=lambda *_: None)

    assert calls == ["https://blocked.example/story", "https://fallback.example/story"]
    assert out["text_chars"] > 200
    assert out["text_from_related"] is True
    assert out["text_source"] == "https://fallback.example/story"
    assert out["url"] == "https://fallback.example/story"
    # تصویر از لینک اصلی گرفته شد، هرچند متنش بلاک بود
    assert out["image_url"] == "/img/og.jpg"
    assert out["image_source"] == "https://blocked.example/story"
    # v1.2: فقط یک تصویر شاخص؛ از لینک اصلی گرفته می‌شود حتی اگر متنش بلاک باشد
    assert out["image_url"] == "/img/og.jpg"
    assert out["image_source"] == "https://blocked.example/story"
    assert len(out["tried"]) == 2


def test_enrich_item_stops_visiting_once_text_and_image_found(monkeypatch):
    """v1.2: به‌محض داشتن متن کامل + تصویر، بقیه‌ی کاندیدها باز نمی‌شوند."""
    from gnews import render as render_mod

    calls = []

    def fake_fetch(url, timeout=25, dynamic=False, content_only=False):
        calls.append(url)
        return {
            "status": 200,
            "text": "x" * 900,
            "image": "https://a.com/1.jpg",
            "images": ["https://a.com/1.jpg"],
            "site_name": "A",
        }

    monkeypatch.setattr(render_mod, "fetch_article", fake_fetch)

    class FakeResolver:
        def resolve(self, url, fallback=None):
            return {
                "https://news.google.com/main": "https://a.com/story",
                "https://news.google.com/rel": "https://b.com/story",
            }.get(url)

    item = {
        "title": "T",
        "google_url": "https://news.google.com/main",
        "google_description_html": '<li><a href="https://news.google.com/rel">R</a>'
        "<font>B</font></li>",
    }
    out = render_mod.enrich_item(item, FakeResolver(), log=lambda *_: None)
    assert calls == ["https://a.com/story"]
    assert out["text_from_related"] is False


def test_max_candidates_limits_attempts(monkeypatch):
    """v1.2: سقف ۴ لینک (لینک اصلی + ۳ لینک description) وقتی هیچ صفحه‌ای جواب نمی‌دهد."""
    from gnews import render as render_mod

    calls = []

    def fake_fetch(url, timeout=25, dynamic=False, content_only=False):
        calls.append(url)
        return {"status": 403, "text": "", "image": None, "images": []}

    monkeypatch.setattr(render_mod, "fetch_article", fake_fetch)

    class FakeResolver:
        def resolve(self, url, fallback=None):
            return {
                "https://news.google.com/0": "https://a.com/s",
                "https://news.google.com/1": "https://b.com/s",
                "https://news.google.com/2": "https://c.com/s",
                "https://news.google.com/3": "https://d.com/s",
                "https://news.google.com/4": "https://e.com/s",
            }.get(url)

    links = "".join(
        f'<li><a href="https://news.google.com/{i}">L{i}</a><font>P{i}</font></li>'
        for i in range(1, 5)
    )
    item = {
        "title": "T",
        "google_url": "https://news.google.com/0",
        "google_description_html": f"<ol>{links}</ol>",
    }
    render_mod.enrich_item(item, FakeResolver(), max_candidates=4, log=lambda *_: None)
    assert len(calls) == 4  # ۱ اصلی + ۳ لینک description
    assert calls[0] == "https://a.com/s"


def test_download_image_chain_tries_next_candidate(monkeypatch, tmp_path):
    from gnews import render as render_mod

    class FakeResponse:
        def __init__(self, body):
            self.body = body

    def fake_get(url, timeout=25):
        if "broken" in url:
            raise RuntimeError("boom")
        return FakeResponse(b"\xff\xd8" + b"x" * 5000)

    sf = pytest.importorskip("scrapling.fetchers")  # فقط در CI با نصب کامل

    monkeypatch.setattr(sf, "Fetcher", type("F", (), {"get": staticmethod(fake_get)}))
    path, used = render_mod.download_image_chain(
        ["https://broken.example/a.jpg", "https://ok.example/b.jpg"], "slug1", str(tmp_path)
    )
    assert path and used == "https://ok.example/b.jpg"
    assert os.path.getsize(path) > 1000


# --------------------------------------------------------------------------- #
# gallery / "check every description link"
# --------------------------------------------------------------------------- #
def _fake_fetch_factory(per_url):
    calls = []

    def fake_fetch(url, timeout=25, dynamic=False, content_only=False):
        calls.append(url)
        return per_url(url)

    return fake_fetch, calls


def test_render_html_has_no_gallery_and_links_plain(tmp_path):
    from gnews.render import render_html

    hero = tmp_path / "hero.jpg"
    hero.write_bytes(b"\xff\xd8" + b"h" * 400)
    item = {
        "position": 1,
        "title": "T",
        "publisher": "P",
        "url": "https://p.com/s",
        "description": "d",
        "text": "Some body text.",
        "text_chars": 15,
        "image_file": str(hero),
        "related_links": [
            {
                "title": "Other",
                "publisher": "Q",
                "url": "https://q.com/s",
                "resolved_url": "https://q.com/s",
            },
        ],
    }
    html = render_html([item], {"title": "Feed"})
    assert html.count("data:image/jpeg;base64,") == 1  # فقط تصویر شاخص
    assert 'class="gallery"' not in html and 'class="rm"' not in html
    assert "https://q.com/s" in html  # لینک مرتبط بدون تصویر
