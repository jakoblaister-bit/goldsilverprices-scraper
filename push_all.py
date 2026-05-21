"""
push_all.py
Runs all dealer scrapers in sequence — Tier 1 (every 3 hrs via CI) and
Tier 2 (HTML-scraped, same pipeline).

Run:  python push_all.py
"""

import json as _json, os as _os, urllib.request as _urllib_req, urllib.parse as _urllib_parse
from datetime import datetime as _dt, timezone as _tz

_BREVO_KEY  = _os.environ.get("BREVO_KEY", "")
_BREVO_LIST = 3
_ALERT_FROM = "alerts@goldsilverprices.com.au"

def _brevo_headers():
    return {"api-key": _BREVO_KEY, "Content-Type": "application/json"}

def _get_lowest_dealer_prices():
    """Return {metal: lowest_buy_price} from Supabase after scraping."""
    prices = {}
    for metal in ("gold", "silver"):
        try:
            url = (f"{_SUPABASE_URL}/rest/v1/prices_v2"
                   f"?metal=eq.{metal}&available=eq.true&buy_price=gt.0"
                   f"&select=buy_price&order=buy_price.asc&limit=1")
            req = _urllib_req.Request(url, headers=_DB_HEADERS)
            with _urllib_req.urlopen(req, timeout=10) as resp:
                rows = _json.loads(resp.read().decode())
                if rows:
                    prices[metal] = float(rows[0]["buy_price"])
        except Exception as e:
            print(f"  [ALERTS] Price fetch ({metal}): {e}")
    return prices

def _check_price_alerts():
    print("\n  Checking price alerts...")
    dealer_prices = _get_lowest_dealer_prices()
    if not dealer_prices:
        print("  [ALERTS] No dealer prices available, skipping")
        return

    today = _dt.now(_tz.utc).strftime("%Y-%m-%d")

    try:
        url = f"https://api.brevo.com/v3/contacts/lists/{_BREVO_LIST}/contacts?limit=500"
        req = _urllib_req.Request(url, headers=_brevo_headers())
        with _urllib_req.urlopen(req, timeout=15) as resp:
            contacts = _json.loads(resp.read().decode()).get("contacts", [])
    except Exception as e:
        print(f"  [ALERTS] Fetch contacts failed: {e}")
        return

    fired = 0
    for c in contacts:
        attrs  = c.get("attributes") or {}
        metal  = (attrs.get("METAL") or "").lower()
        target = float(attrs.get("TARGET_PRICE") or 0)
        last_sent = attrs.get("LAST_ALERT_DATE") or ""

        if target <= 0 or metal not in dealer_prices:
            continue
        if last_sent == today:
            continue  # already emailed today

        current = dealer_prices[metal]
        if current > target:
            continue

        email = c.get("email", "")
        if not email:
            continue

        _send_alert_email(email, metal, target, current)
        _reset_alert(email, today)
        fired += 1

    print(f"  [ALERTS] {fired} alert(s) fired")

def _send_alert_email(email, metal, target, current):
    metal_cap = metal.capitalize()
    page_path = "gold-price" if metal == "gold" else "silver-price"
    html = f"""
<div style="font-family:system-ui,sans-serif;max-width:560px;margin:0 auto;padding:24px;color:#0F172A">
  <img src="https://goldsilverprices.com.au/icons.svg" alt="" width="32" height="32" style="margin-bottom:16px">
  <h2 style="margin:0 0 8px;color:#0F2D52;font-size:20px">Your {metal_cap} Price Alert</h2>
  <p style="color:#475569;font-size:14px;line-height:1.6;margin:0 0 20px">
    Good news. The {metal_cap.lower()} spot price has reached your target of
    <strong>A${target:,.2f}/oz</strong>.
  </p>
  <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:20px;margin-bottom:24px">
    <div style="font-size:12px;color:#64748B;margin-bottom:4px">Current {metal_cap} spot price (AUD)</div>
    <div style="font-size:30px;font-weight:800;color:#0F2D52">A${current:,.2f}<span style="font-size:15px;font-weight:400;color:#64748B">/oz</span></div>
    <div style="font-size:12px;color:#64748B;margin-top:8px">Your target: A${target:,.2f}/oz</div>
  </div>
  <a href="https://goldsilverprices.com.au/{page_path}"
     style="display:inline-block;background:#16A34A;color:#fff;text-decoration:none;padding:12px 24px;border-radius:8px;font-weight:700;font-size:14px">
    Compare {metal_cap} Dealer Prices
  </a>
  <p style="font-size:11px;color:#94A3B8;margin-top:28px;line-height:1.6">
    You set this alert at GoldSilverPrices.com.au. To set a new alert, visit the
    <a href="https://goldsilverprices.com.au/{page_path}" style="color:#94A3B8">{metal_cap} Price page</a>.
    Reply to this email to unsubscribe from alerts.
  </p>
</div>"""
    payload = _json.dumps({
        "sender": {"name": "GoldSilverPrices", "email": _ALERT_FROM},
        "to": [{"email": email}],
        "subject": f"{metal_cap} alert: A${current:,.0f}/oz reached your target",
        "htmlContent": html,
    }).encode()
    try:
        req = _urllib_req.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=payload, headers=_brevo_headers(), method="POST"
        )
        _urllib_req.urlopen(req, timeout=15)
        print(f"  [ALERT] Sent to {email}")
    except Exception as e:
        print(f"  [ALERT] Send failed ({email}): {e}")

def _reset_alert(email, today):
    encoded = _urllib_parse.quote(email, safe="")
    payload = _json.dumps({
        "attributes": {"TARGET_PRICE": 0, "LAST_ALERT_DATE": today}
    }).encode()
    try:
        req = _urllib_req.Request(
            f"https://api.brevo.com/v3/contacts/{encoded}",
            data=payload, headers=_brevo_headers(), method="PUT"
        )
        _urllib_req.urlopen(req, timeout=15)
    except Exception as e:
        print(f"  [ALERT] Reset failed ({email}): {e}")

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
# New dealers — comment out any entry below to disable that dealer without removing it
from push_bullionlist import push as push_bullionlist
from push_mgc import push as push_mgc
from push_imperial import push as push_imperial
from push_bullionnow import push as push_bullionnow

dealers = [
    # Existing dealers
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
    # New dealers (added 2026-05-20) — comment out individually to revert
    ("Bullion List",            push_bullionlist),
    ("Melbourne Gold Company",  push_mgc),
    ("Imperial Bullion",        push_imperial),
    ("Bullion Now",             push_bullionnow),
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

try:
    _check_price_alerts()
except Exception as e:
    print(f"\nAlert check warning (non-fatal): {e}")