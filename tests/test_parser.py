"""Unit tests for the pure parsing layer (no browser, no network)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest

from pdx.parser import (
    build_item,
    clean_markdown,
    collect_items,
    domain_of,
    humanize_age,
    parse_article,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)


def load(name: str) -> dict:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def mini() -> dict:
    return load("mini_article.json")


# --------------------------------------------------------------------------- #
# clean_markdown
# --------------------------------------------------------------------------- #
def test_entity_chip_is_unwrapped():
    assert clean_markdown("blame [Samsung](pplx://entity_chip/abc123) here") == "blame Samsung here"


def test_inline_citations_are_dropped():
    assert clean_markdown("Exports fell 4%[1][2].") == "Exports fell 4%."


def test_empty_and_none_input():
    assert clean_markdown(None) == ""
    assert clean_markdown("") == ""


def test_collapses_extra_blank_lines():
    assert clean_markdown("a\n\n\n\nb") == "a\n\nb"


# --------------------------------------------------------------------------- #
# humanize_age
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "iso,expected",
    [
        ("2026-11-04T11:59:30", "just now"),
        ("2026-11-04T11:30:00", "30 minutes ago"),
        ("2026-11-04T11:00:00", "1 hour ago"),
        ("2026-11-04T09:00:00", "3 hours ago"),
        ("2026-11-03T12:00:00", "1 day ago"),
        ("2026-10-30T12:00:00", "5 days ago"),
    ],
)
def test_humanize_age(iso, expected):
    assert humanize_age(iso, now=NOW) == expected


def test_humanize_age_handles_timezone_aware_and_bad_input():
    assert humanize_age("2026-11-04T09:00:00+00:00", now=NOW) == "3 hours ago"
    assert humanize_age("not-a-date", now=NOW) is None
    assert humanize_age(None, now=NOW) is None


def test_domain_of():
    assert domain_of("https://www.reuters.com/tech/chips") == "reuters.com"
    assert domain_of(None) == ""


# --------------------------------------------------------------------------- #
# parse_article / build_item
# --------------------------------------------------------------------------- #
def test_parse_article_sections_and_sources(mini):
    parsed = parse_article(mini)
    assert parsed["title"] == "Chip exports slow in Asia"
    assert parsed["summary"].startswith("Exports fell 4%")
    assert parsed["read_time_min"] == 3
    assert [s["heading"] for s in parsed["report_sections"]] == [
        "Chip exports slow in Asia",
        "Why it matters",
    ]
    assert "pplx://" not in json.dumps(parsed["report_sections"])
    assert parsed["report_chars"] > 50


def test_parse_article_deduplicates_sources(mini):
    parsed = parse_article(mini)
    urls = [s["url"] for s in parsed["sources"]]
    assert len(urls) == len(set(urls)) == 3
    assert parsed["sources_count"] == 3
    assert parsed["sources"][0]["domain"] == "reuters.com"


def test_parse_article_image_and_credit(mini):
    parsed = parse_article(mini)
    assert parsed["image_url"].endswith("demo.jpg")
    assert parsed["image_credit"].startswith("https://www.gettyimages.com")


def test_parse_article_rejects_empty_payload():
    with pytest.raises(ValueError):
        parse_article({"entries": []})


def test_build_item_adds_metadata(mini):
    item = build_item("chip-exports-slow", mini, position=4, category="tech", now=NOW)
    assert item["position"] == 4
    assert item["category"] == "tech"
    assert item["url"] == "https://www.perplexity.ai/discover/tech/chip-exports-slow"
    assert item["published"] == "2 hours ago"
    assert item["image_file"] is None


def test_collect_items_skips_errors(mini):
    payloads = {
        "good": mini,
        "bad": {"error": "HTTP 400"},
        "empty": {"entries": []},
    }
    items = collect_items(payloads, order=["bad", "good", "empty"], category="tech", now=NOW)
    assert [i["slug"] for i in items] == ["good"]
    assert items[0]["position"] == 1


def test_real_world_fixture_parses():
    """Regression test on a real captured /rest/article response."""
    payload = load("article_sample.json")
    parsed = parse_article(payload)
    assert parsed["title"]
    assert parsed["summary"]
    assert len(parsed["report_sections"]) >= 2
    assert parsed["report_chars"] > 1000
    assert parsed["sources_count"] >= 5
    assert "[1]" not in parsed["report_sections"][0]["body"]
