"""Unit tests for the render layer + CLI re-render path."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import pytest

from pdx.parser import build_item
from pdx.render import render_csv, render_html, render_json, render_markdown

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001 0d0a2db40000000049454e44ae426082".replace(" ", "")
)


@pytest.fixture()
def item() -> dict:
    with open(os.path.join(FIXTURES, "mini_article.json"), encoding="utf-8") as fh:
        payload = json.load(fh)
    return build_item("chip-exports-slow", payload, position=1, category="tech", now=NOW)


# --------------------------------------------------------------------------- #
def test_render_json_roundtrip(item):
    data = json.loads(render_json([item], source="https://www.perplexity.ai/discover/tech"))
    assert data["count"] == 1
    assert data["items"][0]["title"] == "Chip exports slow in Asia"
    assert data["scraped_at_utc"]


def test_render_csv_has_bom_and_columns(item):
    out = render_csv([item])
    assert out.startswith("\ufeff")
    header = out.splitlines()[0].lstrip("\ufeff")
    assert header.split(",")[:3] == ["position", "title", "summary"]


def test_render_markdown_contains_all_parts(item):
    md = render_markdown([item], category="tech", scraped_at="2026-11-04 12:00 UTC")
    assert "# Perplexity Discover — tech" in md
    assert "## 1. Chip exports slow in Asia" in md
    assert "**Summary:**" in md
    assert "### Report" in md
    assert "#### Why it matters" in md
    assert "**Sources:**" in md


def test_render_html_contains_sections(item):
    html = render_html([item], category="tech")
    assert 'dir="rtl"' in html
    assert "SUMMARY" in html and "REPORT" in html
    assert "Chip exports slow in Asia" in html
    assert "<details>" in html


def test_render_html_inlines_local_image(item, tmp_path):
    image = tmp_path / "shot.png"
    image.write_bytes(PNG_1PX)
    item["image_file"] = str(image)
    html = render_html([item], category="tech")
    assert "data:image/png;base64," in html


def test_render_html_falls_back_to_remote_url(item):
    assert "https://pplx-res.cloudinary.com" in render_html([item], category="tech")


def test_render_html_escapes_user_content(item):
    item["title"] = '<script>alert("x")</script>'
    html = render_html([item], category="tech")
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


# --------------------------------------------------------------------------- #
def test_cli_rerender_from_json(tmp_path):
    """`--from-json` must rebuild every format without a browser."""
    from perplexity_tech_scraper import main

    with open(os.path.join(FIXTURES, "mini_article.json"), encoding="utf-8") as fh:
        payload = json.load(fh)
    item = build_item("chip-exports-slow", payload, position=1, category="tech", now=NOW)
    source_json = tmp_path / "in.json"
    source_json.write_text(
        render_json([item], source="https://www.perplexity.ai/discover/tech"),
        encoding="utf-8",
    )

    out_dir = tmp_path / "out"
    site_dir = tmp_path / "site"
    rc = main(
        ["--from-json", str(source_json), "--out", str(out_dir), "--site", str(site_dir), "--quiet"]
    )
    assert rc == 0
    for suffix in (".json", ".csv", ".md", ".html"):
        assert (out_dir / f"perplexity_tech{suffix}").exists()
    assert (site_dir / "index.html").exists()
    assert (site_dir / ".nojekyll").exists()
    assert len(list((site_dir / "archive").iterdir())) == 1


def test_cli_help_runs():
    result = subprocess.run(
        [sys.executable, "perplexity_tech_scraper.py", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--category" in result.stdout
    assert "--site" in result.stdout
