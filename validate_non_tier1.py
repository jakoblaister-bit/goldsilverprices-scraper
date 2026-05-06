"""
validate_non_tier1.py
Checks all non-Tier-1 dealer rows in the DB for:
  1. Spot-price sanity  — price suspiciously close to spot (Jaggards bug) or below spot (buyback bug)
  2. Cross-dealer outlier — price >20% below Tier 1 average for same product
  3. URL reachability   — HEAD request, checks for 200 and that final URL isn't a homepage/category

Run:  python validate_non_tier1.py
"""

import json, urllib.request, urllib.error

SUPABASE_URL = "https://cjxkhvkvhgnlnviykoad.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNqeGtodmt2aGdubG52aXlrb2FkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY1ODIyMDYsImV4cCI6MjA5MjE1ODIwNn0.eCg-JzEshidI-l7pVsumO_SsXbDOh_s--zvH1jc78g0"

TIER1 = {"Ainslie Bullion", "Gold Stackers", "Gold Bullion Australia"}

# Approximate AUD spot — used only as a sanity floor, not for exact comparison
SPOT = {"gold": 6200, "silver": 97}

# Multipliers per oz for each metal
OZ_PER_G = 1 / 31.1035


def fetch_all():
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/prices_v2?select=*&order=dealer,metal,category,weight_oz",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept": "application/json",
        }
    )
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def spot_per_oz(metal):
    return SPOT.get(metal, 0)


def price_per_oz(row):
    """Normalise buy_price to a per-oz figure."""
    oz = row.get("weight_oz") or 0
    if oz <= 0:
        return None
    return row["buy_price"] / oz


def product_key(row):
    """Key that matches the same product across dealers."""
    if row["category"] == "coin":
        return (row["metal"], "coin", row.get("coin_type") or "", round(row.get("weight_oz") or 0, 4))
    return (row["metal"], "bar", row.get("bar_brand") or "", row.get("bar_type") or "", round(row.get("weight_oz") or 0, 4))


def check_url(url, timeout=8):
    """Returns (status_code, final_url, flag_msg)."""
    if not url:
        return None, None, "WARN: no URL stored"
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            final = r.url
            status = r.status
    except urllib.error.HTTPError as e:
        return e.code, url, f"WARN: HTTP {e.code}"
    except Exception as e:
        return None, url, f"WARN: {e}"

    # Heuristic: if final URL has no path beyond domain it's likely a homepage
    from urllib.parse import urlparse
    path = urlparse(final).path.rstrip("/")
    if path in ("", "/"):
        return status, final, "WARN: redirected to homepage"
    # Category pages typically end in a short path with no product slug
    if len(path.split("/")) <= 2 and not any(c.isdigit() for c in path):
        return status, final, "WARN: looks like category/root page"

    return status, final, None


def main():
    print("Fetching DB…")
    rows = fetch_all()
    tier1_rows = [r for r in rows if r["dealer"] in TIER1]
    other_rows = [r for r in rows if r["dealer"] not in TIER1]

    # Build Tier 1 price-per-oz lookup: product_key → list of poz values
    tier1_poz = {}
    for r in tier1_rows:
        poz = price_per_oz(r)
        if poz:
            k = product_key(r)
            tier1_poz.setdefault(k, []).append(poz)

    print(f"  {len(tier1_rows)} Tier 1 rows  |  {len(other_rows)} rows to validate\n")

    dealers = sorted(set(r["dealer"] for r in other_rows))

    for dealer in dealers:
        drows = [r for r in other_rows if r["dealer"] == dealer]
        print(f"{'─'*70}")
        print(f"  {dealer}  ({len(drows)} rows)")
        print(f"{'─'*70}")

        for r in drows:
            flags = []
            poz = price_per_oz(r)
            spot = spot_per_oz(r["metal"])
            label = r.get("weight_label") or f"{r.get('weight_oz')}oz"
            product = r.get("coin_type") or f"{r.get('bar_brand')} {r.get('bar_type')}"

            # 1. Spot sanity
            if poz and spot:
                ratio = poz / spot
                if ratio <= 1.005:
                    flags.append("WARN: price ≈ spot (likely storing spot price, not product price)")
                elif ratio <= 0.97:
                    flags.append("WARN: price below spot (likely buyback price stored as buy price)")
                elif ratio >= 1.50:
                    flags.append("WARN: price >50% above spot (wrong selector?)")

            # 2. Cross-dealer outlier
            k = product_key(r)
            t1_prices = tier1_poz.get(k)
            if t1_prices and poz:
                t1_avg = sum(t1_prices) / len(t1_prices)
                diff_pct = (poz - t1_avg) / t1_avg * 100
                if diff_pct < -20:
                    flags.append(f"WARN: {abs(diff_pct):.0f}% below Tier 1 avg (${t1_avg*r.get('weight_oz',1):,.0f})")
                elif diff_pct > 20:
                    flags.append(f"NOTE: {diff_pct:.0f}% above Tier 1 avg")

            # 3. URL check
            url_status, final_url, url_flag = check_url(r.get("buy_url"))
            if url_flag:
                flags.append(f"URL {url_flag}")

            status = "OK " if not flags else "!!!"
            print(f"  [{status}] {r['metal']:6s} {r['category']:4s}  {product:30s}  {label:8s}  "
                  f"${r['buy_price']:>10,.2f}  {(r.get('buy_url') or '')[:60]}")
            for f in flags:
                print(f"           ↳ {f}")

        print()


if __name__ == "__main__":
    main()