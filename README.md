# 🕷️ News Scraper Toolkit — Perplexity Discover + Google News

[![CI](https://github.com/USERNAME/perplexity-discover-scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/USERNAME/perplexity-discover-scraper/actions/workflows/ci.yml)
[![Scrape](https://github.com/USERNAME/perplexity-discover-scraper/actions/workflows/scrape.yml/badge.svg)](https://github.com/USERNAME/perplexity-discover-scraper/actions/workflows/scrape.yml)
[![Docker](https://github.com/USERNAME/perplexity-discover-scraper/actions/workflows/docker.yml/badge.svg)](https://github.com/USERNAME/perplexity-discover-scraper/actions/workflows/docker.yml)
![python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)
![license](https://img.shields.io/badge/license-MIT-green)

دو اسکرپر مستقل روی [Scrapling](https://github.com/D4Vinci/Scrapling) 0.5:

1. **Perplexity Discover** — تصویر شاخص + `Summary` (چکیده و بولت‌ها) + `Report` کامل بخش‌به‌بخش
2. **Google News RSS** — تیتر از `<title>`، باز کردن لینک `<link>` تا آدرس واقعی ناشر،
   کشیدن **تصویر و متن خبر**، و پارس `<description>` (پوشش‌های مرتبط) با لینک‌های باز‌شده

خروجی: `JSON` + `CSV` + `Markdown` + یک `HTML` تک‌فایلی RTL با تصاویر جاسازی‌شده (base64) — آماده‌ی باز شدن آفلاین یا انتشار روی GitHub Pages.

---

## ✨ امکانات

- 🖼️ تصویر شاخص هر خبر (دانلود + اعتبار عکاس)
- 📝 `summary` یک‌خطی + `bullet_summary` (نکات کلیدی)
- 📖 `report_sections[]` — متن کامل گزارش، هر بخش با تیتر خودش
- 🔗 منابع: عنوان، دامنه، لینک و تاریخ (حداکثر ۱۲ منبع اول در JSON)
- 🕵️ عبور از Cloudflare/Turnstile با `StealthySession` (Patchright)
- ⚡ یک بار باز کردن مرورگر + `fetch` درون‌صفحه‌ای برای همه‌ی مقاله‌ها (≈ ۲۰ خبر در ~۲۲ ثانیه)
- 🧪 ۲۸ تست واحد که **بدون مرورگر و بدون شبکه** اجرا می‌شوند
- 🤖 چهار GitHub Workflow + یک Composite Action + Docker/Compose
- 🌐 خروجی آماده برای GitHub Pages (`--site docs/`)

---

## 🚀 نصب

```bash
git clone https://github.com/USERNAME/perplexity-discover-scraper.git
cd perplexity-discover-scraper

python -m venv .venv && source .venv/bin/activate    # ویندوز: .venv\Scripts\activate
pip install -e ".[dev]"
scrapling install        # Chromium برای Patchright (~700MB، فقط یک‌بار)
```

یا بدون نصب پکیج:

```bash
pip install -r requirements.txt && scrapling install
```

## ▶️ اجرا

```bash
# دسته‌ی tech، همه‌ی کارت‌های صفحه
python perplexity_tech_scraper.py

# فقط ۵ خبر، بدون تصویر (سریع‌تر)
python perplexity_tech_scraper.py --limit 5 --no-images

# دسته‌ی دیگر + خروجی دلخواه
python perplexity_tech_scraper.py --category finance --out output/finance

# فقط خبرهای جدیدتر از ۶ ساعت
python perplexity_tech_scraper.py --max-age-hours 6

# ساخت خروجی برای GitHub Pages
python perplexity_tech_scraper.py --site docs

# رندر مجدد از JSON ذخیره‌شده (بدون شبکه)
python perplexity_tech_scraper.py --from-json output/perplexity_tech.json --out rebuilt

# نسخه‌ی سبک صفحه‌ی اصلی Discover (فقط تیتر/سن/منابع)
python perplexity_discover.py 15
```

بعد از `pip install -e .` این دستور هم در دسترس است: `pdx-scrape --category tech`

### آرگومان‌ها

| آرگومان | پیش‌فرض | توضیح |
|---|---|---|
| `--category` | `tech` | `tech` \| `top` \| `finance` \| `sports` \| `arts` \| `health` |
| `--limit N` | همه | حداکثر تعداد خبر |
| `--out DIR` | `output` | پوشه‌ی خروجی |
| `--no-images` | — | بدون دانلود تصویر |
| `--no-scroll` | — | اسکرول نکن (سریع‌تر) |
| `--max-age-hours N` | — | فقط خبرهای جدیدتر از N ساعت |
| `--min-items N` | `1` | اگر کمتر از این تعداد استخراج شد، با کد خطای ۱ خارج شو (گارد CI) |
| `--site DIR` | — | نوشتن `index.html` + کپی آرشیو + `.nojekyll` برای Pages |
| `--from-json FILE` | — | رندر مجدد از JSON (بدون مرورگر) |
| `--quiet` | — | لاگ کمتر |

### خروجی‌ها

```
output/
├── perplexity_tech.json     # داده‌ی کامل (summary، report_sections، sources، image_*)
├── perplexity_tech.csv      # برای اکسل (UTF-8 BOM)
├── perplexity_tech.md       # مارک‌داون با تصویر، Summary، Report و منابع
├── perplexity_tech.html     # گزارش کارتی RTL، تک‌فایل با تصاویر base64
└── images/                  # تصویر شاخص هر خبر
```

---

## 🧠 چطور کار می‌کند (و چرا)

صفحه‌ی Discover یک اپ Next.js پشت Cloudflare است:

| مرحله | ابزار | یادداشت |
|---|---|---|
| ۱. باز کردن صفحه | `StealthySession` + `solve_cloudflare=True` | با `Fetcher` ساده فقط ~۱۹KB اسکلت خالی می‌آید |
| ۲. پیدا کردن کارت‌ها | `a[href*="/discover/"]` در DOM رندرشده | لینک خود دسته‌ها فیلتر می‌شوند |
| ۳. گرفتن داده‌ی کامل | `fetch('/rest/article/<slug>?version=2.18&source=default')` **داخل همان صفحه** | ۲۰ ناوبری مرورگر → ۲۰ درخواست سبک |
| ۴. پارس | `pdx.parser` (تابع خالص) | با fixture قابل تست است |
| ۵. رندر | `pdx.render` | CSV/JSON/MD/HTML |

### نقشه‌ی فیلدها

| خروجی | منبع در پاسخ API |
|---|---|
| `title` | `entries[0].article_info.title` |
| `summary` | `entries[0].article_info.summary` |
| `bullet_summary` | `entries[0].article_info.bullet_summary` |
| `report_sections[]` | `entries[i].query_str` + `json.loads(entries[i].text)["answer"]` |
| `sources[]` | `web_results[]` → `name`, `url`, `meta_data.date` |
| `image_url` / `image_credit` | `entries[0].featured_images[0].image` / `.author_url` |
| `published` / `published_iso` | `entries[0].updated_datetime` (بدون تایم‌زون → UTC) |
| `read_time_min` | `article_info.read_time` |

### گالری تله‌ها 🪤

1. `page.css("a >> b")` در Scrapling 0.5 پشتیبانی نمی‌شود → `SelectorSyntaxError`.
2. کلاس‌های Tailwind پرکسپلکسیتی مشترک‌اند؛ «1 hour ago» داخل `<span>` است → باید `*::text` گرفت نه `::text`.
3. `page.markdown()` **متد** است، نه property؛ `page.text` هم رشته‌ی HTML نیست (`html_content` / `get_all_text()`).
4. در حالت مهمان بعد از ۲۰ کارت lazy-load بیشتری نمی‌آید.
5. متن‌ها نشانه‌ی داخلی دارند: `[Amazon](pplx://entity_chip/…)` و `[1]` که باید پاک شوند.
6. `updated_datetime` بدون تایم‌زون است → `tzinfo` دستی UTC می‌شود، وگرنه `TypeError`.

---

## 📰 Google News RSS (`gnews_scraper.py`)

```bash
# فید پیش‌فرض: Technology — Latest (همان لینکی که دادید)
python gnews_scraper.py --limit 10

# فید دلخواه (جست‌وجو، تاپیک، زبان/کشور)
python gnews_scraper.py --feed "https://news.google.com/rss/search?q=openai&hl=en-US&gl=US&ceid=US:en"

# بدون باز کردن صفحات ناشر (فقط فید + دیسکریپشن؛ خیلی سریع)
python gnews_scraper.py --describe-only --limit 20

# برای سایت‌هایی که HTTP را بلاک می‌کنند (Forbes 403): مرورگر مخفی
python gnews_scraper.py --limit 5 --dynamic

# خروجی آماده‌ی GitHub Pages
python gnews_scraper.py --limit 10 --site site
```

### هر آیتم چه چیزی دارد؟

| فیلد | منبع |
|---|---|
| `title` | تگ `<title>` فید (تیتر خبر + نام ناشر) |
| `google_url` | تگ `<link>` فید (ریدایرکت گوگل) |
| `resolved_url` / `url` | **آدرس واقعی ناشر** — با توکن‌های `data-n-a-id/ts/sg` و RPC `batchexecute` باز می‌شود |
| `description` | `og:description` ناشر، یا متن تخت `<description>` گوگل |
| `related_links[]` | `<description>` گوگل: `title` + `publisher` + `url` و **`resolved_url`** (لینک هر پوشش هم باز می‌شود) |
| `image_url` / `image_file` | `og:image` ناشر + دانلود در `output/images/` |
| `text` / `text_chars` | متن خبر (پاراگراف‌های صفحه‌ی ناشر، با حذف منو/کوکی/تبلیغ) |
| `publisher`, `published_iso`, `fetch_status` | متادیتای ناشر و وضعیت HTTP |

### تصویر و متن: زنجیره‌ی fallback (رفتار v1.2)

برای هر خبر:

1. **لینک اصلی** باز می‌شود → متن + **تصویر شاخص** (`og:image`).
2. اگر متن کامل نبود (< ۲۰۰ کاراکتر، مثل 403/202) **یا** تصویری نبود →
   لینک‌های داخل `<description>` یکی‌یکی امتحان می‌شوند
   (بدون آدرس تکراری، از هر دامنه یک‌بار، تا سقف `--max-candidates`؛ پیش‌فرض **۴**).
3. تصویر شاخص = تصویر لینک اصلی؛ اگر نبود، اولین تصویری که از لینک‌های description آمد.
4. اگر هیچ صفحه‌ای متن کامل نداد، بهترین متن جزئی نگه داشته می‌شود.

برای **تصویر** علاوه بر `og:image`، این‌ها هم به‌عنوان کاندید دانلود می‌شوند:
`og:image:secure_url` → `twitter:image` → JSON-LD → `<img data-src>` داخل متن
(دانلود اولی که موفق شد استفاده می‌شود).

| فیلد | معنی |
|---|---|
| `image_url` / `image_file` | تصویر شاخص خبر |
| `image_source` | آدرسی که تصویر از آن گرفته شد |
| `text_source` / `text_from_related` | متن از کدام لینک آمد |
| `tried[]` | لینک‌های چک‌شده با `status` / `text_chars` / `image` |

### چرا لینک‌ها «باز» می‌شوند؟

لینک‌های `news.google.com/rss/articles/CBM…` ریدایرکت جاوااسکریپتی‌اند و با `curl -L`
به آدرس ناشر نمی‌رسند (فقط یک صفحه‌ی پوسته با کدهای رمز‌شده برمی‌گردانند). روشی که
پیاده شده:

1. یک GET سبک به همان صفحه → استخراج `data-n-a-id`, `data-n-a-ts`, `data-n-a-sg`
2. یک POST به `/_/DotsSplashUi/data/batchexecute` با متد `Fbv4je`
3. خواندن آدرس ناشر از پاسخ (`garturlres`)

≈ ۰.۱ ثانیه برای هر لینک، بدون مرورگر. اگر پاسخ نداد، به همان لینک گوگل fallback می‌شود.

### خروجی‌ها

```
output/
├── gnews.json     # داده‌ی کامل (متن خبر + لینک‌های باز‌شده)
├── gnews.csv      # اکسل (UTF-8 BOM)
├── gnews.md       # مارک‌داون با تصویر، دیسکریپشن، متن و پوشش مرتبط
├── gnews.html     # کارت‌های RTL با تصاویر base64
└── images/        # تصویر شاخص هر خبر
```

> ⚠️ بعضی سایت‌ها (Forbes، Hypebeast، TweakTown) به درخواست HTTP با 403/202 پاسخ می‌دهند؛
> برای آن‌ها `--dynamic` (مرورگر مخفی) یا `--describe-only` استفاده کنید. این موارد در
> `fetch_status` ثبت می‌شوند و بقیه‌ی فید ادامه پیدا می‌کند.

---

## 🧩 هاب واحد وب — «نبض فناوری» (All / Perplexity / G News)

یک صفحه‌ی HTML که **هر دو منبع** را نشان می‌دهد، با سوییچر سه‌تایی و **مرتب‌سازی بر اساس تاریخ انتشار** —
ولی داده و خروجی‌ها **کاملاً جدا** می‌مانند:

```
output/
├── perplexity_tech.json / .csv / .md / .html   ← فقط پروکسپلکسیتی
├── images/                                     ← تصاویر پروکسپلکسیتی
├── gnews.json / .csv / .md / .html             ← فقط گوگل‌نیوز
├── gnews-images/                               ← تصاویر گوگل‌نیوز
site/
├── index.html                                  ← هاب (سوییچر + گروه‌بندی روزانه)
└── archive/hub-YYYYMMDD-HHMM.html
```

```bash
# فقط ساخت هاب از داده‌های موجود
python build_hub.py

# اول هر دو منبع را اسکرپ کن، بعد هاب را بساز
python build_hub.py --refresh --limit 10

# مسیرهای دلخواه
python build_hub.py --perplexity output/perplexity_tech.json \
                    --gnews output/gnews.json --out site/index.html
```

* **تم دارک** کامل (بدون asset خارجی) با گرادیان‌های نرم، کارت‌های شیشه‌ای و رنگ اختصاصی هر منبع
  (بنفش = Perplexity، سبز = G News).
* سوییچر **وسط‌چین و چسبان** با «قرص» متحرک؛ سه گزینه: **All** (شمارنده کل) · **Perplexity** · **G News** —
  انتخاب در `#hash` ذخیره می‌شود و با کلیدهای ← → هم عوض می‌شود.
* تاریخ‌ها **شمسی** (تبدیل درون‌خط، بدون وابستگی به Intl) و ساعت با ارقام فارسی؛ متن‌های لاتین با
  `unicode-bidi:plaintext` درست چیده می‌شوند.
* مارک‌داون ساده (`**پررنگ**` و `` `کد` ``) در خلاصه/گزارش/متن رندر می‌شود.
* اقلام بر اساس تاریخ نزولی گروه‌بندی می‌شوند («Wednesday, 04 November 2026»).
* هر کارت برچسب منبع دارد؛ محتوای هر منبع با فیلدهای خودش نمایش داده می‌شود
  (Perplexity: Summary + Report · G News: Description + متن خبر + منابع).
* تصاویر به‌صورت base64 درون صفحه (تا `--inline-limit` مورد برای هر منبع)، بدون هیچ asset خارجی،
  پس آفلاین و در پیش‌نمایش هم درست نمایش داده می‌شود.
* JSON/CSV هر منبع دست‌نخورده و جدا باقی می‌ماند؛ هاب فقط «نمای» ترکیبی است.


---

## 🤖 اتوماسیون با GitHub Actions

| Workflow | تریگر | کار |
|---|---|---|
| [`ci.yml`](.github/workflows/ci.yml) | push / PR | lint (ruff) + tests روی Python 3.10–3.13 + smoke scrape واقعی روی main |
| [`scrape.yml`](.github/workflows/scrape.yml) | cron هر ۶ ساعت + دستی | اسکرپ، کامیت خودکار داده در `output/`، آپلود آرتیفکت، انتشار اختیاری روی Pages |
| [`release.yml`](.github/workflows/release.yml) | تگ `v*.*.*` | تست، build با `python -m build`، `twine check`، ساخت GitHub Release |
| [`docker.yml`](.github/workflows/docker.yml) | push / PR | build تستی + انتشار ایمیج در `ghcr.io` |
| [`gnews.yml`](.github/workflows/gnews.yml) | cron هر ۳ ساعت + دستی | اسکرپ فید Google News، خلاصه در Job Summary، کامیت داده، آرتیفکت |

> صفحات تک‌منبع (`perplexity_tech.html` و `gnews.html`) هم همان تم دارک «نبض فناوری» را دارند.

> `scrape.yml` حالا هر دو منبع را جدا اسکرپ می‌کند و در پایان `build_hub.py` صفحه‌ی هاب را
> در `site/index.html` می‌سازد (برای Pages).

### راه‌اندازی Pages (یک‌بار)

1. `Settings → Pages → Build and deployment → Source: **GitHub Actions**`
2. اجرای دستی `Scrape Discover` با `publish_pages = true`
3. آدرس: `https://USERNAME.github.io/perplexity-discover-scraper/` (آرشیو در `/archive/`)

> اگر Pages فعال نباشد، استپ «Ensure Pages is enabled» با API تلاش می‌کند فعالش کند و در صورت نبود دسترسی فقط لاگ می‌دهد (workflow fail نمی‌شود).

### استفاده به‌عنوان Composite Action در ریپوی دیگر

```yaml
- id: discover
  uses: USERNAME/perplexity-discover-scraper/actions/scrape@main
  with:
    category: tech
    limit: 10
    images: "true"
    artifact-name: discover-tech

- run: echo "scraped ${{ steps.discover.outputs.count }} → ${{ steps.discover.outputs.json-path }}"
```

نمونه‌ی کامل: [`scripts/demo-action.yml`](scripts/demo-action.yml)

### Secrets لازم

| نام | اجباری؟ | کاربرد |
|---|---|---|
| `GITHUB_TOKEN` | خودکار | کامیت داده، آپلود آرتیفکت، Pages، GHCR |
| `PYPI_API_TOKEN` | خیر | فقط اگر بخواهید در PyPI هم منتشر کنید |

---

## 🐳 Docker

```bash
docker build -t perplexity-discover-scraper .
docker run --rm -v "$PWD/output:/data/output" perplexity-discover-scraper \
  --category tech --out /data/output

# یا
docker compose run --rm scraper --category finance
```

مثال cron (هر ۶ ساعت):

```cron
0 */6 * * * cd /path/to/repo && docker compose run --rm scraper --category tech
```

---

## 🧪 تست و کیفیت کد

```bash
pytest --cov=pdx --cov=gnews --cov-report=term-missing   # ۶۴ تست، بدون مرورگر/شبکه
ruff check . && ruff format --check .
```

پوشش تست: پاک‌سازی مارک‌داون، `humanize_age`، پارس `report_sections`/`sources`، حذف تکراری منابع، رندر CSV/JSON/MD/HTML، escape شدن XSS، مسیر `--from-json` و ساخت خروجی Pages.

```
perplexity-discover-scraper/
├── pdx/
│   ├── parser.py            # خالص: JSON → dict (قابل تست)
│   ├── render.py            # JSON/CSV/MD/HTML
│   └── browser.py           # فقط اینجا مرورگر لازم است
├── gnews/
│   ├── feed.py              # RSS parse + باز کردن لینک گوگل + استخراج تصویر/متن
│   └── render.py            # JSON/CSV/MD/HTML گوگل‌نیوز
├── pdx/hub.py                   # نمای ترکیبی برای صفحه‌ی هاب
├── build_hub.py                 # CLI هاب (All / Perplexity / G News)
├── perplexity_tech_scraper.py   # CLI پروکسپلکسیتی (تصویر + Summary + Report)
├── gnews_scraper.py             # CLI گوگل‌نیوز (title/link/image/text/description)
├── perplexity_discover.py       # نمونه‌ی سبک صفحه‌ی اصلی
├── scrapling_demo.py            # تست سلامت نصب Scrapling
├── tests/                       # ۲۸ تست + fixture واقعی API
├── actions/scrape/action.yml    # Composite Action
├── .github/workflows/           # ci · scrape · release · docker
├── Dockerfile · docker-compose.yml
└── pyproject.toml · Makefile · requirements*.txt
```

---

## 📦 استفاده به‌عنوان کتابخانه

```python
from pdx import render_html, render_markdown
from pdx.browser import download_image, fetch_api_payloads
from pdx.parser import collect_items

payloads, order = fetch_api_payloads(category="tech", limit=5)
items = collect_items(payloads, order=order, category="tech")
for item in items:
    item["image_file"] = download_image(item["image_url"], item["slug"], "output/images")

open("output/tech.html", "w", encoding="utf-8").write(render_html(items, "tech"))
```

## ⚖️ نکات حقوقی

این پروژه برای استفاده‌ی شخصی/پژوهشی نوشته شده و فقط از اندپوینت‌های **عمومی خود سایت** استفاده می‌کند.
لطفاً `robots.txt` و شرایط استفاده‌ی Perplexity و ناشران را رعایت کنید، درخواست‌ها را محدود (rate-limit) نگه دارید و
محتوای استخراج‌شده را بازنشر نکنید. تصاویر متعلق به ناشران اصلی هستند (اعتبار در `image_credit`).

## 📄 لایسنس

MIT — فایل [LICENSE](LICENSE).
