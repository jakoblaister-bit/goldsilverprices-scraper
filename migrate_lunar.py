"""
migrate_lunar.py
Update all coin_type='Lunar' rows in prices_v2 to 'Lunar Horse', 'Lunar Snake', etc.
using the year column to determine the correct animal.
"""
import json, urllib.request, urllib.parse

SUPABASE_URL = "https://cjxkhvkvhgnlnviykoad.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNqeGtodmt2aGdubG52aXlrb2FkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY1ODIyMDYsImV4cCI6MjA5MjE1ODIwNn0.eCg-JzEshidI-l7pVsumO_SsXbDOh_s--zvH1jc78g0"
HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=minimal",
}

YEAR_TO_ANIMAL = {
    2026: "Horse", 2025: "Snake",   2024: "Dragon", 2023: "Rabbit",
    2022: "Tiger", 2021: "Ox",      2020: "Mouse",  2019: "Pig",
    2018: "Dog",   2017: "Rooster", 2016: "Monkey", 2015: "Goat",
    2014: "Horse", 2013: "Snake",   2012: "Dragon",
}

# ── 1. Fetch all Lunar rows ──────────────────────────────────────────────────
url = f"{SUPABASE_URL}/rest/v1/prices_v2?coin_type=eq.Lunar&select=id,year,dealer"
req = urllib.request.Request(url, headers={k:v for k,v in HEADERS.items() if k != "Content-Type" and k != "Prefer"})
with urllib.request.urlopen(req, timeout=15) as r:
    rows = json.loads(r.read())

print(f"Found {len(rows)} rows with coin_type='Lunar'")
if not rows:
    print("Nothing to migrate.")
    exit(0)

# ── 2. Group by year ─────────────────────────────────────────────────────────
from collections import defaultdict
by_year = defaultdict(list)
for row in rows:
    by_year[row.get("year")].append(row["id"])

for year, ids in sorted(by_year.items(), key=lambda x: (x[0] is None, x[0])):
    animal = YEAR_TO_ANIMAL.get(year, "Horse")  # default to current year (2026) if null
    coin_type = f"Lunar {animal}"
    print(f"  year={year} ({len(ids)} rows) → {coin_type}")

# ── 3. Patch each group ──────────────────────────────────────────────────────
total_ok = 0
for year, ids in by_year.items():
    animal    = YEAR_TO_ANIMAL.get(year, "Horse")
    coin_type = f"Lunar {animal}"
    id_list   = ",".join(str(i) for i in ids)
    patch_url = f"{SUPABASE_URL}/rest/v1/prices_v2?id=in.({id_list})"
    data      = json.dumps({"coin_type": coin_type}).encode()
    req       = urllib.request.Request(patch_url, data=data, headers=HEADERS, method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            print(f"  ✓ Updated {len(ids)} rows (year={year}) → {coin_type}")
            total_ok += len(ids)
    except Exception as e:
        body = e.read().decode() if hasattr(e, "read") else str(e)
        print(f"  ✗ Error for year={year}: {body[:200]}")

print(f"\nDone. {total_ok}/{len(rows)} rows migrated.")