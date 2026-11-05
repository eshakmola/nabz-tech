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
GET /api/meta         → وضعیت آخرین اجرای کران (updated_at، شمارش‌ها، مراحل)
GET /api/item/:id     → یک خبر
GET /api/rss          → RSS 2.0 فید ترکیبی
```

پارامترهای همه‌ی اندپوینت‌ها: `source=all|perplexity|gnews` · `q=` · `limit=` · `offset=` ·
`since=ISO` · `lang=` · `format=json|rss`

```bash
curl "https://nabz-worker.<account>.workers.dev/api/news?source=gnews&limit=3"
curl "https://nabz-worker.<account>.workers.dev/api/rss"
```

## ⏰ کران ساعتی (Cron Trigger)

```toml
[triggers]
crons = ["5 * * * *"]     # هر ساعت، دقیقه‌ی ۵
```

`handler scheduled` در هر اجرا:

1. فید **Google News Tech** را می‌خواند (بدون مرورگر).
2. لینک‌های `news.google.com/rss/articles/CBM…` را با `batchexecute` به آدرس ناشر تبدیل می‌کند.
3. از صفحه‌ی ناشر `og:image` (به‌صورت **base64 inline**، بدون هات‌لینک)، `og:description` و چند پاراگراف را برمی‌دارد.
4. با آرشیو قبلی در KV **dedupe** می‌کند (کلید: منبع + عنوان + بخشی از لینک)، مرتب بر تاریخ،
   با نگه‌داری `KEEP_DAYS` (پیش‌فرض ۱۴ روز) و سقف `MAX_ITEMS` (پیش‌فرض ۸۰۰).
5. `hub:gnews`، `hub:perplexity` (تازه‌سازی از گیت‌هاب)، `hub:all` و `hub:meta` را در KV می‌نویسد.

`GET /api/meta` وضعیت همین اجرا را نشان می‌دهد:

```json
{"cron": {"updated_at": "…", "counts": {"all": 20, "perplexity": 8, "gnews": 12}, "steps": ["gnews fetched: 12", "…"]}}
```

> Perplexity به مرورگر نیاز دارد، پس آن سمت با اکشن گیت‌هاب (هر ساعت) ساخته می‌شود؛
> ورکر آن را در KV تازه می‌کند و در آرشیو ترکیبی می‌ریزد.

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
node cloudflare/test-local.mjs      # 12/12 بررسی (API + وب)
node cloudflare/test-cron.mjs       # 8/8 بررسی (کران: فید واقعی → resolve → KV)
OFFLINE=1 node cloudflare/test-cron.mjs   # همان تست، بدون شبکه
```

## امنیت

- توکن کلادفلر فقط در Secrets گیت‌هاب؛ نه در کد و نه در wrangler.toml.
- CORS باز (`*`) چون API عمومی خواندنی است؛ فقط متد `GET/HEAD` پذیرفته می‌شود.
- خروجی JSON با `cache-control` کوتاه و `cacheEverything` در لبه کش می‌شود.
