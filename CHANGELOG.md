# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/).

## [1.5.0] - 2026-11-05

### Added
- **Cloudflare Worker** (`cloudflare/`): one deployment serving the dark hub page *and* a
  read-only JSON API (`/api/news`, `/api/perplexity`, `/api/gnews`, `/api/hub`,
  `/api/item/:id`, `/api/rss`), with `source/q/limit/offset/since/lang` filters, CORS,
  edge caching, KV-first + `raw.githubusercontent.com` fallback.
- `scripts/publish_data.py`: writes `data/perplexity_tech.json`, `data/gnews.json`
  (still separate) plus `data/hub.json` (combined view), and can push to Cloudflare KV
  (`--kv`).
- `publish.yml`: scrape → build page → publish data → KV → GitHub Pages → Worker deploy
  (every 3 hours, plus manual dispatch).
- `cloudflare/test-local.mjs`: 12 offline checks for the worker (no Cloudflare account needed).

## [1.4.0] - 2026-11-04

### Changed
- Hub redesign: **dark theme**, centered sticky 3-way switch with a sliding pill,
  Persian (Jalali) dates rendered client-side without `Intl`, markdown-lite in
  summaries/reports, per-source accent colors, card hover/animation polish.
- The page is now named **«نبض فناوری»** (`pdx.hub.HUB_TITLE`, `--title` to override).
- Per-source pages (`perplexity_tech.html`, `gnews.html`) use the same dark theme,
  auto text direction for Latin text, and skip empty summary/description blocks.
- Fixed horizontal overflow caused by long unbreakable article text
  (now `overflow-wrap:anywhere` + `min-width:0` grid children).

### Added
- **Combined hub page** (`pdx/hub.py` + `build_hub.py`): one RTL page with a
  three-way switch (**All / Perplexity / G News**), date-descending grouping per
  day, per-source badges and counts, hash-persisted filter, and base64-inlined
  images (no external assets).
- Data stays separate: Perplexity (`output/perplexity_tech.*` + `images/`) and
  Google News (`output/gnews.*` + `gnews-images/`) keep their own JSON/CSV/MD/HTML.
- `build_hub.py --refresh` runs both scrapers then builds the page; writes
  `site/index.html`, a dated archive copy and `.nojekyll`.
- 11 new tests (64 total): normalisation, UTC handling of naive timestamps,
  date ordering, per-source loading, switch markup/counts, JSON-in-script
  escaping, missing-source handling, CLI.
- `scrape.yml` now scrapes both sources and publishes the hub to Pages.

## [1.3.1] - 2026-11-04

### Reverted
- Google News image handling is back to the **1.2 behaviour**: a single hero image
  per item (`og:image`, with the download-candidate chain) and **no gallery /
  no per-link thumbnails**.
- Removed `--max-images` and `--fast`; `--max-candidates` is back to `4`
  (primary + up to 3 description links).
- HTML card layout restored (hero + DESCRIPTION + ARTICLE TEXT + plain related
  links). JSON no longer carries `images[]`, `images_count`, `image_files`,
  `gallery`, or `related_links[].image_*`.
- Test-suite trimmed to the 1.2 contract (53 tests).

## [1.3.0] - 2026-11-04

### Changed
- Image strategy back to **one primary image per link** (`og:image` of that page):
  the card shows a single hero image, and every related link keeps its own small
  thumbnail instead of a bulk gallery of inline images.
- `--max-candidates` defaults to `0` (= every link inside `<description>`) and
  `--max-images` (default 6) caps how many link-images are collected.
- HTML cards return to the previous layout (hero + description + text +
  related-link list with 34×34 thumbnails).

### Fixed
- Index suffix was truncated by the filename slug, so the 2nd/3rd image of the
  same item overwrote the previous file (`slug[:48]` → `slug[:60]`).
- Large images are downscaled to 900px / JPEG-q72 before base64 inlining
  (HTML went from 3.2 MB back to ~1.9 MB for 6 cards).

## [1.2.0] - 2026-11-04

### Added
- **Fallback chain for text + image**: when the primary publisher link yields no
  full body (`< 200` chars, e.g. 403/202 walls) or no image, the links inside
  Google's `<description>` are tried in order (`candidate_pages()`, dedupe by URL
  and host, `--max-candidates`, default 4).
- Image candidate collection: `og:image` → `og:image:secure_url` → `twitter:image`
  → JSON-LD `image` → lazy `<img data-src>`, with logo/avatar/1×1 filtering;
  `download_image_chain()` walks the list when a download fails.
- New fields: `text_source`, `text_from_related`, `image_source`,
  `image_candidates[]`, `tried[]`, `author`, `published_source`.
- Stealth-browser retry is now triggered by *short body* (not only empty) and
  merges partial HTTP results instead of replacing them.
- 7 new tests (51 total) covering the chain, dedupe, image candidates, meta
  extras and a mocked 403→fallback flow.

### Changed
- `--dynamic` is opt-in; the run logs a hint instead of silently launching a
  browser per failing item (a full run once took 10 min and crashed EPIPE).

## [1.1.0] - 2026-11-04

### Added
- **Google News RSS scraper** (`gnews/`, `gnews_scraper.py`, `pdx-gnews`):
  - reads the item `<title>` and opens the `<link>` redirect to the real publisher URL
    (data-n-a-id/ts/sg tokens + `batchexecute` `Fbv4je` RPC, no browser)
  - pulls the hero image (`og:image`) + article body text from the publisher page
  - parses Google's `<description>` into `related_links[]` (title + publisher) and
    resolves every related link to its publisher URL as well
  - flags: `--feed`, `--feed-file`, `--limit`, `--describe-only`, `--dynamic`,
    `--no-text`, `--no-images`, `--delay`, `--site`, `--min-items`
- `gnews.yml` workflow (cron every 3h, job summary, data commit, artifact).
- 16 new tests (44 total) covering feed parsing, description links, resolver token
  extraction, meta parsing and all renderers.

### Fixed
- Meta tags whose `content` contains an apostrophe were truncated
  (`og:description` of Gizmodo became `"We"`).
- `<font>` publisher label lives *outside* the `<a>` in Google's description,
  so publisher names came back empty.
- Article text extraction picked the first (sidebar) `<article>` element or a
  boilerplate paragraph; blocks are now scored by paragraph volume and
  nav/cookie/thumbnail-grid paragraphs are filtered.

## [1.0.0] - 2026-11-04

### Added
- `pdx` package: `parser` (pure), `render` (JSON/CSV/MD/HTML), `browser` (Scrapling stealth).
- CLI `perplexity_tech_scraper.py` (`pdx-scrape`) with `--category`, `--limit`,
  `--no-images`, `--max-age-hours`, `--min-items`, `--site`, `--from-json`.
- Hero image download + inline base64 embedding in the self-contained HTML report.
- 28 unit tests with a captured real `/rest/article` fixture (no browser needed).
- GitHub Actions: `ci.yml` (lint + matrix tests + live smoke), `scrape.yml`
  (cron every 6h, auto-commit data, optional GitHub Pages deploy),
  `release.yml` (build + GitHub release), `docker.yml` (GHCR publish).
- Composite action `actions/scrape`.
- Dockerfile (Playwright base image), docker-compose, Makefile, pre-commit hooks.

### Fixed
- Scrapling 0.5 does not support `>>` selector chaining — replaced with plain CSS.
- Metadata text lives inside `<span>`; `::text` misses it — switched to `*::text`.
- Naive `updated_datetime` caused `TypeError: can't subtract offset-naive and
  offset-aware datetimes` — timestamps are now coerced to UTC.
- Category links (`/discover/tech`) were captured as articles — filtered out.
- Article JSON is fetched with an in-page `fetch()` batch instead of 20 browser
  navigations (22s instead of minutes).
