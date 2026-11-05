#!/usr/bin/env bash
# دیپلوی کامل Cloudflare Worker + ساخت KV — یک دستور
#
#   export CLOUDFLARE_API_TOKEN=...      # توکن با دسترسی Workers Scripts:Edit و Workers KV Storage:Edit
#   export CLOUDFLARE_ACCOUNT_ID=...     # از داشبورد کلادفلر (کنار نام حساب)
#   bash cloudflare/deploy.sh
#
# اگر wrangler از قبل لاگین است (npx wrangler login)، دو متغیر بالا لازم نیست.
set -euo pipefail

cd "$(dirname "$0")"

if [ -n "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
  echo "→ account: ${CLOUDFLARE_ACCOUNT_ID}"
fi

echo "→ ساخت/یافتن namespace برای HUB ..."
KV_JSON=$(npx --yes wrangler@3 kv namespace list 2>/dev/null || echo "[]")
KV_ID=$(python3 - "$KV_JSON" <<'PY'
import json, sys
try:
    namespaces = json.loads(sys.argv[1])
except Exception:
    namespaces = []
for ns in namespaces:
    if ns.get("title") in ("HUB", "nabz-worker-HUB"):
        print(ns["id"]); break
PY
)

if [ -z "${KV_ID}" ]; then
  echo "→ ساخته نشد، ایجاد می‌کنیم ..."
  OUT=$(npx --yes wrangler@3 kv namespace create HUB 2>&1 || true)
  echo "$OUT"
  KV_ID=$(echo "$OUT" | grep -oE '[0-9a-f]{32}' | head -1 || true)
fi

if [ -n "${KV_ID}" ]; then
  echo "→ KV namespace: ${KV_ID}"
  python3 - "$KV_ID" <<'PY'
import re, sys, pathlib
kv = sys.argv[1]
p = pathlib.Path("wrangler.toml")
text = p.read_text(encoding="utf-8")
block = f'[[kv_namespaces]]\nbinding = "HUB"\nid = "{kv}"\n'
if "[[kv_namespaces]]" in text:
    text = re.sub(r"\[\[kv_namespaces\]\][^\[]*", block, text)
else:
    text = text.replace("[observability]", block + "\n[observability]")
p.write_text(text, encoding="utf-8")
print("wrangler.toml به‌روزرسانی شد")
PY
else
  echo "! KV_ID پیدا نشد — ورکر بدون KV هم کار می‌کند (fallback به GitHub raw)"
fi

echo "→ دیپلوی ..."
npx --yes wrangler@3 deploy

echo
echo "✅ تمام. آدرس‌ها:"
npx --yes wrangler@3 deployments list 2>/dev/null | head -5 || true
echo "   https://nabz-worker.<subdomain>.workers.dev/"
echo "   https://nabz-worker.<subdomain>.workers.dev/api/news"
