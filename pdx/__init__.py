"""Scrapling-based scraper for Perplexity Discover news feeds.

Public API
----------
parse_article(api_response)      -> dict   (pure, no network)
build_item(...) / collect_items  -> list[dict]
render_html / render_markdown / render_csv / render_json  -> str / writes
scrape()                         -> list[dict] (needs browser)
"""

from .parser import (
    BASE_URL,
    DEFAULT_CATEGORY,
    build_item,
    clean_markdown,
    collect_items,
    domain_of,
    humanize_age,
)
from .render import (
    render_csv,
    render_html,
    render_json,
    render_markdown,
)

__all__ = [
    "BASE_URL",
    "DEFAULT_CATEGORY",
    "build_item",
    "clean_markdown",
    "collect_items",
    "domain_of",
    "humanize_age",
    "render_csv",
    "render_html",
    "render_json",
    "render_markdown",
]

__version__ = "1.6.0"
