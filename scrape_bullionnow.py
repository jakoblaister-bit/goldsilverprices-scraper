"""
scrape_bullionnow.py
Scrapes Bullion Now buy prices from WooCommerce category pages.
Buy prices only (no sell/buyback data available on site).
"""

import re, time, urllib.request

DEALER   = "Bullion Now"
BASE_URL = "https://bullionnow.com.au"
DELAY    = 0.3
OZ_PER_G = 1 / 31.1035

CATEGORY_PAGES = [
    (f"{BASE_URL}/product-category/gold/",   "gold"),
    (f"{BASE_URL}/product-category/silver/", "silver"),
]

FRAC_MAP = {"1/20": 0.05, "1/10": 0.1, "1/4": 0.25, "1/2": 0.5}

LUNAR_ANIMALS = [
    ("horse", "Horse"), ("snake", "Snake"), ("dragon", "Dragon"),
    ("rabbit", "Rabbit"), ("hare", "Rabbit"), ("tiger", "Tiger"),
    ("ox", "Ox"), ("rat", "Mouse"), ("mouse", "Mouse"),
    ("pig", "Pig"), ("dog", "Dog"), ("rooster", "Rooster"),
    ("monkey", "Monkey"), ("goat", "Goat"), ("sheep", "Goat"),
]

COIN_TYPES = [
    (r"kangaroo",                               "Kangaroo"),
    (r"kookaburra",                             "Kookaburra"),
    (r"koala",                                  "Koala"),
    (r"emu(?!\w)",                              "Emu"),
    (r"outback",                                "Outback"),
    (r"southern.cross",                         "Southern Cross"),
    (r"maple",                                  "Maple Leaf"),
    (r"britannia",                              "Britannia"),
    (r"krugerrand",                             "Krugerrand"),
    (r"philharmonic",                           "Philharmonic"),
    (r"american.eagle|liberty.coin|eagle.coin", "American Eagle"),
    (r"lunar",                                  "Lunar"),
]

BAR_BRANDS = [
    ("perth mint", "Perth Mint"),
    ("abc bullion", "ABC Bullion"),
    ("abc ",        "ABC Bullion"),
    ("pamp",        "PAMP"),
    ("valcambi",    "Valcambi"),
]

SKIP_KEYWORDS = [
    "proof", "antiqued", "antique", "coloured", "colored",
    "set", "box", "pack",
    "platinum", "palladium",
    "coin set", "jewellery",
    "numismatic", "collector",
    "round", "shaped",
    "gram gold", "gram silver",
    "100oz", "400oz", "5kg", "10kg",
    "niue", "barbados", "chad",
    "rectangle",
    "granule", "grain",
    "pool", "unallocated",
    # Non-standard brands sold on Bullion Now
    "germania", "mennica", "silvertowne", "intrinsic",
    "scottsdale", "wonka",
    # Novelty product names
    "liberty bar", "multibar", "multi bar", "divisible",
    "legendary warrior", "zombie", "dracula",
    "buy back",
]


def _lunar_type(t):
    for kw, name in LUNAR_ANIMALS:
        if f"year of the {kw}" in t or f"lunar {kw}" in t:
            return f"Lunar {name}"
    for kw, name in LUNAR_ANIMALS:
        if kw in t and ("lunar" in t or "year of" in t):
            return f"Lunar {name}"
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
    m = re.search(r'(\d+/\d+)\s*oz', t)
    if m:
        frac = m.group(1)
        oz = FRAC_MAP.get(frac)
        if oz is None:
            return None, None  # skip non-standard fractions like 1/25oz
        return oz, f"{frac}oz"
    m = re.search(r'(\d+(?:\.\d+)?)\s*kg\b', t)
    if m:
        kg = float(m.group(1))
        return round(kg * 1000 * OZ_PER_G, 4), f"{int(kg) if kg == int(kg) else kg}kg"
    m = re.search(r'(?<![/])(\d+(?:\.\d+)?)\s*g\b', t)
    if m:
        g = float(m.group(1))
        return round(g * OZ_PER_G, 4), f"{int(g) if g == int(g) else g}g"
    m = re.search(r'(\d+(?:\.\d+)?)\s*oz\b', t)
    if m:
        oz = float(m.group(1))
        return oz, f"{int(oz) if oz == int(oz) else oz}oz"
    return None, None


def classify(title):
    t = title.lower()
    if any(kw in t for kw in SKIP_KEYWORDS):
        return None
    is_bar = any(kw in t for kw in ("cast bar", "minted bar", "minted tablet", "certicard",
                                     "cast", "minted", "tablet", "ingot"))
    if any(c in t for c in ("coin", "kangaroo", "koala", "kookaburra", "maple",
                             "britannia", "krugerrand", "philharmonic", "eagle",
                             "kookaburra", "lunar", "year of")):
        is_bar = False
    if "bar" in t and not is_bar and not any(
        c in t for c in ("coin", "kangaroo", "koala", "kookaburra")
    ):
        is_bar = True
    if is_bar:
        brand = next((b for kw, b in BAR_BRANDS if kw in t), "Perth Mint")
        bt = "minted" if any(kw in t for kw in ("minted", "tablet", "certicard")) else "cast"
        return {"category": "bar", "bar_brand": brand, "bar_type": bt, "coin_type": None}
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
    # WooCommerce: product cards are <li class="... type-product ...">
    blocks = re.split(r'<li[^>]*class="[^"]*type-product[^"]*"', html)
    for block in blocks[1:]:
        # Title
        nm = re.search(r'woocommerce-loop-product__title[^>]*>([^<]+)<', block)
        # Price: <bdi>...$</span>&nbsp;1,234.56</bdi>
        pr = re.search(r'&nbsp;\s*([\d,]+\.?\d*)\s*</bdi>', block)
        # URL
        hr = re.search(r'href="(https://bullionnow\.com\.au/[^"]+)"', block)
        if not nm or not pr:
            continue
        title = nm.group(1).strip()
        try:
            price = float(pr.group(1).replace(",", ""))
        except ValueError:
            continue
        href = hr.group(1) if hr else url
        products.append({"title": title, "price": price, "url": href})

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
              f"{label:30}{yr:7}  {p['weight_label']:8}  ${p['buy_price']:>10,.2f}")
    gold   = sum(1 for p in products if p["metal"] == "gold")
    silver = sum(1 for p in products if p["metal"] == "silver")
    coins  = sum(1 for p in products if p["category"] == "coin")
    bars   = sum(1 for p in products if p["category"] == "bar")
    print(f"\n  gold={gold}  silver={silver}  coins={coins}  bars={bars}")