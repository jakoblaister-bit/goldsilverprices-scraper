"""
scrape_bullionlist.py
Scrapes BullionList.com.au category pages for gold and silver buy prices.
"""

import re, time, urllib.request, urllib.error

DEALER   = "Bullion List"
BASE_URL = "https://www.bullionlist.com.au"
DELAY    = 0.3
OZ_PER_G = 1 / 31.1035

CATEGORY_PAGES = [
    (f"{BASE_URL}/gold",   "gold"),
    (f"{BASE_URL}/silver", "silver"),
]

FRAC_MAP = {"1/20": 0.05, "1/10": 0.1, "1/4": 0.25, "1/2": 0.5}

LUNAR_ANIMALS = [
    ("horse", "Horse"), ("snake", "Snake"), ("dragon", "Dragon"),
    ("rabbit", "Rabbit"), ("hare", "Rabbit"), ("tiger", "Tiger"),
    ("ox", "Ox"), ("rat", "Mouse"), ("mouse", "Mouse"),
    ("pig", "Pig"), ("dog", "Dog"), ("rooster", "Rooster"),
    ("cock", "Rooster"), ("monkey", "Monkey"), ("goat", "Goat"),
    ("sheep", "Goat"), ("ram", "Goat"),
]

COIN_TYPES = [
    (r"kangaroo",         "Kangaroo"),
    (r"kookaburra",       "Kookaburra"),
    (r"koala",            "Koala"),
    (r"outback",          "Outback"),
    (r"emu(?!\w)",        "Emu"),
    (r"southern.cross",   "Southern Cross"),
    (r"maple",            "Maple Leaf"),
    (r"britannia",        "Britannia"),
    (r"krugerrand",       "Krugerrand"),
    (r"philharmonic",     "Philharmonic"),
    (r"american.eagle|liberty.coin|eagle.coin", "American Eagle"),
    (r"wedge.tailed.eagle|wedge tail", "Emu"),
]

BAR_BRANDS = [
    ("perth mint",   "Perth Mint"),
    ("abc bullion",  "ABC Bullion"),
    ("abc ",         "ABC Bullion"),
    ("pamp",         "PAMP"),
    ("valcambi",     "Valcambi"),
    ("southern cross bullion", "ABC Bullion"),
]

# Products to skip — numismatic, novelty, bulk, non-standard
SKIP_KEYWORDS = [
    "proof", "antiqued", "antique", "shaped", "coloured", "colored",
    "set", "box", "pack", "7 wonders", "barbados", "chad", "niue",
    "pac-man", "shrek", "superman", "zombie", "stackable", "round",
    "pelican", "zebra", "zeus", "pyramid", "lighthouse", "mausoleum",
    "temple", "artemis", "egyptian", "mandala", "dragon bar 2025",
    "lurna", "snake minted bar",  # specialty dragon/snake design bars (not coins)
    "rectangle",
]


def _lunar_type(t):
    for kw, name in LUNAR_ANIMALS:
        if f"year of the {kw}" in t or f"lunar {kw}" in t:
            return f"Lunar {name}"
    for kw, name in LUNAR_ANIMALS:
        if kw in t and ("lunar" in t or "year of" in t):
            return f"Lunar {name}"
    # Year-based fallback
    m = re.search(r'\b(20\d{2})\b', t)
    if m and ("lunar" in t or "year of" in t):
        yr_map = {2026: "Horse", 2025: "Snake", 2024: "Dragon", 2023: "Rabbit",
                  2022: "Tiger", 2021: "Ox", 2020: "Mouse", 2019: "Pig",
                  2018: "Dog", 2017: "Rooster", 2016: "Monkey", 2015: "Goat", 2014: "Horse"}
        animal = yr_map.get(int(m.group(1)))
        if animal:
            return f"Lunar {animal}"
    return None


def parse_weight(t):
    # Fractions like 1/10oz, 1/2oz
    m = re.search(r'(\d+/\d+)\s*oz', t)
    if m:
        frac = m.group(1)
        oz = FRAC_MAP.get(frac)
        if oz is None:
            n, d = frac.split("/"); oz = round(int(n) / int(d), 6)
        return oz, f"{frac}oz"
    # kg
    m = re.search(r'(\d+(?:\.\d+)?)\s*kg\b', t)
    if m:
        kg = float(m.group(1))
        return round(kg * 1000 * OZ_PER_G, 4), f"{int(kg) if kg == int(kg) else kg}kg"
    # grams
    m = re.search(r'(\d+(?:\.\d+)?)\s*g\b', t)
    if m:
        g = float(m.group(1))
        return round(g * OZ_PER_G, 4), f"{int(g) if g == int(g) else g}g"
    # oz
    m = re.search(r'(\d+(?:\.\d+)?)\s*oz\b', t)
    if m:
        oz = float(m.group(1))
        return oz, f"{int(oz) if oz == int(oz) else oz}oz"
    return None, None


def classify(title):
    t = title.lower()
    if any(kw in t for kw in SKIP_KEYWORDS):
        return None
    # Bars: "bar", "cast", "minted bar", "tablet", "certicard" (Perth Mint minted)
    is_bar = any(kw in t for kw in ("cast bar", "minted bar", "minted tablet", "certicard", "tablet range"))
    # certicard is always a minted bar — don't let coin keywords override it
    if "certicard" not in t and ("coin" in t or "kangaroo" in t or "kookaburra" in t or "koala" in t or "maple" in t):
        is_bar = False
    if "bar" in t and not is_bar and not any(
        c in t for c in ("coin", "kangaroo", "koala", "kookaburra", "outback")
    ):
        is_bar = True
    if is_bar:
        brand = next((b for kw, b in BAR_BRANDS if kw in t), "Perth Mint")
        bt = "minted" if any(kw in t for kw in ("minted", "tablet", "certicard")) else "cast"
        return {"category": "bar", "bar_brand": brand, "bar_type": bt, "coin_type": None}
    # Lunar check first
    lunar = _lunar_type(t)
    if lunar:
        return {"category": "coin", "coin_type": lunar, "bar_brand": None, "bar_type": None}
    coin = next((ct for pat, ct in COIN_TYPES if re.search(pat, t)), None)
    if coin:
        return {"category": "coin", "coin_type": coin, "bar_brand": None, "bar_type": None}
    return None


def extract_year(title):
    m = re.search(r'\b(20\d{2})\b', title)
    return int(m.group(1)) if m else None


def fetch_page(url, metal):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  ERROR fetching {url}: {e}")
        return []

    products = []
    blocks = html.split('class="productBlock">')
    for block in blocks[1:]:
        nm = re.search(r'class="name"><a[^>]*>([^<]+)<', block)
        pr = re.search(r'class="basePrice">\$([\d,]+\.?\d*)', block)
        hr = re.search(r'href="(/(?:gold|silver)/[^"]+)"', block)
        if not nm or not pr:
            continue
        title = nm.group(1).strip()
        price = float(pr.group(1).replace(",", ""))
        href  = hr.group(1) if hr else f"/{metal}"
        products.append({"title": title, "price": price, "url": BASE_URL + href})

    return products


def fetch_products():
    seen_keys = set()
    results = []

    for url, metal in CATEGORY_PAGES:
        raw = fetch_page(url, metal)
        time.sleep(DELAY)
        for item in raw:
            title = item["title"]
            t = title.lower()
            weight_oz, weight_label = parse_weight(t)
            if weight_oz is None:
                continue
            meta = classify(title)
            if meta is None:
                continue
            year = extract_year(title) if meta["category"] == "coin" else None
            key = (metal, meta["category"], meta.get("coin_type"),
                   meta.get("bar_brand"), meta.get("bar_type"), weight_oz, year)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            results.append({
                "dealer":       DEALER,
                "metal":        metal,
                "category":     meta["category"],
                "coin_type":    meta["coin_type"],
                "year":         year,
                "bar_brand":    meta["bar_brand"],
                "bar_type":     meta["bar_type"],
                "weight_oz":    weight_oz,
                "weight_label": weight_label,
                "buy_price":    item["price"],
                "sell_price":   None,
                "buy_url":      item["url"],
                "available":    True,
            })

    return results


if __name__ == "__main__":
    products = fetch_products()
    print(f"\n{DEALER}: {len(products)} products\n")
    for p in sorted(products, key=lambda x: (x["metal"], x["category"], x["weight_oz"])):
        label = p.get("coin_type") or f"{p['bar_brand']} {p['bar_type']}"
        yr    = f" ({p['year']})" if p.get("year") else ""
        print(f"  {'G' if p['metal']=='gold' else 'S'} {p['category']:4}  "
              f"{label:28}{yr:7}  {p['weight_label']:8}  ${p['buy_price']:>10,.2f}")
    gold   = sum(1 for p in products if p["metal"] == "gold")
    silver = sum(1 for p in products if p["metal"] == "silver")
    coins  = sum(1 for p in products if p["category"] == "coin")
    bars   = sum(1 for p in products if p["category"] == "bar")
    print(f"\n  gold={gold}  silver={silver}  coins={coins}  bars={bars}")