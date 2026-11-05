#!/usr/bin/env bash
# دیپلوی کامل: بررسی توکن → پیدا کردن Account ID → ساخت KV → دیپلوی → تست
#
#   export CLOUDFLARE_API_TOKEN=...      # Workers Scripts:Edit + Workers KV Storage:Edit
#   bash cloudflare/deploy.sh
#
# اگر wrangler از قبل لاگین است (npx wrangler login)، توکن لازم نیست.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '%s\n' "$*"; }
die() { printf '✘ %s\n' "$*" >&2; exit 1; }

# ---------- ۱) احراز هویت ----------
if [ -n "${CLOUDFLARE_API_TOKEN:-}" ]; then
  say "→ بررسی توکن ..."
  VERIFY=$(curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
    https://api.cloudflare.com/client/v4/user/tokens/verify || true)
  case "$VERIFY" in
    *'"success":true'*) say "  ✓ توکن معتبر است" ;;
    *) die "توکن کلادفلر معتبر نیست → $VERIFY" ;;
  esac
fi

# ---------- ۲) Account ID ----------
if [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
  say "→ پیدا کردن Account ID ..."
  CLOUDFLARE_ACCOUNT_ID=$(curl -s -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN:-}" \
    https://api.cloudflare.com/client/v4/accounts |
    python3 -c "import json,sys;d=json.load(sys.stdin);print((d.get('result') or [{}])[0].get('id',''))" || true)
  export CLOUDFLARE_ACCOUNT_ID
fi
[ -n "${CLOUDFLARE_ACCOUNT_ID:-}" ] || die "Account ID پیدا نشد؛ آن را export کنید."
say "  account: $CLOUDFLARE_ACCOUNT_ID"

# ---------- ۳) KV namespace ----------
say "→ بررسی/ساخت namespace برای HUB ..."
LIST=$(npx --yes wrangler@3 kv namespace list 2>/dev/null || echo "[]")
KV_ID=$(printf '%s' "$LIST" | python3 -c "
import json, sys
try:
    ns = json.load(sys.stdin)
except Exception:
    ns = []
for n in ns:
    if n.get('title') in ('HUB', 'nabz-worker-HUB'):
        print(n['id']); break
" || true)

if [ -z "$KV_ID" ]; then
  OUT=$(npx --yes wrangler@3 kv namespace create HUB 2>&1 || true)
  printf '%s\n' "$OUT"
  KV_ID=$(printf '%s' "$OUT" | grep -oE '[0-9a-f]{32}' | head -1 || true)
fi
[ -n "$KV_ID" ] || die "ساخت KV ناموفق بود."
say "  KV: $KV_ID"

python3 wire-kv.py "$KV_ID"

# ---------- ۴) دیپلوی ----------
say "→ دیپلوی ..."
npx --yes wrangler@3 deploy

# ---------- ۵) تست ----------
say ""
say "✅ دیپلوی انجام شد. تست:"
say "   curl https://nabz-worker.<subdomain>.workers.dev/health"
say "   curl https://nabz-worker.<subdomain>.workers.dev/api/meta    # وضعیت کران ساعتی"
say ""
say "⏰ کران کلادفلر هر ساعت اجرا می‌شود (crons = \"5 * * * *\") و خبرهای تازه را در KV ذخیره می‌کند."
