"""Google News RSS scraper: resolve redirects, pull image + text + description."""

from .feed import (
    LinkResolver,
    candidate_pages,
    extract_article,
    extract_description,
    fetch_article,
    google_article_id,
    is_junk_url,
    parse_feed,
    strip_tags,
    to_iso,
)
from .render import (
    collect_items,
    download_image,
    download_image_chain,
    enrich_item,
    render_csv,
    render_html,
    render_json,
    render_markdown,
)

__all__ = [
    "LinkResolver",
    "candidate_pages",
    "collect_items",
    "download_image",
    "download_image_chain",
    "enrich_item",
    "extract_article",
    "extract_description",
    "fetch_article",
    "google_article_id",
    "is_junk_url",
    "parse_feed",
    "render_csv",
    "render_html",
    "render_json",
    "render_markdown",
    "strip_tags",
    "to_iso",
]
