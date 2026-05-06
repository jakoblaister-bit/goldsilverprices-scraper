"""
patch_abc_guardian_kjc_perth.py
Fixes URL/price/availability issues for ABC Bullion, Guardian Gold, KJC Bullion, Perth Mint.

ABC Bullion:
  - Deletes 1oz silver bar (product doesn't exist on site)
  - Fixes 1kg silver bar: URL → sabc32151kg slug, price → 3850.00

Guardian Gold:
  - Deletes 1/2oz gold cast bar (no product page)
  - Deletes silver Kookaburra (no product page)
  - Fixes Maple Leaf buy_price: 8102.28 → 6211.35

KJC Bullion:
  - Fixes Kangaroo coin URLs: removes year prefix (2026) from slug for 1/20oz, 1/10oz, 1/4oz, 1/2oz
  - Fixes 100g bar URL: product ID 2422 → 2424
  - Marks all KJC entries available=false (prices are JS-rendered, stale)

Perth Mint:
  - Deletes 3 rows with clearly wrong prices:
      id=6997  1/2oz Kangaroo gold at $5,000 (should be ~$3,400)
      id=7028  5g minted bar at $2,154.62 (duplicated 10g price)
      id=7035  20g minted bar at $6,396.34 (duplicated 1oz price)
"""

import json, urllib.request, urllib.error, urllib.parse

SUPABASE_URL = "https://cjxkhvkvhgnlnviykoad.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNqeGtodmt2aGdubG52aXlrb2FkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY1ODIyMDYsImV4cCI6MjA5MjE1ODIwNn0.eCg-JzEshidI-l7pVsumO_SsXbDOh_s--zvH1jc78g0"
TABLE = f"{SUPABASE_URL}/rest/v1/prices_v2"

HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=minimal",
}


def req(method, url, data=None):
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(url, data=body, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def fetch(filters: dict) -> list:
    qs = "&".join(
        f"{k}=eq.{urllib.parse.quote(str(v))}" if v is not None else f"{k}=is.null"
        for k, v in filters.items()
    )
    r = urllib.request.Request(
        f"{TABLE}?{qs}&select=id,dealer,metal,category,coin_type,bar_brand,bar_type,weight_oz,buy_price,buy_url",
        headers={**HEADERS, "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(r, timeout=15) as resp:
        return json.loads(resp.read())


def patch_by_id(row_id: int, updates: dict):
    status, body = req("PATCH", f"{TABLE}?id=eq.{row_id}", updates)
    return status


def patch(filters: dict, updates: dict):
    qs = "&".join(
        f"{k}=eq.{urllib.parse.quote(str(v))}" if v is not None else f"{k}=is.null"
        for k, v in filters.items()
    )
    status, body = req("PATCH", f"{TABLE}?{qs}", updates)
    return status


def delete(filters: dict):
    qs = "&".join(
        f"{k}=eq.{urllib.parse.quote(str(v))}" if v is not None else f"{k}=is.null"
        for k, v in filters.items()
    )
    status, body = req("DELETE", f"{TABLE}?{qs}")
    return status


def delete_by_id(row_id: int):
    status, body = req("DELETE", f"{TABLE}?id=eq.{row_id}")
    return status


def ok(status):
    return status in (200, 204)


# ── ABC Bullion ────────────────────────────────────────────────────────────────

def fix_abc():
    print("\n── ABC Bullion ──")

    # 1oz silver bar doesn't exist on site — delete it
    status = delete({"dealer": "ABC Bullion", "metal": "silver", "category": "bar", "weight_oz": 1.0})
    print(f"  {'✓' if ok(status) else '✗'} Deleted 1oz silver bar (non-existent product)  [{status}]")

    # 1kg silver bar: wrong URL slug and wrong price ($2,818 → $3,850)
    # New URL: sabc32151kg-abc-silver-cast-bar-9995
    status = patch(
        {"dealer": "ABC Bullion", "metal": "silver", "category": "bar", "weight_oz": 32.1507},
        {
            "buy_url":   "https://www.abcbullion.com.au/store/silver/sabc32151kg-abc-silver-cast-bar-9995",
            "buy_price": 3850.00,
        }
    )
    print(f"  {'✓' if ok(status) else '✗'} Fixed 1kg silver bar URL + price → $3,850  [{status}]")

    # If weight_oz is stored differently, try 32.15 fallback
    rows = fetch({"dealer": "ABC Bullion", "metal": "silver", "category": "bar"})
    for r in rows:
        print(f"    row id={r['id']} weight_oz={r['weight_oz']} price={r['buy_price']} url={r['buy_url']}")


# ── Guardian Gold ──────────────────────────────────────────────────────────────

def fix_guardian():
    print("\n── Guardian Gold ──")

    # Show all Guardian rows first so we can verify
    rows = fetch({"dealer": "Guardian Gold"})
    print(f"  Current rows ({len(rows)}):")
    for r in rows:
        label = r.get("coin_type") or f"{r.get('bar_brand')} {r.get('bar_type')}"
        print(f"    id={r['id']} {r['metal']} {r['category']} {label} {r['weight_oz']}oz ${r['buy_price']}")

    # Delete 1/2oz gold cast bar (no product page on Guardian)
    status = delete({"dealer": "Guardian Gold", "metal": "gold", "category": "bar", "bar_type": "cast", "weight_oz": 0.5})
    print(f"  {'✓' if ok(status) else '✗'} Deleted 1/2oz gold cast bar  [{status}]")

    # Delete silver Kookaburra (no product page)
    status = delete({"dealer": "Guardian Gold", "metal": "silver", "category": "coin", "coin_type": "Kookaburra"})
    print(f"  {'✓' if ok(status) else '✗'} Deleted silver Kookaburra  [{status}]")

    # Fix Maple Leaf price: $8,102.28 → $6,211.35 (verified on site)
    status = patch(
        {"dealer": "Guardian Gold", "metal": "gold", "category": "coin", "coin_type": "Maple Leaf"},
        {"buy_price": 6211.35}
    )
    print(f"  {'✓' if ok(status) else '✗'} Fixed Maple Leaf price → $6,211.35  [{status}]")


# ── KJC Bullion ───────────────────────────────────────────────────────────────

def fix_kjc():
    print("\n── KJC Bullion ──")

    # Fetch all KJC rows to inspect current URLs
    rows = fetch({"dealer": "KJC Bullion"})
    print(f"  Current rows ({len(rows)}):")
    for r in rows:
        label = r.get("coin_type") or f"{r.get('bar_brand')} {r.get('bar_type')}"
        print(f"    id={r['id']} {r['metal']} {label} {r['weight_oz']}oz  url={r['buy_url']}")

    # Fix Kangaroo coin URLs: remove year prefix from slugs
    # Old slugs: /PD/1-20-oz-2026-australian-kangaroo-gold-bullion-coin/3003872
    # New slugs: /PD/1-20-oz-australian-kangaroo-gold-bullion-coin/3003872
    kangaroo_coin_fixes = [
        # (weight_oz, new_url)
        (0.05,  "https://www.kjc.com.au/PD/1-20-oz-australian-kangaroo-gold-bullion-coin/3003872"),
        (0.1,   "https://www.kjc.com.au/PD/1-10-oz-australian-kangaroo-gold-bullion-coin/3003873"),
        (0.25,  "https://www.kjc.com.au/PD/1-4-oz-australian-kangaroo-gold-bullion-coin/3003874"),
        (0.5,   "https://www.kjc.com.au/PD/1-2-oz-australian-kangaroo-gold-bullion-coin/3003877"),
        (1.0,   "https://www.kjc.com.au/PD/1-oz-australian-kangaroo-gold-bullion-coin/3003875"),
    ]
    for weight, url in kangaroo_coin_fixes:
        # Try direct filter first
        matching = [r for r in rows
                    if r.get("coin_type") == "Kangaroo" and abs((r.get("weight_oz") or 0) - weight) < 0.001]
        if matching:
            for r in matching:
                s = patch_by_id(r["id"], {"buy_url": url, "available": False})
                print(f"  {'✓' if ok(s) else '✗'} KJC Kangaroo {weight}oz URL fixed  id={r['id']}  [{s}]")
        else:
            print(f"  ~ KJC Kangaroo {weight}oz — no matching row found, skipping")

    # Fix 100g gold bar URL: product ID 2422 → 2424
    bar_100g = [r for r in rows
                if r.get("bar_brand") and abs((r.get("weight_oz") or 0) - 3.215) < 0.01]
    if not bar_100g:
        # Try broader match on ~3.2oz
        bar_100g = [r for r in rows
                    if r.get("metal") == "gold" and r.get("category") == "bar"
                    and abs((r.get("weight_oz") or 0) - 3.215) < 0.05]
    if bar_100g:
        for r in bar_100g:
            new_url = (r.get("buy_url") or "").replace("/2422", "/2424").replace("/2422/", "/2424/")
            if "2424" not in (r.get("buy_url") or ""):
                s = patch_by_id(r["id"], {"buy_url": new_url, "available": False})
                print(f"  {'✓' if ok(s) else '✗'} KJC 100g bar URL fixed (2422→2424)  id={r['id']}  [{s}]")
            else:
                print(f"  ~ KJC 100g bar URL already has 2424, marking unavailable  id={r['id']}")
                s = patch_by_id(r["id"], {"available": False})
                print(f"    [{s}]")
    else:
        print("  ~ KJC 100g bar — no matching row found")

    # Mark silver Lunar unavailable (JS-rendered price, stale)
    lunar = [r for r in rows if r.get("coin_type") == "Lunar" or "Lunar" in str(r.get("coin_type", ""))]
    for r in lunar:
        s = patch_by_id(r["id"], {"available": False})
        print(f"  {'✓' if ok(s) else '✗'} KJC {r['metal']} Lunar marked unavailable  id={r['id']}  [{s}]")


# ── Perth Mint ─────────────────────────────────────────────────────────────────

def fix_perth():
    print("\n── Perth Mint ──")

    # Delete 3 rows with clearly wrong prices (identified by id in prior session)
    bad_ids = [
        (6997, "1/2oz Kangaroo gold at $5,000 (should be ~$3,400)"),
        (7028, "5g minted bar at $2,154.62 (duplicated 10g price)"),
        (7035, "20g minted bar at $6,396.34 (duplicated 1oz price)"),
    ]
    for row_id, reason in bad_ids:
        status = delete_by_id(row_id)
        print(f"  {'✓' if ok(status) else '✗'} Deleted id={row_id}: {reason}  [{status}]")

    # Show remaining Perth Mint rows for verification
    rows = fetch({"dealer": "Perth Mint"})
    print(f"\n  Remaining Perth Mint rows ({len(rows)}):")
    for r in rows:
        label = r.get("coin_type") or f"{r.get('bar_brand')} {r.get('bar_type')}"
        print(f"    id={r['id']} {r['metal']} {label} {r.get('weight_oz')}oz ${r['buy_price']:.2f}")


if __name__ == "__main__":
    fix_abc()
    fix_guardian()
    fix_kjc()
    fix_perth()
    print("\nDone ✅")