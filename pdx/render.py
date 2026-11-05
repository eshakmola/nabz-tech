"""Render layer — turns parsed items into CSV / JSON / Markdown / HTML strings."""

from __future__ import annotations

import base64
import csv
import io
import json
import os
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from .parser import DEFAULT_CATEGORY

CSV_COLUMNS = [
    "position",
    "title",
    "summary",
    "sources_count",
    "read_time_min",
    "published",
    "published_iso",
    "url",
    "image",
    "report_chars",
]


def _esc(value: Any) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# --------------------------------------------------------------------------- #
# JSON / CSV
# --------------------------------------------------------------------------- #
def render_json(items: list[dict], source: str, scraped_at: str | None = None) -> str:
    payload = {
        "source": source,
        "scraped_at_utc": scraped_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(items),
        "items": items,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_csv(items: Iterable[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for item in items:
        row = {k: item.get(k) for k in CSV_COLUMNS}
        row["image"] = item.get("image_file") or item.get("image_url")
        writer.writerow(row)
    return "\ufeff" + buf.getvalue()  # BOM so Excel opens UTF-8 properly


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #
def render_markdown(
    items: list[dict],
    category: str = DEFAULT_CATEGORY,
    scraped_at: str | None = None,
    source: str = "https://www.perplexity.ai/discover",
) -> str:
    stamp = scraped_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Perplexity Discover — {category}",
        "",
        f"*{len(items)} articles · scraped {stamp}*",
        "",
        f"Source: <{source}>",
    ]
    for item in items:
        lines += ["", "---", "", f"## {item['position']}. {item['title']}", ""]
        meta = [
            item.get("published"),
            f"{item['read_time_min']} min read" if item.get("read_time_min") else None,
            f"{item['sources_count']} sources",
        ]
        lines.append("*" + " · ".join(m for m in meta if m) + "*")

        if item.get("image_file"):
            lines += ["", f"![{item['title']}]({item['image_file']})"]
        elif item.get("image_url"):
            lines += ["", f"![{item['title']}]({item['image_url']})"]

        lines += ["", f"**Summary:** {item.get('summary') or '—'}"]
        if item.get("bullet_summary"):
            lines += ["", item["bullet_summary"]]
        if item.get("report_sections"):
            lines.append("")
            lines.append("### Report")
            for section in item["report_sections"]:
                lines += ["", f"#### {section['heading'] or 'Section'}", "", section["body"]]
        if item.get("sources"):
            listed = " · ".join(
                f"[{s['domain'] or s['name'] or 'source'}]({s['url']})" for s in item["sources"][:8]
            )
            lines += ["", f"**Sources:** {listed}"]
        lines += ["", f"<{item['url']}>"]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# HTML (single self-contained file, images inlined as base64)
# --------------------------------------------------------------------------- #
_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#0a0e17;font-family:'Vazirmatn','Segoe UI',Tahoma,system-ui,sans-serif;color:#e8eefb}
.wrap{background-image:radial-gradient(900px 480px at 88% -8%,rgba(99,102,241,.20),transparent 62%)}
.wrap{max-width:1180px;margin:0 auto;padding:28px 18px 56px}
h1{color:#f2f6ff;font-size:26px;margin:0 0 4px}
.lede{color:#94a3b8;font-size:14px;margin:0 0 22px}
.summary p,.summary ul,details p,.title,.meta,.tag{unicode-bidi:plaintext;text-align:start}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:18px}
.grid>*{min-width:0}
body{overflow-x:hidden}
p,li,summary,details p,.title{overflow-wrap:anywhere;word-break:break-word}
.card{background:#111827;border:1px solid rgba(148,163,184,.18);border-radius:16px;padding:16px;
      box-shadow:0 1px 3px rgba(16,24,40,.06);display:flex;flex-direction:column;gap:12px}
.thumb{width:100%;height:210px;object-fit:cover;border-radius:12px;display:block;background:#0f172a}
.thumb-empty{height:210px;border-radius:12px;background:#0f172a;display:flex;
             align-items:center;justify-content:center;color:#64748b;font-size:13px}
.meta{font-size:12px;color:#94a3b8}
.title{margin:0;font-size:19px;line-height:1.5}
.summary{background:rgba(255,255,255,.04);border-right:3px solid #818cf8;border-radius:8px;padding:10px 12px}
.summary .label{font-size:11px;font-weight:700;letter-spacing:.6px;color:#a5b4fc}
.summary p{margin:6px 0 0;font-size:14px;line-height:1.8;color:#dbe4f4}
.summary ul{margin:8px 0 0;padding-inline-start:18px;font-size:13px;line-height:1.7;color:#c3cfe2}
.report .label{font-size:11px;font-weight:700;letter-spacing:.6px;color:#38bdf8}
details{margin-top:8px;border-top:1px dashed #e2e8f0;padding-top:8px}
summary{cursor:pointer;font-weight:600;font-size:14px;color:#e8eefb}
details p{margin:8px 0 0;font-size:14px;line-height:1.9;color:#b9c6dc}
.tags{margin-top:2px}
.tag{display:inline-block;font-size:12px;background:rgba(148,163,184,.12);border-radius:99px;
     padding:3px 10px;margin:3px 4px 0 0;color:#c3cfe2;text-decoration:none}
.tag:hover{background:rgba(148,163,184,.24);color:#fff}
.foot{margin-top:auto;padding-top:6px}
.foot a{font-size:13px;color:#a5b4fc;text-decoration:none}
"""


def _image_tag(item: dict, height: int = 210) -> str:
    path = item.get("image_file")
    if path and os.path.exists(path):
        with open(path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
        return (
            f'<img class="thumb" style="height:{height}px" alt="{_esc(item["title"])}" '
            f'src="data:{mime};base64,{b64}">'
        )
    if item.get("image_url"):
        return (
            f'<img class="thumb" style="height:{height}px" alt="{_esc(item["title"])}" '
            f'src="{_esc(item["image_url"])}" loading="lazy">'
        )
    return f'<div class="thumb-empty" style="height:{height}px">بدون تصویر</div>'


def _bullets(markdown: str | None) -> str:
    if not markdown:
        return ""
    rows = []
    for line in markdown.splitlines():
        text = line.strip().lstrip("-*").strip()
        if text:
            rows.append(f"<li>{_esc(text)}</li>")
    return f"<ul>{''.join(rows)}</ul>" if rows else ""


def render_html(
    items: list[dict],
    category: str = DEFAULT_CATEGORY,
    scraped_at: str | None = None,
    title: str | None = None,
) -> str:
    stamp = scraped_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    page_title = title or f"Perplexity Discover · {category}"

    cards = []
    for item in items:
        tags = "".join(
            f'<a class="tag" href="{_esc(src["url"])}">{_esc(src["domain"] or src["name"])}</a>'
            for src in (item.get("sources") or [])[:8]
        )
        sections = "".join(
            f"<details><summary>{_esc(sec['heading'] or 'بخش')}</summary>"
            f"<p>{_esc(sec['body'])}</p></details>"
            for sec in (item.get("report_sections") or [])
        )
        meta = " · ".join(
            m
            for m in (
                item.get("published"),
                f"{item['read_time_min']} min read" if item.get("read_time_min") else None,
                f"{item['sources_count']} sources",
            )
            if m
        )
        summary_html = (
            '<div class="summary"><div class="label">SUMMARY</div>'
            f'<p>{_esc(item["summary"])}</p>'
            f"{_bullets(item.get('bullet_summary'))}</div>"
            if (item.get("summary") or "").strip() or item.get("bullet_summary")
            else ""
        )
        cards.append(
            f"""
      <article class="card">
        {_image_tag(item)}
        <div class="meta">#{item["position"]} · {_esc(meta)}</div>
        <h3 class="title">{_esc(item["title"])}</h3>
        {summary_html}
        {f'<div class="report"><div class="label">REPORT</div>{sections}</div>' if sections else ""}
        {f'<div class="tags">{tags}</div>' if tags else ""}
        <div class="foot"><a href="{_esc(item["url"])}">خواندن در Perplexity ↗</a></div>
      </article>"""
        )

    return f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(page_title)}</title>
<style>{_CSS}</style>
</head>
<body>
  <div class="wrap">
    <h1>{_esc(page_title)}</h1>
      <div class="lede" style="font-size:11.5px;letter-spacing:2.2px;text-transform:uppercase;color:#7d8aa3;margin:2px 0 16px">نبض فناوری · نمای تک‌منبع</div>

    <p class="lede">{len(items)} خبر · استخراج‌شده در {stamp} · Scrapling 0.5 (StealthySession)</p>
    <div class="grid">{"".join(cards)}
    </div>
  </div>
</body>
</html>
"""
