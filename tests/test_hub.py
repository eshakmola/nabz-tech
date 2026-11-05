"""Tests for the combined hub page (3-way switch, date ordering, separate sources)."""

from __future__ import annotations

import json
import re

import pytest

from pdx.hub import (
    build_hub,
    gnews_entries,
    load_sources,
    perplexity_entries,
    render_hub,
)

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


@pytest.fixture()
def data(tmp_path):
    (tmp_path / "images").mkdir()
    (tmp_path / "gnews-images").mkdir()
    hero = tmp_path / "images" / "p1.png"
    hero.write_bytes(PNG)
    shot = tmp_path / "gnews-images" / "g1.png"
    shot.write_bytes(PNG)

    perplexity = {
        "count": 2,
        "items": [
            {
                "title": "Older Perplexity story",
                "url": "https://www.perplexity.ai/discover/tech/a",
                "published_iso": "2026-11-04T09:00:00",  # naive UTC
                "published": "3 hours ago",
                "summary": "P summary",
                "bullet_summary": "- one\n- two",
                "report_sections": [{"heading": "H", "body": "B"}],
                "sources_count": 12,
                "sources": [{"domain": "reuters.com", "url": "https://reuters.com/x"}],
                "image_file": "images/p1.png",
                "image_url": "https://pplx.example/p1.jpg",
                "read_time_min": 3,
                "category": "tech",
            },
            {
                "title": "Newest Perplexity story",
                "url": "https://www.perplexity.ai/discover/tech/b",
                "published_iso": "2026-11-04T17:00:00",
                "published": "10 minutes ago",
                "summary": "P2",
                "bullet_summary": "",
                "report_sections": [],
                "sources_count": 3,
                "sources": [],
                "image_file": "images/missing.png",
                "image_url": "https://pplx.example/p2.jpg",
                "read_time_min": 4,
                "category": "tech",
            },
        ],
    }
    gnews = {
        "count": 2,
        "items": [
            {
                "title": "Google News story",
                "url": "https://example.com/g",
                "published_iso": "2026-11-04T15:00:00+00:00",
                "publisher": "Example",
                "description": "G description",
                "text": "Para one.\n\nPara two.",
                "image_file": "gnews-images/g1.png",
                "image_url": "https://example.com/g.jpg",
                "related_links": [
                    {
                        "publisher": "Other",
                        "url": "https://news.google.com/x",
                        "resolved_url": "https://other.com/x",
                    }
                ],
            },
            {
                "title": "Undated Google News story",
                "url": "https://example.com/u",
                "published_iso": None,
                "publisher": "Example",
                "description": None,
                "text": "",
                "image_file": None,
                "image_url": None,
                "related_links": [],
            },
        ],
    }
    pj = tmp_path / "perplexity_tech.json"
    gj = tmp_path / "gnews.json"
    pj.write_text(json.dumps(perplexity), encoding="utf-8")
    gj.write_text(json.dumps(gnews), encoding="utf-8")
    return {"tmp": tmp_path, "p": str(pj), "g": str(gj), "perplexity": perplexity, "gnews": gnews}


# --------------------------------------------------------------------------- #
def test_entries_are_normalised_per_source(data):
    p = perplexity_entries(data["perplexity"], str(data["tmp"]))
    g = gnews_entries(data["gnews"], str(data["tmp"]))

    assert {e["source"] for e in p} == {"perplexity"}
    assert {e["source"] for e in g} == {"gnews"}
    assert p[0]["publisher"].startswith("Perplexity")
    assert p[0]["sources_count"] == 12
    assert p[0]["image"].startswith("data:image/png;base64,")
    assert g[0]["publisher"] == "Example"
    assert g[0]["text"].startswith("Para one")
    assert g[0]["sources"] == [{"domain": "Other", "url": "https://other.com/x"}]


def test_naive_timestamps_are_treated_as_utc(data):
    p = perplexity_entries(data["perplexity"], str(data["tmp"]))
    assert p[0]["ts"] == "2026-11-04T09:00:00+00:00"


def test_combined_view_is_sorted_by_date_desc(data):
    entries = load_sources(data["p"], data["g"])
    stamps = [e["ts"] or "" for e in entries]
    assert stamps == sorted(stamps, reverse=True)
    assert entries[0]["title"] == "Newest Perplexity story"
    assert entries[-1]["title"] == "Undated Google News story"  # بدون تاریخ → آخر
    assert len(entries) == 4
    assert [e["order"] for e in entries] == [1, 2, 3, 4]


def test_missing_image_falls_back_to_remote_url(data):
    entries = load_sources(data["p"], data["g"])
    fallback = next(e for e in entries if e["title"] == "Newest Perplexity story")
    assert fallback["image"] == "https://pplx.example/p2.jpg"


def test_inline_limit_zero_keeps_remote_urls(data):
    entries = load_sources(data["p"], data["g"], inline_limit=0)
    assert all(not (e["image"] or "").startswith("data:") for e in entries)


def test_sources_can_be_loaded_independently(data):
    only_p = load_sources(data["p"], None)
    only_g = load_sources(None, data["g"])
    assert {e["source"] for e in only_p} == {"perplexity"} and len(only_p) == 2
    assert {e["source"] for e in only_g} == {"gnews"} and len(only_g) == 2


# --------------------------------------------------------------------------- #
def test_render_hub_has_three_way_switch(data):
    entries = load_sources(data["p"], data["g"])
    html = render_hub(entries)

    assert 'dir="rtl"' in html
    buttons = re.findall(r'data-src="(all|perplexity|gnews)"', html)
    assert buttons == ["all", "perplexity", "gnews"]
    active = re.findall(r'<button[^>]+data-src="(\w+)"[^>]+aria-selected="true"', html)
    assert active == ["all"]  # فقط All در ابتدا فعال
    assert "Perplexity" in html and "G News" in html

    payload = json.loads(
        re.search(r"window\.__HUB__ = (\[.*?\]);</script>", html, re.S)
        .group(1)
        .replace("<\\/", "</")
    )
    assert len(payload) == 4
    assert {entry["source"] for entry in payload} == {"perplexity", "gnews"}
    # شمارنده‌ها در سوییچر
    assert '>All<span class="n">4</span>' in html
    assert '>Perplexity<span class="n">2</span>' in html
    assert '>G News<span class="n">2</span>' in html


def test_render_hub_escapes_and_has_no_external_assets(data):
    entries = load_sources(data["p"], data["g"])
    entries[0]["title"] = "</script><img src=x onerror=alert(1)>"
    html = render_hub(entries)
    # payload داخل <script> است: هیچ < یا > خامی نباید در آن باشد
    payload = re.search(r"window\.__HUB__ = (\[.*?\]);</script>", html, re.S).group(1)
    assert "<" not in payload and ">" not in payload
    assert html.count("</script>") == 2
    assert '<meta name="color-scheme" content="dark">' in html  # تم دارک
    assert 'class="dock"' in html  # سوییچر وسط‌چین/چسبان
    assert 'class="pill"' in html  # قرص متحرک سوییچر
    assert "<h1>نبض فناوری</h1>" in html  # نام صفحه
    assert 'src="http' not in html.split("<script>")[0]  # هیچ asset خارجی در head
    assert "cdn." not in html and "googleapis" not in html


def test_build_hub_writes_file_and_reports_counts(data, tmp_path):
    out = tmp_path / "site" / "index.html"
    info = build_hub(data["p"], data["g"], str(out))
    assert out.exists()
    assert info["count"] == 4 and info["perplexity"] == 2 and info["gnews"] == 2
    text = out.read_text(encoding="utf-8")
    assert "window.__HUB__" in text


def test_build_hub_with_missing_source(tmp_path, data):
    out = tmp_path / "hub.html"
    info = build_hub(data["p"], str(tmp_path / "nope.json"), str(out))
    assert info["count"] == 2 and info["gnews"] == 0
    assert 'G News<span class="n">0</span>' in out.read_text(encoding="utf-8")


def test_hub_cli_runs(tmp_path, data):
    from build_hub import main

    out = tmp_path / "site" / "index.html"
    rc = main(["--perplexity", data["p"], "--gnews", data["g"], "--out", str(out)])
    assert rc == 0
    assert out.exists()
    assert (tmp_path / "site" / ".nojekyll").exists()
    assert len(list((tmp_path / "site" / "archive").iterdir())) == 1
