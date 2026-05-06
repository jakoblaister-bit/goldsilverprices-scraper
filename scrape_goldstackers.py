"""
scrape_goldstackers.py
Fetches live buy + sell prices from goldstackers.com.au/live-charts-prices/
"""

import re, html as htmllib, urllib.request

DEALER     = "Gold Stackers"
BASE       = "https://www.goldstackers.com.au"
PRICE_PAGE = BASE + "/live-charts-prices/"
OZ_PER_G   = 1 / 31.1035

EXCLUDE = [
    "pool allocated",
    "buyback",
    "tael",
    "luong",
    "blister pack",
    "eureka",
    "1 kg silver",          # 1kg random-date silver coin (unusual)
    "random dates/design",
]

def excluded(name):
    lo = name.lower()
    return any(s in lo for s in EXCLUDE)


# ── Weight ─────────────────────────────────────────────────────────────────────

def find_weight(raw):
    """Search anywhere in the name for a weight spec. Returns (oz, label)."""
    name = re.sub(r'\s*\([^)]+\)', '', raw).strip()   # drop parenthetical notes

    for pat, oz, lbl in [
        (r'\b1/10\s*oz\b', 0.1,   "1/10oz"),
        (r'\b1/4\s*oz\b',  0.25,  "1/4oz"),
        (r'\b1/2\s*oz\b',  0.5,   "1/2oz"),
        (r'\b1/2\s*kg\b',  round(500 * OZ_PER_G, 4), "500g"),
    ]:
        if re.search(pat, name, re.I):
            return oz, lbl

    m = re.search(r'\b(\d+)\s*kg\b', name, re.I)
    if m:
        kg = int(m.group(1))
        return round(kg * 32.1507, 4), f"{kg}kg"

    m = re.search(r'\b(\d+)\s*oz\b', name, re.I)
    if m:
        return float(m.group(1)), f"{m.group(1)}oz"

    m = re.search(r'\b(\d+\.?\d*)\s*gram\b', name, re.I)
    if m:
        g = float(m.group(1))
        return round(g * OZ_PER_G, 6), f"{int(g)}g" if g == int(g) else f"{g}g"

    m = re.search(r'\b(\d+\.?\d*)\s*g\b', name, re.I)
    if m:
        g = float(m.group(1))
        return round(g * OZ_PER_G, 6), f"{int(g)}g" if g == int(g) else f"{g}g"

    return None, None


# ── Coin type ──────────────────────────────────────────────────────────────────

LUNAR_ANIMALS = [
    "horse", "snake", "dragon", "rabbit", "tiger",
    "ox", "rat", "pig", "dog", "rooster", "monkey", "goat", "sheep",
]

WILDLIFE = [
    ("kangaroo",           "Kangaroo"),
    ("kookaburra",         "Kookaburra"),
    ("koala",              "Koala"),
    ("wedge.tailed eagle", "Wedge-Tailed Eagle"),
    ("emu",                "Australian Emu"),
    ("brumby",             "Australian Brumby"),
    ("kiwi",               "Kiwi"),
    ("thorny lizard",      "Thorny Lizard"),
    ("crocodile",          "Crocodile"),
]

INTL = [
    ("maple leaf",  "Maple Leaf"),
    ("maple",       "Maple Leaf"),
    ("krugerrand",  "Krugerrand"),
    ("britannia",   "Britannia"),
    ("philharmonic","Philharmonic"),
    ("buffalo",     "Buffalo"),
    ("american eagle", "American Eagle"),
    ("american silver eagle", "American Eagle"),
]


def coin_type_for(name):
    lo = name.lower()
    yr = None
    m = re.search(r'\b(202\d)\b', name)
    if m:
        yr = m.group(1)

    for animal in LUNAR_ANIMALS:
        if f"lunar {animal}" in lo or f"year of the {animal}" in lo:
            return f"Lunar {animal.capitalize()}"

    for pat, display in WILDLIFE:
        if re.search(pat, lo):
            return display

    for pat, display in INTL:
        if pat in lo:
            return display

    return None


# ── Bar ────────────────────────────────────────────────────────────────────────

def classify_bar(name):
    lo = name.lower()
    bar_type = "minted" if "minted" in lo else "cast"

    if "perth mint" in lo:
        return "Perth Mint", bar_type
    if "gba" in lo or "gold bullion australia" in lo:
        return "GBA", bar_type
    if "abc" in lo:
        return "ABC", bar_type
    if "pamp" in lo:
        return "PAMP", bar_type
    if "generic" in lo:
        return "Generic", bar_type

    return None, None


# ── Top-level classify ─────────────────────────────────────────────────────────

def classify(name):
    if excluded(name):
        return None

    lo = name.lower()

    if "platinum" in lo:
        return None

    # Strip company names containing "gold" so metal detection reads the product metal
    lo_metal = lo.replace("gold bullion australia", "").replace("gold stackers", "")
    if "gold" in lo_metal and "silver" not in lo_metal:
        metal = "gold"
    elif "silver" in lo_metal:
        metal = "silver"
    elif "gold" in lo_metal:
        metal = "gold"
    else:
        return None

    weight_oz, weight_label = find_weight(name)
    if weight_oz is None:
        return None

    is_coin = (
        "coin" in lo or "coins" in lo
        or ("kookaburra" in lo and "bar" not in lo)
        or ("koala" in lo and "bar" not in lo)
        or "krugerrand" in lo
        or "philharmonic" in lo
        or "maple" in lo
        or "buffalo" in lo
        or "american eagle" in lo
    )

    is_bar = (
        "bar" in lo or "bars" in lo
        or "cast" in lo
        or "minted bar" in lo
    )

    if is_coin and not is_bar:
        ct = coin_type_for(name)
        if not ct:
            return None
        yr_m = re.search(r'\b(202\d)\b', name)
        return {"metal": metal, "category": "coin", "coin_type": ct,
                "year": int(yr_m.group(1)) if yr_m else None,
                "weight_oz": weight_oz, "weight_label": weight_label}

    # Anything that's not a coin — treat as bar (covers "Gold Bullion Australia Silver – Xoz"
    # and "Generic Silver – Xoz" which lack an explicit "bar"/"cast" keyword)
    bar_brand, bar_type = classify_bar(name)
    if not bar_brand:
        return None
    category = "minted bar" if bar_type == "minted" else "cast bar"
    return {"metal": metal, "category": category,
            "bar_brand": bar_brand, "bar_type": bar_type,
            "weight_oz": weight_oz, "weight_label": weight_label}


# ── Fetch ──────────────────────────────────────────────────────────────────────

def fetch_products():
    req = urllib.request.Request(
        PRICE_PAGE,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"},
    )
    raw = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")

    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', raw, re.DOTALL)
    results = []
    seen = set()

    for row in rows:
        if "/product/" not in row:
            continue

        url_m  = re.search(r'href=(https://[^\s>]+/product/[^\s>]+?)(?:\s|>)', row)
        name_m = re.search(r'>([^<]+)</a>', row)
        prices = re.findall(r'<bdi>.*?(\d[\d,]*\.\d+)</bdi>', row, re.DOTALL)

        if not url_m or not name_m or len(prices) < 2:
            continue

        product_url = url_m.group(1).rstrip('/')
        if product_url in seen:
            continue
        seen.add(product_url)

        name = htmllib.unescape(name_m.group(1)).strip()

        # Strip trailing parenthetical notes from display name
        display_name = re.sub(r'\s*\([^)]*(?:delay|stock|date)[^)]*\)', '', name, flags=re.I).strip()

        fields = classify(name)
        if not fields:
            continue

        try:
            buy_price  = float(prices[0].replace(",", ""))
            sell_price = float(prices[1].replace(",", ""))
        except ValueError:
            continue

        if buy_price <= 0:
            continue
        if sell_price <= 0:
            sell_price = None

        results.append({
            "dealer":       DEALER,
            "metal":        fields["metal"],
            "category":     fields["category"],
            "coin_type":    fields.get("coin_type"),
            "year":         fields.get("year"),
            "bar_brand":    fields.get("bar_brand"),
            "bar_type":     fields.get("bar_type"),
            "weight_oz":    fields["weight_oz"],
            "weight_label": fields["weight_label"],
            "buy_price":    buy_price,
            "sell_price":   sell_price,
            "buy_url":      product_url,
            "raw_name":     name,
        })

    results.sort(key=lambda r: (
        r["metal"], r["category"],
        r["coin_type"] or r["bar_brand"] or "",
        r["weight_oz"],
    ))
    return results


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import csv
    rows = fetch_products()
    out = "goldstackers_live.csv"
    fields = ["dealer","metal","category","coin_type","bar_brand","bar_type",
              "weight_oz","weight_label","buy_price","sell_price","buy_url","raw_name"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    gold   = [r for r in rows if r["metal"] == "gold"]
    silver = [r for r in rows if r["metal"] == "silver"]
    coins  = [r for r in rows if r["category"] == "coin"]
    bars   = [r for r in rows if r["category"] != "coin"]
    print(f"✅ {len(rows)} rows → {out}")
    print(f"   gold={len(gold)}  silver={len(silver)}  coins={len(coins)}  bars={len(bars)}")
    for r in rows:
        print(f"  [{r['metal']:6s}] [{r['category']:10s}] "
              f"{(r['coin_type'] or r['bar_brand']+' '+r['bar_type']):30s} "
              f"{r['weight_label']:8s}  buy={r['buy_price']:>10,.2f}  sell={str(r['sell_price'] or '-'):>10s}  |  {r['raw_name']}")