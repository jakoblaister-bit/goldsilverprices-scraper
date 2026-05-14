"""
push_all.py
Runs all dealer scrapers in sequence — Tier 1 (every 3 hrs via CI) and
Tier 2 (HTML-scraped, same pipeline).

Run:  python push_all.py
"""

import json as _json, urllib.request as _urllib_req
from datetime import datetime as _dt, timezone as _tz

_SUPABASE_URL = "https://cjxkhvkvhgnlnviykoad.supabase.co"
_SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNqeGtodmt2aGdubG52aXlrb2FkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY1ODIyMDYsImV4cCI6MjA5MjE1ODIwNn0.eCg-JzEshidI-l7pVsumO_SsXbDOh_s--zvH1jc78g0"
_DB_HEADERS = {
    "apikey": _SUPABASE_KEY, "Authorization": f"Bearer {_SUPABASE_KEY}",
    "Content-Type": "application/json", "Prefer": "return=minimal",
}

def _fetch_live_spot():
    results = {}
    for metal, symbol in (("gold", "XAU"), ("silver", "XAG")):
        try:
            req = _urllib_req.Request(
                f"https://api.gold-api.com/price/{symbol}/AUD",
                headers={"User-Agent": "goldsilverprices.com.au/scraper"},
            )
            with _urllib_req.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read().decode())
                price = data.get("price")
                if price and float(price) > 0:
                    results[metal] = float(price)
        except Exception as e:
            print(f"  [SPOT FETCH] {metal}: {e}")
    return results if results else None

def _save_spot_to_db(spot):
    now = _dt.now(_tz.utc).isoformat()
    for metal, price_aud in spot.items():
        try:
            payload = _json.dumps({"metal": metal, "price_aud": price_aud, "scraped_at": now}).encode()
            req = _urllib_req.Request(
                f"{_SUPABASE_URL}/rest/v1/spot_prices",
                data=payload, headers=_DB_HEADERS, method="POST",
            )
            _urllib_req.urlopen(req, timeout=10)
        except Exception as e:
            print(f"  [SPOT SAVE] {metal}: {e}")

print("=" * 60)
print("  Fetching live spot prices...")
_spot = _fetch_live_spot()
if _spot:
    _save_spot_to_db(_spot)
    print("  " + "  ".join(f"{m.capitalize()}: A${p:,.0f}" for m, p in _spot.items()))
else:
    print("  ! Spot fetch failed - dealers will use their own estimates")
print("=" * 60)
print()

import sys
from snapshot_daily import run as daily_snapshot
from push_ainslie import push as push_ainslie
from push_goldstackers import push as push_goldstackers
from push_gba import push as push_gba
from push_swan import push as push_swan
from push_abc import push as push_abc
from push_jaggards import push as push_jaggards
from push_guardian import push as push_guardian
from push_perth import push as push_perth
from push_kjc import push as push_kjc
from push_bullionstar import push as push_bullionstar

dealers = [
    ("Ainslie Bullion",        push_ainslie),
    ("Gold Stackers",          push_goldstackers),
    ("Gold Bullion Australia",  push_gba),
    ("Swan Bullion",            push_swan),
    ("ABC Bullion",             push_abc),
    ("Jaggards",                push_jaggards),
    ("Guardian Gold",           push_guardian),
    ("Perth Mint",              push_perth),
    ("KJC Bullion",             push_kjc),
    ("BullionStar",             push_bullionstar),
]

errors = []
for name, fn in dealers:
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    try:
        fn()
    except Exception as e:
        print(f"  ERROR: {e}")
        errors.append(name)

print(f"\n{'='*60}")
if errors:
    print(f"FAILED: {', '.join(errors)}")
    sys.exit(1)
else:
    print("All dealers updated ✅")

try:
    daily_snapshot()
except Exception as e:
    print(f"\nSnapshot warning (non-fatal): {e}")