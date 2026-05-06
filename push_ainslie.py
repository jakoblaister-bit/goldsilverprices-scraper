"""
push_ainslie.py
Scrapes ainsliebullion.com.au/Charts, maps to prices_v2 schema,
deletes all existing Ainslie rows, then bulk-inserts fresh data.

Run:  python push_ainslie.py
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from scrape_ainslie import fetch_products

SUPABASE_URL = "https://cjxkhvkvhgnlnviykoad.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNqeGtodmt2aGdubG52aXlrb2FkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY1ODIyMDYsImV4cCI6MjA5MjE1ODIwNn0.eCg-JzEshidI-l7pVsumO_SsXbDOh_s--zvH1jc78g0"
TABLE = f"{SUPABASE_URL}/rest/v1/prices_v2"

HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=minimal",
}


# ── Field mapping ─────────────────────────────────────────────────────────────

def split_bar_product_type(product_type):
    """'Perth Mint minted' → ('Perth Mint', 'minted')  etc."""
    special = {
        "Perth Mint (AO) cast": ("Perth Mint AO", "cast"),
        "Ainslie stacker":      ("Ainslie",        "stacker"),
    }
    if product_type in special:
        return special[product_type]
    # Generic: everything before last space = brand, last word = type
    parts = product_type.rsplit(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (product_type, None)


def to_db_row(row, scraped_at):
    is_coin = row["category"] == "coin"

    if is_coin:
        coin_type = row["product_type"]
        bar_brand = bar_type = None
    else:
        coin_type = None
        bar_brand, bar_type = split_bar_product_type(row["product_type"])

    return {
        "dealer":     "Ainslie Bullion",
        "metal":      row["metal"],
        "category":   "coin" if is_coin else "bar",
        "coin_type":  coin_type,
        "bar_brand":  bar_brand,
        "bar_type":   bar_type,
        "weight_oz":    row["weight_oz"],
        "weight_label": row["weight"],
        "buy_price":    row["buy_price"],
        "sell_price": row["sell_price"],
        "buy_url":    row["buy_url"],
        "available":  True,
        "scraped_at": scraped_at,
    }


# ── Supabase helpers ──────────────────────────────────────────────────────────

def request(method, url, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req  = urllib.request.Request(url, data=body, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def delete_ainslie():
    status, body = request("DELETE", f"{TABLE}?dealer=eq.Ainslie%20Bullion")
    if status in (200, 204):
        print("  ✓ Deleted existing Ainslie rows")
    else:
        raise RuntimeError(f"DELETE failed {status}: {body[:200]}")


def insert_rows(rows):
    status, body = request("POST", TABLE, rows)
    if status in (200, 201):
        print(f"  ✓ Inserted {len(rows)} rows")
    else:
        raise RuntimeError(f"INSERT failed {status}: {body[:300]}")


# ── Main ──────────────────────────────────────────────────────────────────────

def push():
    print("Scraping Ainslie Charts page…")
    scraped = fetch_products()
    print(f"  {len(scraped)} products parsed")

    scraped_at = datetime.now(timezone.utc).isoformat()
    db_rows = [to_db_row(r, scraped_at) for r in scraped]

    print("Pushing to Supabase…")
    delete_ainslie()
    insert_rows(db_rows)

    # Summary
    coins = sum(1 for r in db_rows if r["category"] == "coin")
    bars  = sum(1 for r in db_rows if r["category"] == "bar")
    with_sell = sum(1 for r in db_rows if r["sell_price"])
    print(f"\n  coins={coins}  bars={bars}  sell_price populated={with_sell}")
    print("Done ✅")


if __name__ == "__main__":
    push()