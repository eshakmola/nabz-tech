/**
 * nabz-worker — «نبض فناوری» API + web on Cloudflare Workers
 *
 * Routes
 *   GET  /                → the web UI (same look as the GitHub Pages hub)
 *   GET  /health          → liveness probe
 *   GET  /api             → index of endpoints
 *   GET  /api/news        → combined, date-sorted feed      (All / Perplexity / G News)
 *   GET  /api/perplexity  → Perplexity items only
 *   GET  /api/gnews       → Google News items only
 *   GET  /api/hub         → prebuilt page payload (items + counts + generated_at)
 *   GET  /api/item/:id    → one item
 *   GET  /api/rss         → RSS 2.0 of the combined feed
 *
 * Query params (all endpoints): source, q, limit, offset, since, lang, format
 *
 * Caching: the upstream JSON is stored in KV (`HUB` binding) by the GitHub Action;
 * if KV is empty or unreachable the worker falls back to raw.githubusercontent.com
 * (so it works even before KV is wired up).
 */

const DEFAULTS = {
  repo: 'eshakmola/nabz-tech',
  branch: 'main',
  ttl: 900,
};

const CORS = {
  'access-control-allow-origin': '*',
  'access-control-allow-methods': 'GET,HEAD,OPTIONS',
  'access-control-allow-headers': 'content-type',
};

/* ------------------------------------------------------------------ utils */
const json = (data, status = 200, extra = {}) =>
  new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': `public, max-age=60, s-maxage=${DEFAULTS.ttl}`,
      ...CORS,
      ...extra,
    },
  });

const bad = (message, status = 400) => json({ ok: false, error: message }, status);

const esc = (s = '') =>
  String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const num = (v, fallback) => {
  const n = parseInt(v, 10);
  return Number.isFinite(n) && n >= 0 ? n : fallback;
};

/* -------------------------------------------------------- upstream loading */
async function fetchSource(env, source) {
  const repo = env.GITHUB_REPO || DEFAULTS.repo;
  const branch = env.GITHUB_BRANCH || DEFAULTS.branch;
  const file = source === 'perplexity' ? 'perplexity_tech.json' : 'gnews.json';

  // 1) KV cache (filled by the scheduled GitHub Action)
  if (env.HUB && typeof env.HUB.get === 'function') {
    try {
      const raw = await env.HUB.get(`hub:${source}`, 'json');
      if (raw && Array.isArray(raw)) return { items: raw, via: 'kv' };
    } catch (e) {
      /* fall through to raw */
    }
  }

  // 2) raw.githubusercontent.com
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 12000);
  try {
    const res = await fetch(`https://raw.githubusercontent.com/${repo}/${branch}/data/${file}`, {
      signal: ctrl.signal,
      headers: { 'user-agent': 'nabz-worker' },
      cf: { cacheEverything: true, cacheTtl: 300 },
    });
    if (!res.ok) return { items: [], via: 'raw', error: `upstream ${res.status}` };
    const doc = await res.json();
    const items = normalize(Array.isArray(doc) ? doc : doc.items || [], source);
    return { items, via: 'raw' };
  } catch (e) {
    return { items: [], via: 'raw', error: String(e && e.message ? e.message : e) };
  } finally {
    clearTimeout(timer);
  }
}

const dayKey = (iso) => (iso ? String(iso).slice(0, 10) : '');

const J_MONTHS = ['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور','مهر','آبان','آذر','دی','بهمن','اسفند'];
const J_DAYS = ['یکشنبه','دوشنبه','سه‌شنبه','چهارشنبه','پنجشنبه','جمعه','شنبه'];
const FA = ['۰','۱','۲','۳','۴','۵','۶','۷','۸','۹'];
const fa = (n) => String(n).replace(/\d/g, (d) => FA[+d]);

function jalali(d) {
  const gy = d.getUTCFullYear(), gm = d.getUTCMonth() + 1, gd = d.getUTCDate();
  const gdm = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
  let jy = gy <= 1600 ? 0 : 979;
  const gy2 = gy <= 1600 ? gy - 621 : gy - 1600;
  let days =
    365 * gy2 + Math.floor((gy2 + 3) / 4) - Math.floor((gy2 + 99) / 100) +
    Math.floor((gy2 + 399) / 400) - 80 + gd + gdm[gm - 1] + (gy2 % 4 === 0 && gm > 2 ? 1 : 0);
  jy += 33 * Math.floor(days / 12053); days %= 12053;
  jy += 4 * Math.floor(days / 1461); days %= 1461;
  if (days > 365) { jy += Math.floor((days - 1) / 365); days = (days - 1) % 365; }
  const jm = days < 186 ? 1 + Math.floor(days / 31) : 7 + Math.floor((days - 186) / 30);
  const jd = 1 + (days < 186 ? days % 31 : (days - 186) % 30);
  return { jy, jm, jd };
}

function dayLabel(iso) {
  if (!iso) return 'بدون تاریخ';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return 'بدون تاریخ';
  const j = jalali(d);
  return J_DAYS[d.getUTCDay()] + ' ' + fa(j.jd) + ' ' + J_MONTHS[j.jm - 1] + ' ' + fa(j.jy);
}

function normalize(items, source) {
  return (items || []).map((it) => {
    const ts = it.ts || it.published_iso || it.published || null;
    const title = String(it.title || '').trim();
    const id = it.id || slug(`${source}-${ts || ''}-${title}`);
    return {
      id,
      source: it.source && it.source !== 'perplexity' && it.source !== 'gnews' ? source : it.source || source,
      source_label: it.source_label || (source === 'perplexity' ? 'Perplexity' : 'G News'),
      title,
      url: it.url || '',
      publisher: it.publisher || (source === 'perplexity' ? 'Perplexity' : ''),
      ts,
      summary: it.summary || '',
      bullets: it.bullets || '',
      sections: it.sections || [],
      text: it.text || '',
      sources_count: it.sources_count || 0,
      sources: it.sources || [],
      image: it.image_cdn || it.image || it.image_url || null,
      read_time: it.read_time || null,
      lang: it.lang || 'en',
    };
  });
}

function slug(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  return 'i' + (h >>> 0).toString(36);
}


/* ------------------------------------------------- edge-side Google News ingest */
const GN_FEED =
  'https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-US&gl=US&ceid=US:en';
const BATCH_URL = 'https://news.google.com/_/DotsSplashUi/data/batchexecute';

const stripTags = (html = '') =>
  String(html).replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
const unescapeHtml = (t = '') =>
  String(t)
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&');

function parseFeed(xml) {
  const items = [];
  const blocks = String(xml).match(/<item>([\s\S]*?)<\/item>/g) || [];
  for (const block of blocks) {
    const pick = (tag) => {
      const m = block.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`));
      return m ? m[1] : '';
    };
    const rawTitle = unescapeHtml(stripTags(pick('title')));
    const link = stripTags(pick('link'));
    const pubDate = stripTags(pick('pubDate'));
    if (!rawTitle || !link) continue;
    // "Headline - Publisher" → title + publisher
    const cut = rawTitle.lastIndexOf(' - ');
    const title = cut > 20 ? rawTitle.slice(0, cut) : rawTitle;
    const publisher = cut > 20 ? rawTitle.slice(cut + 3) : '';
    const stamp = Date.parse(pubDate);
    items.push({
      title,
      publisher,
      google_url: link,
      ts: Number.isFinite(stamp) ? new Date(stamp).toISOString() : null,
      description_html: unescapeHtml(pick('description')),
    });
  }
  return items;
}

/** Google News CBM… → publisher URL (splash page tokens + batchexecute RPC). */
async function resolveGoogleUrl(googleUrl, timeoutMs = 9000) {
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    const page = await fetch(googleUrl, {
      signal: ctrl.signal,
      headers: { 'user-agent': 'Mozilla/5.0 (compatible; nabz-worker/1.0)' },
      redirect: 'follow',
    }).then((r) => r.text());
    clearTimeout(timer);
    const aid = (page.match(/data-n-a-id="([^"]+)"/) || [])[1];
    const ts = (page.match(/data-n-a-ts="([^"]+)"/) || [])[1];
    const sig = (page.match(/data-n-a-sg="([^"]+)"/) || [])[1];
    if (!aid || !ts || !sig) return null;
    const inner = JSON.stringify([
      'garturlreq',
      [['X', 'X', ['X', 'X'], null, null, 1, 1, 'US:en', null, 1, null, null, null, null, null, 0, 1],
        'X', 'X', 1, [1, 1, 1], 1, 1, null, 0, 0, null, 0],
      aid, Number(ts), sig,
    ]);
    const body = new URLSearchParams({
      'f.req': JSON.stringify([[[ 'Fbv4je', inner, null, 'generic']]]),
    });
    const out = await fetch(BATCH_URL, {
      method: 'POST',
      body,
      headers: {
        'content-type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'user-agent': 'Mozilla/5.0 (compatible; nabz-worker/1.0)',
      },
    }).then((r) => r.text());
    const found = out.match(/https?:\/\/[^"\\\s]+/);
    if (!found) return null;
    const url = found[0].replace(/\\u003d/g, '=').replace(/\\u0026/g, '&');
    return url.includes('news.google.com') ? null : url;
  } catch (e) {
    return null;
  }
}

/** publisher page → og:image + description (+ first paragraphs) */
function toDataUrl(buf, contentType = 'image/jpeg') {
  const bytes = new Uint8Array(buf);
  let bin = '';
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
  }
  return `data:${contentType.split(';')[0]};base64,${btoa(bin)}`;
}

async function inlineImage(url, maxBytes = 90000) {
  if (!url) return null;
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 6000);
    const res = await fetch(url, {
      signal: ctrl.signal,
      headers: { 'user-agent': 'Mozilla/5.0 (compatible; nabz-worker/1.0)', accept: 'image/*' },
      cf: { cacheEverything: true, cacheTtl: 3600 },
    });
    clearTimeout(timer);
    if (!res.ok) return null;
    const type = res.headers.get('content-type') || 'image/jpeg';
    if (!type.startsWith('image/')) return null;
    const len = Number(res.headers.get('content-length') || 0);
    if (len && len > maxBytes) return url;          // خیلی بزرگ: همان لینک را بده
    const buf = await res.arrayBuffer();
    if (buf.byteLength > maxBytes) return url;
    return toDataUrl(buf, type);
  } catch (e) {
    return null;
  }
}

async function fetchPublisher(url, timeoutMs = 9000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      signal: ctrl.signal,
      headers: { 'user-agent': 'Mozilla/5.0 (compatible; nabz-worker/1.0)', accept: 'text/html' },
      redirect: 'follow',
    });
    if (!res.ok) return {};
    const html = (await res.text()).slice(0, 400000);
    const meta = (prop) =>
      (html.match(new RegExp(`<meta[^>]+(?:property|name)=["']${prop}["'][^>]+content=["']([^"']+)`, 'i')) ||
        html.match(new RegExp(`<meta[^>]+content=["']([^"']+)["'][^>]+(?:property|name)=["']${prop}["']`, 'i')) ||
        [])[1] || '';
    const img = meta('og:image') || meta('twitter:image');
    const desc = unescapeHtml(meta('og:description') || meta('description'));
    const paras = [...html.matchAll(/<p[^>]*>([\s\S]{40,600}?)<\/p>/gi)]
      .map((m) => unescapeHtml(stripTags(m[1])))
      .filter((t) => t.length > 40)
      .slice(0, 3);
    return {
      image: img && img.startsWith('http') ? await inlineImage(img) : null,
      summary: desc.slice(0, 400),
      text: paras.join('\n\n').slice(0, 1500),
    };
  } catch (e) {
    return {};
  } finally {
    clearTimeout(timer);
  }
}

async function ingestGoogleNews(limit = 12) {
  const xml = await fetch(GN_FEED, {
    headers: { 'user-agent': 'Mozilla/5.0 (compatible; nabz-worker/1.0)' },
  }).then((r) => r.text());
  const parsed = parseFeed(xml).slice(0, limit);
  const out = [];
  for (const item of parsed) {
    const real = await resolveGoogleUrl(item.google_url);
    if (!real) continue;
    const page = await fetchPublisher(real);
    const related = [...item.description_html.matchAll(/<a[^>]+href="([^"]+)"[^>]*>(.*?)<\/a>/gi)]
      .slice(0, 6)
      .map((m) => ({ domain: stripTags(m[2]), url: unescapeHtml(m[1]) }));
    out.push({
      source: 'gnews',
      source_label: 'G News',
      title: item.title,
      url: real,
      publisher: item.publisher,
      ts: item.ts,
      summary: page.summary || '',
      bullets: '',
      sections: [],
      text: page.text || '',
      sources_count: related.length,
      sources: related,
      image: page.image || null,
      image_cdn: page.image || null,
      read_time: null,
      lang: 'en',
    });
  }
  return out;
}

/** merge new items into the archive: dedupe + newest first + retention */
function mergeArchive(existing = [], fresh = [], { keepDays = 14, maxItems = 800 } = {}) {
  const seen = new Set();
  const key = (i) => `${i.source}|${(i.title || '').toLowerCase().slice(0, 80)}|${(i.url || '').slice(0, 60)}`;
  const merged = [];
  for (const it of [...fresh, ...existing]) {
    if (!it || !it.title) continue;
    const k = key(it);
    if (seen.has(k)) continue;
    seen.add(k);
    merged.push(it);
  }
  const cutoff = Date.now() - keepDays * 86400000;
  const kept = merged
    .filter((i) => !i.ts || Date.parse(i.ts) >= cutoff)
    .sort((a, b) => (Date.parse(b.ts) || 0) - (Date.parse(a.ts) || 0))
    .slice(0, maxItems);
  kept.forEach((it, idx) => (it.order = idx + 1));
  return kept;
}

/* -------------------------------------------------------------- filtering */
function applyQuery(items, url) {
  const q = url.searchParams;
  const source = (q.get('source') || '').toLowerCase();
  const query = (q.get('q') || '').trim().toLowerCase();
  const lang = q.get('lang');
  const since = q.get('since');
  const limit = num(q.get('limit'), 0);
  const offset = num(q.get('offset'), 0);

  let out = items;
  if (source && source !== 'all') out = out.filter((i) => i.source === source);
  if (lang) out = out.filter((i) => (i.lang || '').startsWith(lang.toLowerCase()));
  if (since) {
    const stamp = Date.parse(since);
    if (Number.isFinite(stamp)) out = out.filter((i) => i.ts && Date.parse(i.ts) >= stamp);
  }
  if (query) {
    out = out.filter((i) =>
      [i.title, i.summary, i.text, i.publisher].join(' ').toLowerCase().includes(query),
    );
  }
  out = out.slice().sort((a, b) => (Date.parse(b.ts) || 0) - (Date.parse(a.ts) || 0));
  if (offset) out = out.slice(offset);
  if (limit) out = out.slice(0, limit);
  return out;
}

/* ------------------------------------------------------------------- html */
const PAGE_CSS = `
:root{--ink:#e8eefb;--ink2:#aab6cc;--muted:#7d8aa3;--line:rgba(148,163,184,.16);--pdx:#8b8cf9;--gn:#34d399}
*{box-sizing:border-box}
body{margin:0;background:#06080f;color:var(--ink);font-family:Vazirmatn,"Segoe UI",Tahoma,system-ui,sans-serif;
background-image:radial-gradient(900px 520px at 88% -8%,rgba(99,102,241,.22),transparent 62%),
radial-gradient(760px 460px at 6% 4%,rgba(16,185,129,.16),transparent 60%);background-attachment:fixed}
.wrap{max-width:1160px;margin:0 auto;padding:34px 18px 70px}
.top{text-align:center;display:flex;flex-direction:column;align-items:center;gap:14px}
h1{margin:0;font-size:30px;background:linear-gradient(120deg,#fff,#c7d2fe 52%,#a7f3d0);-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{margin:0;font-size:11.5px;letter-spacing:2.4px;color:var(--muted);text-transform:uppercase}
.lede{color:var(--ink2);font-size:13.5px;line-height:2;margin:0}
.dock{position:sticky;top:0;z-index:9;display:flex;justify-content:center;padding:14px 0;
background:linear-gradient(180deg,rgba(6,8,15,.95) 42%,rgba(6,8,15,.7) 78%,transparent)}
.switch{display:inline-flex;gap:2px;padding:5px;border-radius:999px;background:rgba(12,16,28,.88);
border:1px solid var(--line);backdrop-filter:blur(16px)}
.switch button{border:0;background:transparent;color:#9fadc6;font:inherit;font-size:13.5px;font-weight:600;
padding:10px 20px;border-radius:999px;cursor:pointer;display:inline-flex;gap:8px;align-items:center}
.switch button[aria-selected="true"]{background:linear-gradient(135deg,rgba(99,102,241,.94),rgba(79,70,229,.86));color:#fff}
.switch .n{font-size:11px;background:rgba(148,163,184,.16);border-radius:99px;padding:2px 7px}
.strip{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;color:var(--muted);font-size:12px;margin:6px 0 10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:18px}
.grid>*{min-width:0}
.day{grid-column:1/-1;display:flex;align-items:center;gap:12px;margin:22px 2px 4px}
.day h2{font-size:12.5px;margin:0;padding:6px 14px;border-radius:99px;background:rgba(255,255,255,.05);border:1px solid var(--line)}
.day .line{flex:1;height:1px;background:linear-gradient(90deg,transparent,var(--line),transparent)}
.card{display:flex;flex-direction:column;gap:10px;padding:14px;border-radius:18px;overflow:hidden;
background:linear-gradient(180deg,rgba(255,255,255,.055),rgba(255,255,255,.022));
border:1px solid var(--line);box-shadow:0 18px 40px -28px #000}
.card img{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:12px;background:#0d1220;display:block}
.card .noimg{width:100%;aspect-ratio:16/9;border-radius:12px;display:grid;place-items:center;color:#8fa0bd;font-size:12px;
background:radial-gradient(120% 120% at 20% 0%,rgba(99,102,241,.3),transparent 60%),#0b1020}
.badge{font-size:10px;font-weight:800;letter-spacing:.6px;border-radius:99px;padding:3px 9px}
.badge.perplexity{background:rgba(99,102,241,.9);color:#fff}
.badge.gnews{background:rgba(5,150,105,.9);color:#fff}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:11.5px;color:var(--muted)}
h3{margin:0;font-size:17px;line-height:1.6;color:#f2f6ff}
a{color:inherit;text-decoration:none}
.summary{border-radius:12px;padding:10px 12px;font-size:13px;line-height:1.95;color:#d6e0f0;
background:rgba(255,255,255,.035);border:1px solid rgba(148,163,184,.09);border-inline-start:3px solid var(--pdx)}
.card.gnews .summary{border-inline-start-color:var(--gn)}
.summary .label{font-size:10px;font-weight:800;letter-spacing:1px;color:var(--pdx)}
.card.gnews .summary .label{color:var(--gn)}
.summary p{margin:0;unicode-bidi:plaintext;text-align:start;overflow-wrap:anywhere}
strong{color:#fff}
.empty{padding:40px;text-align:center;color:var(--muted)}
footer{margin-top:40px;text-align:center;color:#65728b;font-size:11.5px}
code{background:rgba(148,163,184,.16);border-radius:5px;padding:1px 6px}
`;

const PAGE_JS = `
const J_MONTHS = ['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور','مهر','آبان','آذر','دی','بهمن','اسفند'];
const J_DAYS = ['یکشنبه','دوشنبه','سه‌شنبه','چهارشنبه','پنجشنبه','جمعه','شنبه'];
function JALALI(ts){
  if(!ts) return 'بدون تاریخ';
  var d = new Date(ts); if(isNaN(d.getTime())) return 'بدون تاریخ';
  var gy=d.getUTCFullYear(), gm=d.getUTCMonth()+1, gd=d.getUTCDate();
  var gdm=[0,31,59,90,120,151,181,212,243,273,304,334];
  var jy = gy<=1600?0:979, gy2 = gy<=1600?gy-621:gy-1600;
  var days = 365*gy2 + Math.floor((gy2+3)/4) - Math.floor((gy2+99)/100) + Math.floor((gy2+399)/400) - 80 + gd + gdm[gm-1] + ((gy2%4===0 && gm>2)?1:0);
  jy += 33*Math.floor(days/12053); days %= 12053;
  jy += 4*Math.floor(days/1461); days %= 1461;
  if(days>365){ jy += Math.floor((days-1)/365); days = (days-1)%365; }
  var jm = days<186 ? 1+Math.floor(days/31) : 7+Math.floor((days-186)/30);
  var jd = 1 + (days<186 ? days%31 : (days-186)%30);
  return J_DAYS[d.getUTCDay()] + ' ' + fa(jd) + ' ' + J_MONTHS[jm-1] + ' ' + fa(jy);
}
const DATA = window.__HUB__ || [];
const grid = document.getElementById('grid');
function md(s){
  return String(s || '').replace(/[&<>"']/g, function(c){
    return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]);
  }).replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>');
}
function fa(n){ return String(n).replace(/\\d/g, function(d){ return '۰۱۲۳۴۵۶۷۸۹'[+d]; }); }
function day(ts){ return JALALI(ts); }
function card(e){
  var img = e.image
    ? '<img loading="lazy" alt="" src="' + e.image + '">'
    : '<div class="noimg">بدون تصویر</div>';
  var row = '<div class="row"><span class="badge ' + e.source + '">' + md(e.source_label) + '</span>'
    + (e.publisher ? '<span>' + md(e.publisher) + '</span>' : '')
    + (e.ts ? '<span>' + day(e.ts) + '</span>' : '') + '</div>';
  var sum = e.summary
    ? '<div class="summary"><div class="label">خلاصه</div><p>' + md(e.summary) + '</p></div>'
    : '';
  return '<article class="card ' + e.source + '">' + img + row
    + '<h3><a href="' + e.url + '" target="_blank" rel="noopener">' + md(e.title) + '</a></h3>'
    + sum + '</article>';
}
function render(which){
  var items = DATA.filter(function(e){ return which === 'all' || e.source === which; });
  if (!items.length) { grid.innerHTML = '<div class="empty">داده‌ای برای این منبع نیست</div>'; return; }
  var html = '', current = null;
  items.forEach(function(e){
    var key = day(e.ts);
    if (key !== current) { current = key; html += '<div class="day"><h2>' + key + '</h2><div class="line"></div></div>'; }
    html += card(e);
  });
  grid.innerHTML = html;
}
Array.prototype.forEach.call(document.querySelectorAll('.switch button'), function(b){
  b.addEventListener('click', function(){
    Array.prototype.forEach.call(document.querySelectorAll('.switch button'), function(x){
      x.setAttribute('aria-selected', x === b ? 'true' : 'false');
    });
    render(b.dataset.src);
  });
});
render('all');
`;

function pageHtml({ items, counts, generatedAt, origin }) {
  const payload = JSON.stringify(items).replace(/</g, '\\u003c').replace(/>/g, '\\u003e');
  const head = `<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark">
<title>نبض فناوری · Perplexity + G News</title><style>${PAGE_CSS}</style></head>
<body><div class="wrap">
<header class="top">
<h1>نبض فناوری</h1><p class="sub">Perplexity · Google News</p>
<p class="lede">یک صفحه، دو منبع، مرتب بر اساس تاریخ انتشار — سروشده از Cloudflare Workers.</p>
</header>
<div class="dock"><div class="switch" role="tablist">
<button data-src="all" aria-selected="true">All<span class="n">${counts.all}</span></button>
<button data-src="perplexity" aria-selected="false">Perplexity<span class="n">${counts.perplexity}</span></button>
<button data-src="gnews" aria-selected="false">G News<span class="n">${counts.gnews}</span></button>
</div></div>
<div class="strip"><span>${counts.all} خبر</span><span>·</span><span>${esc(generatedAt)}</span><span>·</span><code>/api/news</code></div>
<main id="grid" class="grid"></main>
<footer>nabz-worker · API: <code>/api/news</code> · <code>/api/rss</code> · <code>/api/hub</code></footer>
</div>`;
  return (
    head +
    '<script>window.__HUB__ = ' + payload + ';</script>' +
    '<script>' + PAGE_JS + '</script>' +
    '</body></html>'
  );
}

/* -------------------------------------------------------------------- rss */
function rss(items, origin) {
  const entries = items
    .slice(0, 100)
    .map(
      (i) => `    <item>
      <title>${esc(i.title)}</title>
      <link>${esc(i.url)}</link>
      <guid isPermaLink="false">${esc(i.id)}</guid>
      <category>${esc(i.source_label)}</category>
      <pubDate>${i.ts ? new Date(i.ts).toUTCString() : new Date().toUTCString()}</pubDate>
      <description>${esc(i.summary || i.text || '')}</description>
    </item>`,
    )
    .join('\n');
  return `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
    <title>نبض فناوری — Perplexity + Google News</title>
    <link>${origin}/</link>
    <description>Combined tech news hub</description>
    <language>fa</language>
${entries}
</channel></rss>`;
}


/* --------------------------------------------------------------- cron entry */
async function runScheduled(env, waitUntil) {
  const started = new Date().toISOString();
  const log = { started, steps: [] };
  const kv = env.HUB;

  if (!kv || typeof kv.put !== 'function') {
    return { ok: false, error: 'KV binding HUB is missing', ...log };
  }

  let fresh = [];
  try {
    fresh = await ingestGoogleNews(env.GNEWS_CRON_LIMIT ? Number(env.GNEWS_CRON_LIMIT) : 12);
    log.steps.push(`gnews fetched: ${fresh.length}`);
  } catch (e) {
    log.steps.push(`gnews fetch failed: ${e && e.message ? e.message : e}`);
  }

  const existingG = (await kv.get('hub:gnews', 'json')) || [];
  const mergedG = mergeArchive(existingG, fresh, {
    keepDays: Number(env.KEEP_DAYS || 14),
    maxItems: Number(env.MAX_ITEMS || 800),
  });
  await kv.put('hub:gnews', JSON.stringify(mergedG));
  log.steps.push(`gnews archive: ${existingG.length} → ${mergedG.length}`);

  // Perplexity همچنان توسط اکشن گیت‌هاب ساخته می‌شود؛ همین‌جا از گیت‌هاب تازه‌سازی می‌شود
  let pdx = (await kv.get('hub:perplexity', 'json')) || [];
  try {
    const repo = env.GITHUB_REPO || DEFAULTS.repo;
    const branch = env.GITHUB_BRANCH || DEFAULTS.branch;
    const res = await fetch(`https://raw.githubusercontent.com/${repo}/${branch}/data/perplexity_tech.json`, {
      headers: { 'user-agent': 'nabz-worker' },
      cf: { cacheEverything: true, cacheTtl: 300 },
    });
    if (res.ok) {
      const doc = await res.json();
      pdx = normalize(Array.isArray(doc) ? doc : doc.items || [], 'perplexity');
      log.steps.push(`perplexity refreshed: ${pdx.length}`);
    }
  } catch (e) {
    log.steps.push('perplexity refresh failed (kept KV copy)');
  }
  await kv.put('hub:perplexity', JSON.stringify(pdx));

  const all = mergeArchive([], [...pdx, ...mergedG], {
    keepDays: Number(env.KEEP_DAYS || 14),
    maxItems: Number(env.MAX_ITEMS || 800),
  });
  await kv.put('hub:all', JSON.stringify(all));
  await kv.put('hub:meta', JSON.stringify({ updated_at: new Date().toISOString(), counts: {
    all: all.length,
    perplexity: all.filter((i) => i.source === 'perplexity').length,
    gnews: all.filter((i) => i.source === 'gnews').length,
  }, steps: log.steps }));
  log.finished = new Date().toISOString();
  return { ok: true, ...log, counts: { all: all.length, gnews: mergedG.length, perplexity: pdx.length } };
}

/* ------------------------------------------------------------------- main */
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, '') || '/';

    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
    if (request.method !== 'GET' && request.method !== 'HEAD') return bad('method not allowed', 405);

    if (path === '/health') return json({ ok: true, service: 'nabz-worker', time: new Date().toISOString() });

    if (path === '/api' || path === '/api/') {
      return json({
        ok: true,
        service: 'nabz-worker',
        endpoints: ['/api/news', '/api/perplexity', '/api/gnews', '/api/hub', '/api/meta', '/api/item/:id', '/api/rss', '/health', '/'],
        params: ['source=all|perplexity|gnews', 'q=text', 'limit', 'offset', 'since=ISO', 'lang=en', 'format=json|rss'],
        example: `${url.origin}/api/news?source=gnews&limit=5`,
      });
    }

    // data endpoints
    if (path.startsWith('/api/')) {
      const [p, g] = await Promise.all([fetchSource(env, 'perplexity'), fetchSource(env, 'gnews')]);
      const all = [...p.items, ...g.items].sort((a, b) => (Date.parse(b.ts) || 0) - (Date.parse(a.ts) || 0));

      if (path === '/api/item' || path.startsWith('/api/item/')) {
        const id = path.split('/')[3] || url.searchParams.get('id') || '';
        const found = all.find((i) => i.id === id);
        return found ? json({ ok: true, item: found }) : bad('item not found', 404);
      }

      const counts = {
        all: all.length,
        perplexity: all.filter((i) => i.source === 'perplexity').length,
        gnews: all.filter((i) => i.source === 'gnews').length,
      };
      const generatedAt = new Date().toISOString();
      const origin = url.origin;

      if (path === '/api/meta') {
        const meta = env.HUB ? (await env.HUB.get('hub:meta', 'json')) : null;
        return json({ ok: true, cron: meta || null, counts });
      }

      if (path === '/api/hub') {
        return json({
          ok: true,
          generated_at: generatedAt,
          counts,
          sources: { perplexity: p.via, gnews: g.via },
          warnings: [p.error, g.error].filter(Boolean),
          items: all,
        });
      }

      let items = all;
      if (path === '/api/perplexity') items = all.filter((i) => i.source === 'perplexity');
      if (path === '/api/gnews') items = all.filter((i) => i.source === 'gnews');
      items = applyQuery(items, url);

      if (path === '/api/rss' || url.searchParams.get('format') === 'rss') {
        return new Response(rss(items, origin), {
          headers: { 'content-type': 'application/rss+xml; charset=utf-8', 'cache-control': 'public, max-age=300', ...CORS },
        });
      }
      return json({ ok: true, generated_at: generatedAt, count: items.length, counts, items });
    }

    if (path === '/') {
      const [p, g] = await Promise.all([fetchSource(env, 'perplexity'), fetchSource(env, 'gnews')]);
      const all = [...p.items, ...g.items].sort((a, b) => (Date.parse(b.ts) || 0) - (Date.parse(a.ts) || 0));
      const counts = {
        all: all.length,
        perplexity: all.filter((i) => i.source === 'perplexity').length,
        gnews: all.filter((i) => i.source === 'gnews').length,
      };
      return new Response(
        pageHtml({ items: all, counts, generatedAt: new Date().toISOString().replace('T', ' ').slice(0, 16) + ' UTC', origin: url.origin }),
        { headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'public, max-age=300', 'content-security-policy': "default-src 'self' 'unsafe-inline' data: https:" } },
      );
    }

    return bad('not found', 404);
  },

  /** Cloudflare Cron Trigger — هر ساعت خبرهای تازه را در KV ذخیره می‌کند */
  async scheduled(event, env, ctx) {
    const task = runScheduled(env).catch((e) => ({ ok: false, error: String(e) }));
    if (ctx && typeof ctx.waitUntil === 'function') ctx.waitUntil(task);
    else await task;
  },

  /** برای تست لوکال / دیباگ دستی */
  async runNow(env) {
    return runScheduled(env);
  },
};
