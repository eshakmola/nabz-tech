#!/usr/bin/env python3
"""شناسه‌ی KV را در wrangler.toml می‌نویسد (برای استفاده در CI و deploy.sh)."""
import pathlib
import re
import sys

if len(sys.argv) < 2 or not re.fullmatch(r"[0-9a-f]{32}", sys.argv[1]):
    raise SystemExit("usage: wire-kv.py <32-hex KV namespace id>")

kv = sys.argv[1]
p = pathlib.Path(__file__).with_name("wrangler.toml")
text = p.read_text(encoding="utf-8")
block = f'[[kv_namespaces]]\nbinding = "HUB"\nid = "{kv}"\n'
text = (
    re.sub(r"\[\[kv_namespaces\]\][^\[]*", block, text)
    if "[[kv_namespaces]]" in text
    else text.replace("[triggers]", block + "\n[triggers]")
)
p.write_text(text, encoding="utf-8")
print(f"✓ KV wired: {kv}")
