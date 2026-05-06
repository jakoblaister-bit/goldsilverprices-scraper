"""
patch_swan_jaggards.py
Fixes URL/availability/price issues found by validate_non_tier1.py:

Swan Bullion:
  - Adds 6 missing buy_urls
  - Marks all gold bars/coins as available=false (verified out of stock on site)

Jaggards:
  - Fixes Philharmonic 1oz gold URL + price
  - Deletes ghost entries (no real page on site): Krugerrand, Britannia, Maple Leaf gold 1oz,
    silver bar 1oz, silver Maple Leaf, silver Britannia, 1990 Kookaburra
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


def patch(filters: dict, updates: dict):
    """PATCH rows matching filters with updates dict."""
    qs = "&".join(
        f"{k}=eq.{urllib.parse.quote(str(v))}" if v is not None
        else f"{k}=is.null"
        for k, v in filters.items()
    )
    status, body = req("PATCH", f"{TABLE}?{qs}", updates)
    return status


def delete(filters: dict):
    """DELETE rows matching filters."""
    qs = "&".join(
        f"{k}=eq.{urllib.parse.quote(str(v))}" if v is not None
        else f"{k}=is.null"
        for k, v in filters.items()
    )
    status, body = req("DELETE", f"{TABLE}?{qs}")
    return status


# ── Swan Bullion ───────────────────────────────────────────────────────────────

def fix_swan():
    print("\n── Swan Bullion ──")

    # Missing URLs: all verified out of stock on the site
    missing_urls = [
        # (filters,  url)
        ({"dealer": "Swan Bullion", "metal": "gold", "category": "bar",
          "bar_brand": "Perth Mint", "bar_type": "minted", "weight_oz": 0.1607527},
         "https://swanbullion.com/perth-mint-5g-gold-minted-bar/"),

        ({"dealer": "Swan Bullion", "metal": "gold", "category": "bar",
          "bar_brand": "Perth Mint", "bar_type": "minted", "weight_oz": 0.643015},
         "https://swanbullion.com/perth-mint-20g-gold-minted-bar/"),

        ({"dealer": "Swan Bullion", "metal": "gold", "category": "bar",
          "bar_brand": "Perth Mint", "bar_type": "minted", "weight_oz": 1.0},
         "https://swanbullion.com/perth-mint-1oz-gold-minted-bar/"),

        ({"dealer": "Swan Bullion", "metal": "gold", "category": "bar",
          "bar_brand": "Perth Mint", "bar_type": "cast", "weight_oz": 1.0},
         "https://swanbullion.com/perth-mint-1oz-gold-cast-bar/"),

        ({"dealer": "Swan Bullion", "metal": "gold", "category": "bar",
          "bar_brand": "Perth Mint", "bar_type": "minted", "weight_oz": 1.607527},
         "https://swanbullion.com/perth-mint-50g-gold-minted-bar/"),

        ({"dealer": "Swan Bullion", "metal": "gold", "category": "coin",
          "coin_type": "Krugerrand"},
         "https://swanbullion.com/south-african-krugerrand-1oz-gold-coin/"),
    ]

    for filters, url in missing_urls:
        status = patch(filters, {"buy_url": url, "available": False})
        label = filters.get("coin_type") or f"{filters.get('bar_brand')} {filters.get('bar_type')} {filters.get('weight_oz')}oz"
        ok = status in (200, 204)
        print(f"  {'✓' if ok else '✗'} Swan URL+unavailable patched: {label}  [{status}]")

    # Also mark the Kangaroo 1oz gold as unavailable (verified out of stock)
    status = patch(
        {"dealer": "Swan Bullion", "metal": "gold", "category": "coin", "coin_type": "Kangaroo"},
        {"available": False}
    )
    print(f"  {'✓' if status in (200,204) else '✗'} Swan Kangaroo 1oz gold marked unavailable  [{status}]")


# ── Jaggards ──────────────────────────────────────────────────────────────────

def fix_jaggards():
    print("\n── Jaggards ──")

    # Fix Philharmonic: real page exists at correct URL with price $6,578
    status = patch(
        {"dealer": "Jaggards", "metal": "gold", "category": "coin", "coin_type": "Philharmonic"},
        {
            "buy_url":   "https://www.jaggards.com.au/product/1oz-austrian-gold-philharmonic-coin/",
            "buy_price": 6578.00,
            "available": False,   # verified out of stock
        }
    )
    print(f"  {'✓' if status in (200,204) else '✗'} Jaggards Philharmonic URL+price fixed  [{status}]")

    # Delete ghost entries — products that have no real page on Jaggards site
    ghosts = [
        {"dealer": "Jaggards", "metal": "gold",   "category": "coin", "coin_type": "Krugerrand"},
        {"dealer": "Jaggards", "metal": "gold",   "category": "coin", "coin_type": "Britannia"},
        {"dealer": "Jaggards", "metal": "gold",   "category": "coin", "coin_type": "Maple Leaf"},
        {"dealer": "Jaggards", "metal": "silver",  "category": "bar",  "bar_brand": "Perth Mint", "bar_type": "cast", "weight_oz": 1.0},
        {"dealer": "Jaggards", "metal": "silver",  "category": "coin", "coin_type": "Maple Leaf"},
        {"dealer": "Jaggards", "metal": "silver",  "category": "coin", "coin_type": "Britannia"},
    ]
    for filters in ghosts:
        status = delete(filters)
        label = filters.get("coin_type") or f"{filters.get('bar_brand')} {filters.get('bar_type')}"
        print(f"  {'✓' if status in (200,204) else '✗'} Deleted ghost: {filters['metal']} {label}  [{status}]")

    # Fix Kookaburra silver: 1990 vintage coin URL → delete (no 2026 Kookaburra on Jaggards)
    status = delete({
        "dealer": "Jaggards", "metal": "silver", "category": "coin", "coin_type": "Kookaburra"
    })
    print(f"  {'✓' if status in (200,204) else '✗'} Deleted 1990 vintage Kookaburra entry  [{status}]")


if __name__ == "__main__":
    fix_swan()
    fix_jaggards()
    print("\nDone ✅")