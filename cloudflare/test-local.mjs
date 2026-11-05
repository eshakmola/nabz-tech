#!/usr/bin/env node
/**
 * worker  را کاملًا لوکال (بدون حساب کلادفلر) تست می‌کند.
 *
 *   node cloudflare/test-local.mjs            # با دادهٔ زندهٔ data/*.json
 *   BASE=http://127.0.0.1:8787 node ...        # اگر خودتان wrangler dev را بالا آورده‌اید
 *
 * اگر BASE داده نشود، خودِ ماژول worker را با یک env جعلی صدا می‌زند و
 * upstream گیت‌هاب را با یک fetch جایگزین (فایل‌های لوکال) شبیه‌سازی می‌کند.
 */
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');

const FILES = {
  'data/perplexity_tech.json': join(root, 'data', 'perplexity_tech.json'),
  'data/gnews.json': join(root, 'data', 'gnews.json'),
};

// fetch جایگزین برای حالت آفلاین
const realFetch = globalThis.fetch;
globalThis.fetch = async (input, init) => {
  const url = typeof input === 'string' ? input : input.url;
  for (const [suffix, file] of Object.entries(FILES)) {
    if (url.endsWith(suffix)) {
      const body = await readFile(file, 'utf8');
      return new Response(body, { status: 200, headers: { 'content-type': 'application/json' } });
    }
  }
  return realFetch(input, init);
};

const { default: worker } = await import(join(here, 'src', 'index.js'));

const BASE = process.env.BASE || 'http://local.test';
const env = { GITHUB_REPO: 'eshakmola/nabz-tech', GITHUB_BRANCH: 'main' };

async function call(path) {
  const req = new Request(BASE + path, { method: 'GET' });
  const res = await worker.fetch(req, env, {});
  const text = await res.text();
  let body = null;
  try {
    body = JSON.parse(text);
  } catch {
    body = text;
  }
  return { status: res.status, type: res.headers.get('content-type') || '', body };
}

const checks = [];
const expect = (name, cond, extra = '') => {
  checks.push([name, !!cond, extra]);
  console.log(`${cond ? '✅' : '❌'} ${name}${extra ? ' — ' + extra : ''}`);
};

const health = await call('/health');
expect('/health', health.status === 200 && health.body.ok === true);

const api = await call('/api');
expect('/api index lists endpoints', Array.isArray(api.body.endpoints) && api.body.endpoints.includes('/api/news'));

const hub = await call('/api/hub');
expect('/api/hub ok', hub.status === 200 && hub.body.ok === true, `items=${hub.body.counts?.all}`);
expect('hub has both sources', hub.body.counts?.perplexity >= 0 && hub.body.counts?.gnews >= 0,
  `p=${hub.body.counts?.perplexity} g=${hub.body.counts?.gnews}`);
const stamps = (hub.body.items || []).map((i) => i.ts || '');
expect('items sorted by date desc', stamps.every((s, i) => i === 0 || (stamps[i - 1] || '') >= (s || '')));

const only = await call('/api/gnews');
expect('/api/gnews returns only gnews', only.body.items.every((i) => i.source === 'gnews'), `n=${only.body.count}`);

const lim = await call('/api/news?limit=3');
expect('limit works', lim.body.items.length <= 3, `n=${lim.body.items.length}`);

const q = await call('/api/news?q=ai');
expect('q filter works', Array.isArray(q.body.items), `n=${q.body.count}`);

const rss = await call('/api/rss');
expect('/api/rss is xml', rss.type.includes('rss') && String(rss.body).includes('<rss'), rss.type);

const page = await call('/');
expect('/ returns the web UI', page.status === 200 && String(page.body).includes('نبض فناوری'));
expect('page has 3-way switch', ['data-src="all"', 'data-src="perplexity"', 'data-src="gnews"'].every((s) => String(page.body).includes(s)));

const missing = await call('/api/item/nope');
expect('unknown item → 404', missing.status === 404);

const failed = checks.filter((c) => !c[1]).length;
console.log(`\n${checks.length - failed}/${checks.length} checks passed`);
process.exit(failed ? 1 : 0);
