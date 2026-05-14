"""
push_bullionstar.py
Fetches BullionStar NZ products and live 1-piece prices, then upserts to Supabase.

Run:  python push_bullionstar.py
"""

import json, urllib.request, urllib.error
from datetime import datetime, timezone
from scrape_bullionstar import fetch_products, DEALER

SUPABASE_URL = "https://cjxkhvkvhgnlnviykoad.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNqeGtodmt2aGdubG52aXlrb2FkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY1ODIyMDYsImV4cCI6MjA5MjE1ODIwNn0.eCg-JzEshidI-l7pVsumO_SsXbDOh_s--zvH1jc78g0"
TABLE = f"{SUPABASE_URL}/rest/v1/prices_v2"

HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=minimal",
}

# Rough sanity bounds — price per oz should be between spot×1.0 and spot×1.6
SPOT = {"gold": 6200, "silver": 97}


def request(method, url, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req  = urllib.request.Request(url, data=body, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def delete_dealer():
    encoded = DEALER.replace(" ", "%20")
    status, body = request("DELETE", f"{TABLE}?dealer=eq.{encoded}")
    if status in (200, 204):
        print(f"  ✓ Deleted existing {DEALER} rows")
    else:
        raise RuntimeError(f"DELETE failed {status}: {body[:200]}")


def insert_rows(rows):
    status, body = request("POST", TABLE, rows)
    if status in (200, 201):
        print(f"  ✓ Inserted {len(rows)} rows")
    else:
        raise RuntimeError(f"INSERT failed {status}: {body[:300]}")


def weight_g_from_label(label):
    if not label:
        return None
    if label.endswith("g") and not label.endswith("kg"):
        try:
            return float(label[:-1])
        except ValueError:
            return None
    return None


def is_price_sane(metal, price, weight_oz):
    spot = SPOT.get(metal, 0)
    if not spot or not weight_oz:
        return True
    poz = price / weight_oz
    return spot * 1.0 < poz < spot * 1.60


def push():
    print(f"Fetching {DEALER} products and prices…")
    scraped = fetch_products()
    print(f"  {len(scraped)} products fetched")

    scraped_at = datetime.now(timezone.utc).isoformat()
    db_rows    = []
    skipped    = []

    for p in scraped:
        if not is_price_sane(p["metal"], p["buy_price"], p["weight_oz"]):
            skipped.append(p)
            continue
        db_rows.append({
            "dealer":       DEALER,
            "metal":        p["metal"],
            "category":     p["category"],
            "coin_type":    p.get("coin_type"),
            "bar_brand":    p.get("bar_brand"),
            "bar_type":     p.get("bar_type"),
            "weight_oz":    p["weight_oz"],
            "weight_g":     weight_g_from_label(p.get("weight_label")),
            "weight_label": p.get("weight_label"),
            "year":         p.get("year"),
            "buy_price":    p["buy_price"],
            "sell_price":   p.get("sell_price"),
            "buy_url":      p.get("buy_url"),
            "available":    p.get("available", True),
            "scraped_at":   scraped_at,
        })

    if skipped:
        print(f"  ⚠ {len(skipped)} rows failed sanity check:")
        for p in skipped:
            label = p.get("coin_type") or p.get("bar_brand")
            print(f"    {p['metal']} {label}  ${p['buy_price']:.2f}  {p['weight_oz']}oz")

    if not db_rows:
        print("  No valid rows to push — aborting")
        return

    print("Pushing to Supabase…")
    delete_dealer()
    insert_rows(db_rows)

    coins  = sum(1 for r in db_rows if r["category"] == "coin")
    bars   = sum(1 for r in db_rows if r["category"] == "bar")
    gold   = sum(1 for r in db_rows if r["metal"] == "gold")
    silver = sum(1 for r in db_rows if r["metal"] == "silver")
    print(f"\n  gold={gold}  silver={silver}  coins={coins}  bars={bars}")
    print("Done ✅")


if __name__ == "__main__":
    push()