"""
push_kjc.py
Scrapes KJC Bullion category pages, deletes all existing KJC rows,
then bulk-inserts fresh data.

Run:  python push_kjc.py
"""

import json, urllib.request, urllib.error
from datetime import datetime, timezone
from scrape_kjc import fetch_products, DEALER

SUPABASE_URL = "https://cjxkhvkvhgnlnviykoad.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNqeGtodmt2aGdubG52aXlrb2FkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY1ODIyMDYsImV4cCI6MjA5MjE1ODIwNn0.eCg-JzEshidI-l7pVsumO_SsXbDOh_s--zvH1jc78g0"
TABLE = f"{SUPABASE_URL}/rest/v1/prices_v2"

HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=minimal",
}


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
    if label.endswith("kg"):
        return None
    if label.endswith("g"):
        try:
            return float(label[:-1])
        except ValueError:
            return None
    return None


def to_db_row(r, scraped_at):
    return {
        "dealer":       DEALER,
        "metal":        r["metal"],
        "category":     r["category"],
        "coin_type":    r.get("coin_type"),
        "bar_brand":    r.get("bar_brand"),
        "bar_type":     r.get("bar_type"),
        "weight_oz":    r["weight_oz"],
        "weight_g":     weight_g_from_label(r["weight_label"]),
        "weight_label": r["weight_label"],
        "year":         r.get("year"),
        "buy_price":    r["buy_price"],
        "sell_price":   r.get("sell_price"),
        "buy_url":      r["buy_url"],
        "available":    True,
        "scraped_at":   scraped_at,
    }


def push():
    print(f"Scraping {DEALER} live prices…")
    scraped = fetch_products()
    print(f"  {len(scraped)} products parsed")

    before = len(scraped)
    scraped = [r for r in scraped if r.get("buy_price") and r["buy_price"] > 0]
    if len(scraped) < before:
        print(f"  {len(scraped)} with buy_price > 0  ({before - len(scraped)} dropped)")

    scraped_at = datetime.now(timezone.utc).isoformat()
    db_rows = [to_db_row(r, scraped_at) for r in scraped]

    print("Pushing to Supabase…")
    delete_dealer()
    insert_rows(db_rows)

    coins  = sum(1 for r in db_rows if r["category"] == "coin")
    bars   = sum(1 for r in db_rows if r["category"] != "coin")
    with_sell = sum(1 for r in db_rows if r["sell_price"])
    print(f"\n  coins={coins}  bars={bars}  sell_price populated={with_sell}")
    print("Done ✅")


if __name__ == "__main__":
    push()