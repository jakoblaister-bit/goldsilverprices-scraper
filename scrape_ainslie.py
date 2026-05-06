"""
scrape_ainslie.py
Fetches live buy + sell prices from ainsliebullion.com.au/Charts
and writes ainslie_live.csv  (one row per product, no existing CATALOGUE touched).
"""

import csv, re, urllib.request

BASE       = "https://ainsliebullion.com.au"
CHARTS_URL = BASE + "/Charts"
OZ_PER_G   = 1 / 31.1035

# ── Products to skip outright ─────────────────────────────────────────────────
EXCLUDE_SUBSTRINGS = [
    "diwali",
    "luong",
    "scottsdale",
    "fine gold granule",
    "sydney olympics",
    "unallocated",
    "50 x 1966",
    "various brands",
    "kooka/koala",           # combined catch-all — we handle each separately
    "minted dragon gold bar",
    "minted snake gold bar",
    "minted silver round",
    "minted kangaroo silver bar",
    "silver minted dragon bar",
    "silver minted snake bar",
    "tube of",
    "225th anniversary",
    "dragon rectangular",
    "dragon and koi",
    "vintage",
    "coin general",
    "silver - general",
    "2000 sydney",
    "50c round",
    "23 design",             # old Perth Mint design variant
    "2014 year",             # 12-year-old lunar coin (not current)
]

def excluded(name):
    lo = name.lower()
    return any(s in lo for s in EXCLUDE_SUBSTRINGS)


# ── Zodiac animal → Lunar name ─────────────────────────────────────────────────
ZODIAC = {
    "horse":    "Lunar Horse",
    "snake":    "Lunar Snake",
    "dragon":   "Lunar Dragon",
    "rabbit":   "Lunar Rabbit",
    "tiger":    "Lunar Tiger",
    "ox":       "Lunar Ox",
    "rat":      "Lunar Rat",
    "pig":      "Lunar Pig",
    "dog":      "Lunar Dog",
    "rooster":  "Lunar Rooster",
    "monkey":   "Lunar Monkey",
    "goat":     "Lunar Goat",
    "sheep":    "Lunar Goat",
}


# ── Weight parsing from name prefix ───────────────────────────────────────────
def parse_weight(name):
    """Return (weight_oz, label) or (None, None)."""
    # strip leading "N x " prefix  e.g. "1 x 1oz …"
    name = re.sub(r"^\d+\s*x\s*", "", name, flags=re.I).strip()

    for pat, oz, lbl in [
        (r"^1/10\s*oz\b",  0.1,   "1/10oz"),
        (r"^1/4\s*oz\b",   0.25,  "1/4oz"),
        (r"^1/2\s*oz\b",   0.5,   "1/2oz"),
        (r"^1/2\s*kg\b",   round(500 * OZ_PER_G, 4), "500g"),
    ]:
        if re.match(pat, name, re.I):
            return oz, lbl

    m = re.match(r"^(\d+)\s*kg\b", name, re.I)
    if m:
        kg = int(m.group(1))
        return round(kg * 32.1507, 4), f"{kg}kg"

    m = re.match(r"^(\d+)\s*oz\b", name, re.I)
    if m:
        return float(m.group(1)), f"{m.group(1)}oz"

    m = re.match(r"^(\d+\.?\d*)\s*g\b", name, re.I)
    if m:
        g = float(m.group(1))
        label = f"{int(g)}g" if g == int(g) else f"{g}g"
        return round(g * OZ_PER_G, 6), label

    return None, None


# ── Coin-type normalisation ────────────────────────────────────────────────────
# Perth Mint wildlife/design coins keep the year because multiple years coexist
# on the Charts page with different prices.
# International coins have no year variant — just the type name.
# Zodiac: year is already encoded in the animal name.

def extract_year(name):
    m = re.search(r"\b(202\d)\b", name)
    return m.group(1) if m else None


def coin_type_for(name):
    lo = name.lower()
    yr = extract_year(name)

    # Zodiac → "Lunar Horse" etc.  (year implicit in animal)
    for animal, lunar in ZODIAC.items():
        if f"year of the {animal}" in lo:
            return lunar

    # Kangaroo "various years" entry → generic "Kangaroo"
    if "kangaroo" in lo and "various" in lo:
        return "Kangaroo"

    # Perth Mint wildlife / design coins  (year appended when available)
    pm_designs = [
        ("kangaroo",           "Kangaroo"),
        ("kookaburra",         "Kookaburra"),
        ("koala",              "Koala"),
        ("wedge tailed eagle", "Wedge-Tailed Eagle"),
        ("australian emu",     "Australian Emu"),
        ("australian swan",    "Australian Swan"),
        ("australian brumby",  "Australian Brumby"),
        ("outback",            "Outback"),
        ("four guardians",     "Four Guardians"),
        ("chinese myths",      "Chinese Myths & Legends"),
        ("double phoenix",     "Chinese Myths & Legends"),
    ]
    for pat, display in pm_designs:
        if pat in lo:
            return display

    # International coins — no year suffix
    intl = [
        ("maple leaf",           "Maple Leaf"),
        ("krugerrand",           "Krugerrand"),
        ("britannia",            "Britannia"),
        ("philharmonic",         "Philharmonic"),
        ("buffalo",              "Buffalo"),
        ("american silver eagle","American Eagle"),
        ("american eagle",       "American Eagle"),
    ]
    for pat, display in intl:
        if pat in lo:
            return display

    return None


# ── Bar classification ─────────────────────────────────────────────────────────
def classify_bar(name):
    """Return (category, product_type) or (None, None)."""
    lo = name.lower()
    is_minted = "minted" in lo
    category  = "minted bar" if is_minted else "cast bar"
    bar_type  = "minted"    if is_minted else "cast"

    if "ainslie" in lo:
        if "stacker" in lo:
            return "cast bar", "Ainslie stacker"
        brand = "Ainslie"
    elif "perth mint" in lo or "australian origin" in lo:
        brand = "Perth Mint (AO)" if "australian origin" in lo else "Perth Mint"
    elif "abc" in lo:
        brand = "ABC Bullion"
    else:
        return None, None

    return category, f"{brand} {bar_type}"


# ── Classify a product row ─────────────────────────────────────────────────────
def classify(name, url):
    if excluded(name):
        return None

    lo = name.lower()

    # Metal
    has_gold   = "gold"   in lo
    has_silver = "silver" in lo
    if   has_gold and not has_silver:   metal = "gold"
    elif has_silver and not has_gold:   metal = "silver"
    elif has_gold:                      metal = "gold"
    else:                               return None

    weight_oz, weight_label = parse_weight(name)
    if weight_oz is None:
        return None

    # Coin?
    is_coin = (
        "coin" in lo or "coins" in lo
        or "krugerrand" in lo
        or "philharmonic" in lo
        or "maple leaf" in lo
        or "buffalo" in lo
        or ("kookaburra" in lo and "bar" not in lo)
        or ("koala" in lo and "bar" not in lo)
    )

    if is_coin:
        ct = coin_type_for(name)
        if not ct:
            return None
        yr_str = extract_year(name)
        return {"metal": metal, "category": "coin", "product_type": ct,
                "year": int(yr_str) if yr_str else None,
                "weight": weight_label, "weight_oz": weight_oz}

    if "bar" in lo or "bullion" in lo or "stacker" in lo:
        cat, pt = classify_bar(name)
        if not cat:
            return None
        return {"metal": metal, "category": cat, "product_type": pt,
                "weight": weight_label, "weight_oz": weight_oz}

    return None


# ── Fetch & parse ─────────────────────────────────────────────────────────────
def fetch_products():
    html = urllib.request.urlopen(
        urllib.request.Request(CHARTS_URL, headers={"User-Agent": "Mozilla/5.0"}),
        timeout=15,
    ).read().decode("utf-8", errors="ignore")

    pattern = (
        r'<a href="(/Buy/View/Product/Name/[^"]+)"[^>]*>([^<]+)</a>'
        r'.*?text-end">([0-9,]+\.?\d*)</div>'   # sell-back price
        r'\s*<div[^>]*text-end">([0-9,]+\.?\d*)</div>'  # buy price
    )
    rows = []
    seen = set()   # deduplicate by URL

    for url_path, raw_name, sell_str, buy_str in re.findall(pattern, html, re.DOTALL):
        if url_path in seen:
            continue
        seen.add(url_path)

        name = raw_name.strip()
        full_url = BASE + url_path

        fields = classify(name, url_path)
        if not fields:
            continue

        try:
            buy_price  = float(buy_str.replace(",", ""))
            sell_price = float(sell_str.replace(",", ""))
        except ValueError:
            continue

        rows.append({
            "dealer":       "Ainslie Bullion",
            "metal":        fields["metal"],
            "category":     fields["category"],
            "product_type": fields["product_type"],
            "year":         fields.get("year"),
            "weight":       fields["weight"],
            "weight_oz":    fields["weight_oz"],
            "buy_url":      full_url,
            "sell_url":     CHARTS_URL,
            "buy_price":    buy_price,
            "sell_price":   sell_price,
            "raw_name":     name,   # keep for human review
        })

    rows.sort(key=lambda r: (r["metal"], r["category"], r["product_type"], float(r["weight_oz"])))
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    rows = fetch_products()

    out = "ainslie_live.csv"
    fields = ["dealer","metal","category","product_type","weight","weight_oz",
              "buy_url","sell_url","buy_price","sell_price","raw_name"]

    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    gold   = [r for r in rows if r["metal"] == "gold"]
    silver = [r for r in rows if r["metal"] == "silver"]
    coins  = [r for r in rows if r["category"] == "coin"]
    bars   = [r for r in rows if r["category"] != "coin"]
    print(f"✅ {len(rows)} rows → {out}")
    print(f"   gold={len(gold)}  silver={len(silver)}  coins={len(coins)}  bars={len(bars)}")