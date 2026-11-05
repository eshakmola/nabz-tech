#!/usr/bin/env node
/**
 * تست cron trigger ورکر (بدون حساب کلادفلر):
 * ingest گوگل‌نیوز + merge + KV را با یک fetch و KV جعلی اجرا می‌کند.
 *
 *   node cloudflare/test-cron.mjs          # شبکه واقعی (Google News)
 *   OFFLINE=1 node cloudflare/test-cron.mjs  # فقط merge/KV با داده‌ی ساختگی
 */
const OFFLINE = process.env.OFFLINE === '1';

// ---- KV جعلی ----
const store = new Map();
const KV = {
  async get(key, type) {
    const raw = store.get(key);
    if (raw === undefined) return null;
    return type === 'json' ? JSON.parse(raw) : raw;
  },
  async put(key, value) { store.set(key, value); },
};

// ---- fetch جعلی برای حالت آفلاین ----
const realFetch = globalThis.fetch;
if (OFFLINE) {
  globalThis.fetch = async (input) => {
    const url = typeof input === 'string' ? input : input.url;
    if (url.includes('/rss/headlines/')) {
      const now = new Date(Date.now() - 3600 * 1000);  // یک ساعت پیش (داخل KEEP_DAYS)
      const item = (i) => `<item><title>Story ${i} about AI - Publisher ${i}</title>
        <link>https://news.google.com/rss/articles/CBM${i}?oc=5</link>
        <pubDate>${new Date(now.getTime() - i * 60000).toUTCString()}</pubDate>
        <description>&lt;ol&gt;&lt;li&gt;&lt;a href="https://x.com/a"&gt;A&lt;/a&gt;&lt;/li&gt;&lt;/ol&gt;</description></item>`;
      return new Response(`<rss><channel>${[1,2,3,4,5].map(item).join('')}</channel></rss>`);
    }
    if (url.includes('news.google.com/rss/articles')) {
      return new Response('<div data-n-a-id="AID" data-n-a-ts="1700000000" data-n-a-sg="SIG"></div>');
    }
    if (url.includes('batchexecute')) {
      return new Response('[["wrb.fr","Fbv4je","[\\"garturlres\\",\\"https://publisher.example/x\\",1]"]]');
    }
    if (url.includes('publisher.example')) {
      return new Response('<html><head><meta property="og:image" content="https://publisher.example/i.jpg">'
        + '<meta property="og:description" content="Desc here"></head><body><p>'
        + 'x'.repeat(80) + '</p></body></html>');
    }
    if (url.includes('raw.githubusercontent.com')) {
      return new Response(JSON.stringify([{ source:'perplexity', title:'PDX item', url:'https://p/1', ts:'2026-11-05T10:00:00Z' }]));
    }
    return realFetch ? realFetch(input) : new Response('', { status: 404 });
  };
}

const { default: worker } = await import('./src/index.js');

const env = {
  HUB: KV,
  GITHUB_REPO: 'eshakmola/nabz-tech',
  GITHUB_BRANCH: 'main',
  KEEP_DAYS: '14',
  MAX_ITEMS: '800',
};

const checks = [];
const expect = (name, cond, extra = '') => {
  checks.push(!!cond);
  console.log(`${cond ? '✅' : '❌'} ${name}${extra ? ' — ' + extra : ''}`);
};

// اجرای واقعی cron
const result = await worker.runNow(env);
expect('cron ran ok', result.ok === true, JSON.stringify(result.counts || result.error));
expect('gnews archive written', (await KV.get('hub:gnews', 'json')).length > 0,
  `n=${(await KV.get('hub:gnews', 'json')).length}`);
expect('hub:all written', (await KV.get('hub:all', 'json')).length > 0);
expect('meta written', (await KV.get('hub:meta', 'json')).updated_at !== undefined);

// اجرای دوباره: نباید تکراری اضافه شود
const before = (await KV.get('hub:gnews', 'json')).length;
await worker.runNow(env);
const after = (await KV.get('hub:gnews', 'json')).length;
expect('dedupe on re-run', after === before, `${before} → ${after}`);

// /api/meta و /api/hub از KV می‌خوانند
const req = new Request('http://local.test/api/meta');
const meta = await (await worker.fetch(req, env, {})).json();
expect('/api/meta reports cron state', meta.ok && meta.cron && meta.cron.counts, JSON.stringify(meta.cron?.counts));
const hub = await (await worker.fetch(new Request('http://local.test/api/hub'), env, {})).json();
expect('/api/hub reads KV archive', hub.counts.all >= 1, `all=${hub.counts.all}`);

// retention
const { mergeArchive } = { mergeArchive: null };
const old = [{ title: 'old', source: 'gnews', ts: '2020-01-01T00:00:00Z', url: 'u' }];
// از طریق runNow نمی‌شود مستقیم تست کرد؛ پس رفتار را با داده‌ی کهنه در KV می‌سنجیم
await KV.put('hub:gnews', JSON.stringify([...old, ...(await KV.get('hub:gnews', 'json'))]));
await worker.runNow(env);
const afterRetention = await KV.get('hub:gnews', 'json');
expect('retention drops items older than KEEP_DAYS', !afterRetention.some((i) => i.title === 'old'),
  `n=${afterRetention.length}`);

const failed = checks.filter((c) => !c).length;
console.log(`\n${checks.length - failed}/${checks.length} checks passed`);
process.exit(failed ? 1 : 0);
