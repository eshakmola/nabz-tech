# nabz-worker — «نبض فناوری» روی Cloudflare Workers

API + وب، در یک Worker واحد (بدون سرور، بدون asset خارجی).

```
GET /                 → وب‌اپ (همان تم دارک هاب، سوییچر سه‌گانه)
GET /health           → سلامت سرویس
GET /api              → فهرست اندپوینت‌ها
GET /api/news         → فید ترکیبی مرتب بر اساس تاریخ
GET /api/perplexity   → فقط Perplexity
GET /api/gnews        → فقط Google News
GET /api/hub          → { items, counts, generated_at, sources, warnings }
GET /api/item/:id     → یک خبر
GET /api/rss          → RSS 2.0 فید ترکیبی
```

پارامترهای همه‌ی اندپوینت‌ها: `source=all|perplexity|gnews` · `q=` · `limit=` · `offset=` ·
`since=ISO` · `lang=` · `format=json|rss`

```bash
curl "https://nabz-worker.<account>.workers.dev/api/news?source=gnews&limit=3"
curl "https://nabz-worker.<account>.workers.dev/api/rss"
```

## داده از کجا می‌آید؟

به ترتیب اولویت:

1. **KV** (`HUB` binding) — اکشن گیت‌هاب (`publish.yml`) هر ۳ ساعت کلیدهای
   `hub:perplexity` / `hub:gnews` / `hub:all` را می‌نویسد.
2. **raw.githubusercontent.com** — `data/perplexity_tech.json` و `data/gnews.json` از همین ریپو
   (پس ورکر حتی بدون KV هم کار می‌کند).

هیچ کلیدی داخل ورکر نیست؛ فقط دو متغیر `GITHUB_REPO` و `GITHUB_BRANCH` در `wrangler.toml`.

## دیپلوی

### الف) خودکار (گیت‌هاب اکشنز)

این Secretها را در `Settings → Secrets and variables → Actions` بگذارید:

| نام | مقدار |
|---|---|
| `CLOUDFLARE_API_TOKEN` | توکن API با دسترسی **Workers Scripts:Edit** + **Workers KV Storage:Edit** |
| `CLOUDFLARE_ACCOUNT_ID` | Account ID (از داشبورد کلادفلر) |
| `CF_KV_NAMESPACE` | شناسه‌ی namespace ساخته‌شده برای `HUB` |

بعد از هر push/زمان‌بندی، job `deploy-worker` خودش `wrangler deploy` می‌زند.

### ب) دستی

```bash
cd cloudflare
npm install

# ۱) ساخت namespace و گذاشتن id در wrangler.toml
npx wrangler kv namespace create HUB

# ۲) دیپلوی
export CLOUDFLARE_API_TOKEN=...
export CLOUDFLARE_ACCOUNT_ID=...
npx wrangler deploy
```

### ج) تست کامل بدون حساب کلادفلر

```bash
cd ..                       # ریشه‌ی ریپو
python scripts/publish_data.py --dir output --out data
node cloudflare/test-local.mjs      # 12/12 checks
```

## امنیت

- توکن کلادفلر فقط در Secrets گیت‌هاب؛ نه در کد و نه در wrangler.toml.
- CORS باز (`*`) چون API عمومی خواندنی است؛ فقط متد `GET/HEAD` پذیرفته می‌شود.
- خروجی JSON با `cache-control` کوتاه و `cacheEverything` در لبه کش می‌شود.
