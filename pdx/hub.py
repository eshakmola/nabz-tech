"""Unified news hub: one HTML page with a 3-way switch (All / Perplexity / G News).

Data and per-source exports stay **completely separate**:

    output/
    ├── perplexity_tech.json / .csv / .md     ← فقط پروکسپلکسیتی
    ├── perplexity_tech.html
    ├── images/…                              ← تصاویر پروکسپلکسیتی
    ├── gnews.json / .csv / .md               ← فقط گوگل‌نیوز
    ├── gnews.html
    └── images/…                              ← تصاویر گوگل‌نیوز
    site/
    └── index.html                            ← هاب (هر سه حالت، سوییچر + مرتب بر اساس تاریخ)

The hub embeds a *combined view model* (no shared storage, no merging of files)
and renders client-side filtering with plain JS — no external assets.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from typing import Any

from .render import _esc

SOURCES = ("all", "perplexity", "gnews")
INLINE_LIMIT = 140  # how many images get base64-inlined per source
HUB_TITLE = "نبض فناوری"  # default page name


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _parse_ts(value: Any) -> datetime | None:
    """Parse the many timestamp shapes the two scrapers emit."""
    if value in (None, ""):
        return None
    text = str(value).strip()
    if text.isdigit():
        number = int(text)
        return datetime.fromtimestamp(number / (1000 if number > 1e11 else 1), tz=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:  # Perplexity ships naive UTC timestamps
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _b64(path: str | None) -> str | None:
    """Encode an image for inlining (downscales big files when Pillow is available)."""
    if not path or not os.path.exists(path):
        return None
    try:
        size = os.path.getsize(path)
        if size <= 120_000:
            with open(path, "rb") as fh:
                return base64.b64encode(fh.read()).decode()
        try:
            import io as _io

            from PIL import Image

            with Image.open(path) as image:
                image = image.convert("RGB")
                if image.width > 900:
                    ratio = 900 / image.width
                    image = image.resize((900, int(image.height * ratio)))
                buffer = _io.BytesIO()
                image.save(buffer, "JPEG", quality=72, optimize=True)
            return base64.b64encode(buffer.getvalue()).decode()
        except Exception:
            with open(path, "rb") as fh:
                return base64.b64encode(fh.read()).decode()
    except Exception:
        return None


def _resolve_image(image_file: str | None, base_dir: str, kind: str) -> str | None:
    """پیدا کردن فایل تصویر، مستقل از اینکه مسیر نسبی/مطلق/جابه‌جاشده باشد."""
    if not image_file:
        return None
    name = os.path.basename(image_file)
    candidates = [
        image_file,
        os.path.join(base_dir, image_file),
        os.path.join(base_dir, name),
        os.path.join(base_dir, "images" if kind == "perplexity" else "gnews-images", name),
        os.path.join(os.getcwd(), image_file),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def _mime(path: str | None) -> str:
    lowered = (path or "").lower()
    if lowered.endswith(".png"):
        return "image/png"
    if lowered.endswith(".webp"):
        return "image/webp"
    if lowered.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


# --------------------------------------------------------------------------- #
# normalising each source into one view model (files stay untouched)
# --------------------------------------------------------------------------- #
def perplexity_entries(
    data: dict[str, Any], base_dir: str = "", inline_limit: int = INLINE_LIMIT
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for index, item in enumerate(data.get("items") or []):
        stamp = _parse_ts(item.get("published_iso"))
        image_path = _resolve_image(item.get("image_file"), base_dir, "perplexity")
        inline = _b64(image_path) if index < inline_limit else None
        entries.append(
            {
                "source": "perplexity",
                "source_label": "Perplexity",
                "title": item.get("title"),
                "url": item.get("url"),
                "publisher": "Perplexity · " + (item.get("category") or "tech"),
                "ts": stamp.isoformat() if stamp else None,
                "age": item.get("published"),
                "summary": item.get("summary"),
                "bullets": item.get("bullet_summary"),
                "sections": item.get("report_sections") or [],
                "text": "",
                "sources_count": item.get("sources_count") or 0,
                "sources": (item.get("sources") or [])[:6],
                "image": (
                    f"data:{_mime(image_path)};base64,{inline}" if inline else item.get("image_url")
                ),
                "read_time": item.get("read_time_min"),
            }
        )
    return entries


def gnews_entries(
    data: dict[str, Any], base_dir: str = "", inline_limit: int = INLINE_LIMIT
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for index, item in enumerate(data.get("items") or []):
        stamp = _parse_ts(item.get("published_iso"))
        image_path = _resolve_image(item.get("image_file"), base_dir, "gnews")
        inline = _b64(image_path) if index < inline_limit else None
        entries.append(
            {
                "source": "gnews",
                "source_label": "G News",
                "title": item.get("title"),
                "url": item.get("url"),
                "publisher": item.get("publisher") or "",
                "ts": stamp.isoformat() if stamp else None,
                "age": item.get("published"),
                "summary": item.get("description"),
                "bullets": None,
                "sections": [],
                "text": item.get("text") or "",
                "sources_count": 0,
                "sources": [
                    {
                        "domain": link.get("publisher"),
                        "url": link.get("resolved_url") or link["url"],
                    }
                    for link in (item.get("related_links") or [])[:6]
                ],
                "image": (
                    f"data:{_mime(image_path)};base64,{inline}" if inline else item.get("image_url")
                ),
                "read_time": None,
            }
        )
    return entries


def load_sources(
    perplexity_json: str | None,
    gnews_json: str | None,
    inline_limit: int = INLINE_LIMIT,
) -> list[dict[str, Any]]:
    """Build one combined, date-sorted view model from the two independent files."""
    entries: list[dict[str, Any]] = []
    if perplexity_json and os.path.exists(perplexity_json):
        with open(perplexity_json, encoding="utf-8") as fh:
            data = json.load(fh)
        entries += perplexity_entries(data, os.path.dirname(perplexity_json), inline_limit)
    if gnews_json and os.path.exists(gnews_json):
        with open(gnews_json, encoding="utf-8") as fh:
            data = json.load(fh)
        entries += gnews_entries(data, os.path.dirname(gnews_json), inline_limit)
    entries.sort(key=lambda entry: entry.get("ts") or "", reverse=True)
    for index, entry in enumerate(entries, start=1):
        entry["order"] = index
    return entries


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #
_CSS = r"""
:root{
  --bg:#06080f; --bg2:#0b1020;
  --ink:#e8eefb; --ink2:#aab6cc; --muted:#7d8aa3;
  --line:rgba(148,163,184,.16); --line2:rgba(148,163,184,.09);
  --card:linear-gradient(180deg,rgba(255,255,255,.055),rgba(255,255,255,.022));
  --pdx:#8b8cf9; --pdx2:#4f46e5; --gn:#34d399; --gn2:#059669;
  --radius:20px;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  overflow-x:hidden;margin:0;min-height:100vh;background:var(--bg);color:var(--ink);
  font-family:"Vazirmatn","IRANSansX","IRANYekan","Segoe UI",Tahoma,system-ui,sans-serif;
  font-feature-settings:"ss01","cv01";-webkit-font-smoothing:antialiased;
  background-image:
    radial-gradient(900px 520px at 88% -8%,rgba(99,102,241,.22),transparent 62%),
    radial-gradient(760px 460px at 6% 4%,rgba(16,185,129,.16),transparent 60%),
    linear-gradient(180deg,#06080f,#080b14 58%,#06080f);
  background-attachment:fixed;
}
::selection{background:rgba(129,140,248,.35);color:#fff}
.halo{position:fixed;border-radius:50%;filter:blur(90px);pointer-events:none;z-index:0;opacity:.5}
.halo.a{width:420px;height:420px;background:rgba(99,102,241,.30);top:-160px;inset-inline-end:-120px}
.halo.b{width:380px;height:380px;background:rgba(16,185,129,.22);bottom:-180px;inset-inline-start:-140px}
.wrap{position:relative;z-index:1;max-width:1260px;margin:0 auto;padding:34px 20px 72px}

/* ---------------- header ---------------- */
.top{display:flex;flex-direction:column;align-items:center;text-align:center;gap:16px;padding:8px 0 4px}
.brand{display:flex;align-items:center;gap:14px}
.mark{
  width:48px;height:48px;border-radius:15px;display:grid;place-items:center;flex:0 0 auto;
  background:linear-gradient(145deg,rgba(99,102,241,.95),rgba(16,185,129,.85));
  box-shadow:0 10px 30px -8px rgba(99,102,241,.75),inset 0 1px 0 rgba(255,255,255,.35);
}
.mark svg{width:26px;height:26px;display:block}
h1{
  margin:0;font-size:30px;line-height:1.2;letter-spacing:-.4px;font-weight:800;
  background:linear-gradient(120deg,#ffffff 12%,#c7d2fe 52%,#a7f3d0 96%);
  -webkit-background-clip:text;background-clip:text;color:transparent;
}
.brand .sub{margin:3px 0 0;font-size:11.5px;letter-spacing:2.4px;color:var(--muted);text-transform:uppercase}
.lede{max-width:640px;margin:0;color:var(--ink2);font-size:13.5px;line-height:2}

/* ---------------- switch (centered, sticky) ---------------- */
.dock{
  position:sticky;top:0;z-index:20;display:flex;justify-content:center;width:100%;
  padding:14px 0 12px;margin-top:2px;
  background:transparent;
}
.dock::before{content:"";position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(180deg,rgba(6,8,15,.96) 42%,rgba(6,8,15,.72) 76%,transparent)}
.switch{
  position:relative;display:inline-flex;gap:2px;padding:5px;border-radius:999px;
  background:rgba(12,16,28,.86);border:1px solid var(--line);
  backdrop-filter:blur(16px) saturate(140%);-webkit-backdrop-filter:blur(16px) saturate(140%);
  box-shadow:0 18px 40px -20px rgba(0,0,0,.95),inset 0 1px 0 rgba(255,255,255,.06);
}
.switch .pill{
  position:absolute;top:5px;left:0;height:calc(100% - 10px);border-radius:999px;z-index:0;
  background:linear-gradient(135deg,rgba(99,102,241,.92),rgba(79,70,229,.86));
  box-shadow:0 8px 22px -10px rgba(99,102,241,.95),inset 0 1px 0 rgba(255,255,255,.28);
  transition:transform .34s cubic-bezier(.34,1.2,.4,1),width .34s cubic-bezier(.34,1.2,.4,1),background .3s;
}
.switch button{
  position:relative;z-index:1;border:0;background:transparent;font:inherit;font-size:13.5px;
  font-weight:600;color:#9fadc6;padding:10px 20px;border-radius:999px;cursor:pointer;
  display:inline-flex;align-items:center;gap:8px;transition:color .25s,opacity .25s;
  -webkit-tap-highlight-color:transparent;
}
.switch button:hover{color:#dfe7f6}
.switch button[aria-selected="true"]{color:#fff}
.switch .n{
  font-size:11px;font-weight:700;min-width:22px;text-align:center;
  background:rgba(148,163,184,.14);color:#c2cde0;border-radius:99px;padding:2px 7px;
  transition:background .25s,color .25s;
}
.switch button[aria-selected="true"] .n{background:rgba(255,255,255,.24);color:#fff}
.switch button:focus-visible{outline:2px solid #a5b4fc;outline-offset:3px}

/* ---------------- stats ---------------- */
.strip{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:10px;
  color:var(--muted);font-size:12px;margin:2px 0 4px}
.strip .dot{width:6px;height:6px;border-radius:50%;background:var(--gn);box-shadow:0 0 0 4px rgba(52,211,153,.14)}
.strip .sep{opacity:.4}
#stats:empty{display:none}

/* ---------------- days & grid ---------------- */
.stream{display:block;margin-top:14px}
.day{display:flex;align-items:center;gap:14px;margin:34px 2px 14px}
.day:first-child{margin-top:10px}
.day h2{
  margin:0;font-size:12.5px;font-weight:700;letter-spacing:.3px;color:#cdd8ea;
  padding:6px 14px;border-radius:99px;background:rgba(255,255,255,.045);
  border:1px solid var(--line2);white-space:nowrap;
}
.day .line{flex:1;height:1px;background:linear-gradient(90deg,transparent,var(--line),transparent)}
.day .cnt{font-size:11px;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(322px,1fr));gap:18px}
.grid>*{min-width:0}

.card{
  position:relative;display:flex;flex-direction:column;overflow:hidden;
  background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
  backdrop-filter:blur(9px);-webkit-backdrop-filter:blur(9px);
  box-shadow:0 18px 40px -28px rgba(0,0,0,.95),inset 0 1px 0 rgba(255,255,255,.045);
  transition:transform .3s cubic-bezier(.2,.7,.3,1),border-color .3s,box-shadow .3s;
  animation:rise .5s cubic-bezier(.2,.7,.3,1) both;animation-delay:calc(var(--i,0) * 32ms);
}
.card::before{
  content:"";position:absolute;inset:0 0 auto;height:2px;
  background:linear-gradient(90deg,var(--pdx2),var(--pdx),transparent);
  opacity:.9;
}
.card.gnews::before{background:linear-gradient(90deg,var(--gn2),var(--gn),transparent)}
.card:hover{transform:translateY(-4px);border-color:rgba(148,163,184,.34);
  box-shadow:0 30px 60px -30px rgba(0,0,0,1),0 0 0 1px rgba(148,163,184,.06)}
.card.gnews:hover{box-shadow:0 30px 60px -30px rgba(0,0,0,1),0 0 34px -16px rgba(52,211,153,.45)}
.card.perplexity:hover{box-shadow:0 30px 60px -30px rgba(0,0,0,1),0 0 34px -16px rgba(99,102,241,.5)}
@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}

.shot{position:relative;aspect-ratio:16/9;background:#0d1220;overflow:hidden;flex:0 0 auto}
.shot img{width:100%;height:100%;object-fit:cover;display:block;
  transition:transform .55s cubic-bezier(.2,.7,.3,1),filter .4s;filter:saturate(.94) contrast(1.03)}
.card:hover .shot img{transform:scale(1.045)}
.shot::after{content:"";position:absolute;inset:auto 0 0;height:58%;
  background:linear-gradient(180deg,transparent,rgba(6,8,15,.72))}
.shot.plain{display:grid;place-items:center;
  background:radial-gradient(120% 120% at 20% 0%,rgba(99,102,241,.32),transparent 60%),
             radial-gradient(110% 110% at 90% 90%,rgba(16,185,129,.26),transparent 62%),#0b1020}
.shot.plain span{color:#8fa0bd;font-size:12px;letter-spacing:.4px;z-index:1}
.badge{
  position:absolute;top:10px;inset-inline-start:10px;z-index:2;font-size:10px;font-weight:800;
  letter-spacing:.7px;padding:4px 10px;border-radius:99px;backdrop-filter:blur(6px);
}
.badge.perplexity{background:rgba(99,102,241,.9);color:#fff;box-shadow:0 6px 18px -8px rgba(99,102,241,.9)}
.badge.gnews{background:rgba(5,150,105,.9);color:#fff;box-shadow:0 6px 18px -8px rgba(5,150,105,.9)}

.body{display:flex;flex-direction:column;gap:10px;padding:14px 16px 16px}
.row{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;font-size:11.5px;color:var(--muted)}
.row .pub{color:#b9c6dc;font-weight:600}
.row .sep{opacity:.45}
.title{margin:0;font-size:17.5px;line-height:1.62;font-weight:700;letter-spacing:-.2px;color:#f2f6ff}
.title a{color:inherit;text-decoration:none}
.title a:hover{text-decoration:underline;text-decoration-color:rgba(148,163,184,.5);text-underline-offset:4px}

.block{border-radius:12px;padding:10px 12px;font-size:13px;line-height:1.95;color:#d6e0f0;
  background:rgba(255,255,255,.035);border:1px solid var(--line2);border-inline-start:3px solid var(--pdx)}
.card.gnews .block{border-inline-start-color:var(--gn)}
.block .label{display:block;font-size:10px;font-weight:800;letter-spacing:1.1px;
  color:var(--pdx);margin-bottom:5px}
.card.gnews .block .label{color:var(--gn)}
.block p{margin:0;text-align:start}
.title,.block,.block p,.block li,details p,.tag,.row,summary{overflow-wrap:anywhere;word-break:break-word}
/* جهت خودکار برای متن‌های لاتین داخل چیدمان راست‌به‌چپ */
.block p,.block li,details p,.title,.tag,.row,.foot a,summary{unicode-bidi:plaintext}
.block ul{margin:7px 0 0;padding-inline-start:16px;font-size:12.5px;line-height:1.9;color:#c3cfe2}
.block ul li{margin:2px 0}
.block strong{color:#fff;font-weight:700}
.block code{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;background:rgba(148,163,184,.16);
  border-radius:5px;padding:1px 5px;direction:ltr;display:inline-block}
.strip .stamp{direction:ltr;unicode-bidi:embed;color:#65728b}
details{border-radius:10px;border:1px solid var(--line2);background:rgba(255,255,255,.022);padding:0 12px}
details+details{margin-top:6px}
summary{cursor:pointer;font-size:12.5px;font-weight:600;color:#dbe4f4;padding:9px 0;
  list-style:none;display:flex;align-items:center;gap:8px}
summary::-webkit-details-marker{display:none}
summary::before{content:"+";font-size:14px;line-height:1;color:var(--muted);transition:transform .25s}
details[open] summary::before{content:"−"}
details p{margin:0 0 10px;font-size:12.8px;line-height:1.95;color:#b9c6dc}
.tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:2px}
.tag{font-size:11px;color:#b8c6de;text-decoration:none;padding:3px 10px;border-radius:99px;
  background:rgba(148,163,184,.10);border:1px solid var(--line2);transition:.2s}
.tag:hover{background:rgba(148,163,184,.2);color:#fff}
.foot{margin-top:auto;padding-top:6px;border-top:1px dashed var(--line2);display:flex;justify-content:space-between;align-items:center;gap:10px}
.foot a{font-size:12.5px;font-weight:600;color:#a5b4fc;text-decoration:none;transition:.2s}
.card.gnews .foot a{color:#6ee7b7}
.foot a:hover{color:#fff}
.foot .ord{font-size:10.5px;color:#5d6b85}
.empty{padding:56px 20px;text-align:center;color:var(--muted);font-size:13.5px;
  border:1px dashed var(--line);border-radius:var(--radius);background:rgba(255,255,255,.02)}
footer.page{margin-top:44px;padding-top:18px;border-top:1px solid var(--line2);
  display:flex;flex-wrap:wrap;gap:8px;justify-content:center;color:#65728b;font-size:11.5px;text-align:center}

@media (max-width:560px){
  h1{font-size:24px}
  .wrap{padding:22px 14px 56px}
  .dock{padding:10px 0}
  .switch{width:100%;justify-content:space-between}
  .switch button{padding:9px 12px;font-size:12.5px;flex:1;justify-content:center}
  .grid{grid-template-columns:1fr}
}
"""


_JS = r"""
const DATA = window.__HUB__ || [];
const grid = document.getElementById('grid');
const stats = document.getElementById('stats');
const switchEl = document.querySelector('.switch');
const pill = switchEl ? switchEl.querySelector('.pill') : null;
const buttons = Array.from(document.querySelectorAll('.switch button'));

function esc(s){
  return (s === null || s === undefined ? '' : s.toString())
    .replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}
/* مارک‌داون ساده: **پررنگ** و `کد` — بعد از escape، پس امن است */
function md(s){
  return esc(s)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\u0060([^\u0060]+)\u0060/g, '<code>$1</code>');
}
/* تبدیل تاریخ میلادی به شمسی (بدون وابستگی به Intl) */
const J_MONTHS = ['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور','مهر','آبان','آذر','دی','بهمن','اسفند'];
const J_DAYS = ['یکشنبه','دوشنبه','سه‌شنبه','چهارشنبه','پنجشنبه','جمعه','شنبه'];
const FA = ['۰','۱','۲','۳','۴','۵','۶','۷','۸','۹'];
function fa(n){ return String(n).replace(/\d/g, d => FA[+d]); }
function jalali(d){
  const gy = d.getFullYear(), gm = d.getMonth() + 1, gd = d.getDate();
  const g_d_m = [0,31,59,90,120,151,181,212,243,273,304,334];
  let jy = (gy <= 1600) ? 0 : 979;
  const gy2 = (gy <= 1600) ? gy - 621 : gy - 1600;
  const gm2 = gm > 2 ? 1 : 0;
  let days = (365 * gy2) + Math.floor((gy2 + 3) / 4) - Math.floor((gy2 + 99) / 100)
    + Math.floor((gy2 + 399) / 400) - 80 + gd + g_d_m[gm - 1] + (gy2 % 4 === 0 && gm > 2 ? 1 : 0);
  jy += 33 * Math.floor(days / 12053); days %= 12053;
  jy += 4 * Math.floor(days / 1461); days %= 1461;
  if(days > 365){ jy += Math.floor((days - 1) / 365); days = (days - 1) % 365; }
  const jm = (days < 186) ? 1 + Math.floor(days / 31) : 7 + Math.floor((days - 186) / 30);
  const jd = 1 + ((days < 186) ? (days % 31) : ((days - 186) % 30));
  return {y: jy, m: jm, d: jd};
}
function safeDate(ts){ const d = new Date(ts); return isNaN(d.getTime()) ? null : d; }
function fmt(ts){
  const d = safeDate(ts);
  if(!d) return '';
  const p = n => (n < 10 ? '0' : '') + n;
  return fa(p(d.getHours()) + ':' + p(d.getMinutes()));
}
function dayKey(ts){
  const d = safeDate(ts);
  if(!d) return 'بدون تاریخ';
  const j = jalali(d);
  return J_DAYS[d.getDay()] + ' ' + fa(j.d) + ' ' + J_MONTHS[j.m - 1] + ' ' + fa(j.y);
}
function movePill(btn){
  if(!pill || !btn) return;
  const pad = 5;
  pill.style.width = btn.offsetWidth + 'px';
  pill.style.transform = 'translateX(' + (btn.offsetLeft - pad) + 'px)';
}
function block(label, inner, cls){
  return `<div class="block ${cls || ''}"><span class="label">${label}</span>${inner}</div>`;
}
function card(e, i){
  const shot = e.image
    ? `<img class="thumb" loading="lazy" decoding="async" alt="${esc(e.title)}" src="${e.image}">`
    : `<span>بدون تصویر</span>`;
  const bullets = e.bullets
    ? `<ul>${e.bullets.split('\n').filter(Boolean).map(l => `<li>${md(l.replace(/^[-*]\s*/, ''))}</li>`).join('')}</ul>`
    : '';
  const sections = (e.sections || []).slice(0, 4)
    .map(s => `<details><summary>${esc(s.heading || 'بخش')}</summary><p>${md(s.body)}</p></details>`).join('');
  const paras = e.text ? e.text.split('\n\n').filter(Boolean) : [];
  const articleText = paras.slice(0, 3).map(p => `<p>${md(p)}</p>`).join('')
    + (paras.length > 3 ? `<details><summary>ادامه‌ی متن</summary>${paras.slice(3).map(p => `<p>${md(p)}</p>`).join('')}</details>` : '');
  const tags = (e.sources || []).map(s => `<a class="tag" href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.domain || 'منبع')}</a>`).join('');
  const meta = [
    e.publisher ? `<span class="pub">${esc(e.publisher)}</span>` : '',
    fmt(e.ts) ? `<span>${esc(fmt(e.ts))}</span>` : '',
    e.read_time ? `<span>${e.read_time} دقیقه</span>` : '',
    e.sources_count ? `<span>${e.sources_count} منبع</span>` : ''
  ].filter(Boolean).join('<span class="sep">·</span>');

  return `<article class="card ${e.source}" style="--i:${i % 12}">
    <div class="shot ${e.image ? '' : 'plain'}">${shot}<span class="badge ${e.source}">${esc(e.source_label)}</span></div>
    <div class="body">
      <div class="row">${meta}</div>
      <h3 class="title"><a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.title)}</a></h3>
      ${(e.summary || '').trim() ? block('خلاصه', `<p>${md(e.summary)}</p>${bullets}`) : ''}
      ${sections ? block('گزارش', sections) : ''}
      ${articleText ? block('متن خبر', articleText) : ''}
      ${tags ? `<div class="tags">${tags}</div>` : ''}
      <div class="foot"><a href="${esc(e.url)}" target="_blank" rel="noopener">خواندن اصل خبر ↗</a><span class="ord">#${e.order || ''}</span></div>
    </div>
  </article>`;
}
function render(which){
  const items = DATA.filter(e => which === 'all' || e.source === which);
  if(!items.length){
    grid.innerHTML = '<div class="empty">برای این منبع هنوز خبری ثبت نشده است.</div>';
    stats.textContent = '';
    return;
  }
  let html = '', currentDay = null, opened = false, i = 0;
  items.forEach(e => {
    const key = dayKey(e.ts);
    if(key !== currentDay){
      if(opened) html += '</div>';
      currentDay = key;
      const dayCount = items.filter(x => dayKey(x.ts) === key).length;
      html += `<div class="day"><h2>${esc(key)}</h2><span class="cnt">${dayCount} خبر</span><div class="line"></div></div><div class="grid">`;
      opened = true;
    }
    html += card(e, i++);
  });
  if(opened) html += '</div>';
  grid.innerHTML = html;

  const p = items.filter(e => e.source === 'perplexity').length;
  const g = items.filter(e => e.source === 'gnews').length;
  stats.textContent = `${items.length} خبر · Perplexity ${p} · G News ${g} · مرتب بر اساس تاریخ انتشار`;
}
function activate(which, push){
  const btn = buttons.find(b => b.dataset.src === which) || buttons[0];
  buttons.forEach(b => b.setAttribute('aria-selected', b === btn ? 'true' : 'false'));
  movePill(btn);
  render(btn.dataset.src);
  if(push !== false){
    const hash = btn.dataset.src === 'all' ? '' : btn.dataset.src;
    if((location.hash || '').replace('#', '') !== (hash || '')){
      try { history.replaceState(null, '', hash || location.pathname); }
      catch(e){ try { location.hash = hash; } catch(_e){} }   /* file:// هم کار کند */
    }
  }
}
buttons.forEach(btn => btn.addEventListener('click', () => activate(btn.dataset.src)));
switchEl && switchEl.addEventListener('keydown', ev => {
  if(ev.key !== 'ArrowLeft' && ev.key !== 'ArrowRight') return;
  const idx = buttons.findIndex(b => b.getAttribute('aria-selected') === 'true');
  const next = (idx + (ev.key === 'ArrowLeft' ? 1 : -1) + buttons.length) % buttons.length;
  activate(buttons[next].dataset.src);
  buttons[next].focus();
});
window.addEventListener('resize', () => movePill(buttons.find(b => b.getAttribute('aria-selected') === 'true')));
const initial = (location.hash || '').replace('#', '');
activate(['all','perplexity','gnews'].includes(initial) ? initial : 'all', false);
"""


def render_hub(
    entries: list[dict[str, Any]],
    title: str = "نبض فناوری",
    scraped_at: str | None = None,
) -> str:
    stamp = scraped_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    counts = {
        "all": len(entries),
        "perplexity": sum(1 for e in entries if e["source"] == "perplexity"),
        "gnews": sum(1 for e in entries if e["source"] == "gnews"),
    }
    labels = {"all": "All", "perplexity": "Perplexity", "gnews": "G News"}
    buttons = "".join(
        f'<button type="button" data-src="{key}" aria-selected="{"true" if key == "all" else "false"}">'
        f'{labels[key]}<span class="n">{counts[key]}</span></button>'
        for key in SOURCES
    )
    # JSON امن برای درون <script>: هیچ < یا > خامی باقی نمی‌ماند
    payload = (
        json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    mark = (
        '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M2 12h4l2.5-7 3.5 14 3-9 2 2h5"/></svg>'
    )

    return f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#06080f">
<meta name="generator" content="pdx-hub">
<title>{_esc(title)} · Perplexity + G News</title>
<style>{_CSS}</style>
</head>
<body>
  <div class="halo a" aria-hidden="true"></div>
  <div class="halo b" aria-hidden="true"></div>
  <div class="wrap">
    <header class="top">
      <div class="brand">
        <span class="mark">{mark}</span>
        <div>
          <h1>{_esc(title)}</h1>
          <p class="sub">Perplexity · Google News</p>
        </div>
      </div>
      <p class="lede">یک صفحه، دو منبع، مرتب بر اساس تاریخ انتشار — داده و JSON/CSV هر منبع جدا و دست‌نخورده می‌ماند.</p>
    </header>
    <div class="dock">
      <div class="switch" role="tablist" aria-label="انتخاب منبع"><span class="pill" aria-hidden="true"></span>{buttons}</div>
    </div>
    <div class="strip"><span class="dot" aria-hidden="true"></span><span id="stats"></span><span class="sep">·</span><span class="stamp">{_esc(stamp)}</span></div>
    <main id="grid" class="stream"></main>
    <footer class="page">
      <span>ساخته‌شده با pdx-hub</span><span>·</span>
      <span>تصاویر درون‌خط (بدون فایل خارجی)</span><span>·</span>
      <span>هر منبع داده‌ی جداگانه‌ی خودش را دارد</span>
    </footer>
  </div>
  <script>window.__HUB__ = {payload};</script>
  <script>{_JS}</script>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
def build_hub(
    perplexity_json: str | None,
    gnews_json: str | None,
    out_html: str,
    inline_limit: int = INLINE_LIMIT,
    title: str | None = None,
) -> dict[str, Any]:
    """Write the hub HTML (and its archive copy when ``out_html`` lives in a site dir)."""
    entries = load_sources(perplexity_json, gnews_json, inline_limit=inline_limit)
    html = render_hub(entries, title=title or HUB_TITLE)
    os.makedirs(os.path.dirname(out_html) or ".", exist_ok=True)
    with open(out_html, "w", encoding="utf-8") as fh:
        fh.write(html)
    return {
        "path": out_html,
        "count": len(entries),
        "perplexity": sum(1 for e in entries if e["source"] == "perplexity"),
        "gnews": sum(1 for e in entries if e["source"] == "gnews"),
    }
