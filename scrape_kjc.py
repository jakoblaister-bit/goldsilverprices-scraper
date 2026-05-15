"""
scrape_kjc.py
Scrapes live buy prices from kjc-gold-silver-bullion.com.au category pages.
Returns list of product dicts ready for push_kjc.py.
"""

import re, urllib.request

DEALER   = "KJC Bullion"
BASE_URL = "https://www.kjc-gold-silver-bullion.com.au"
OZ_PER_G = 1 / 31.1035

# Category tree pages: (metal, base_path)
CATEGORY_PATHS = [
    ("gold",   "/CT/gold-bullion-coins-1-20oz-to-kilo--99-99-24-carat/93"),
    ("gold",   "/CT/gold-bullion-bars-1gram-to-kilo--full-range-/11"),
    ("silver", "/CT/silver-bullion-coins-1-2oz-to-10-kilo--999-9999-/92"),
    ("silver", "/CT/silver-bullion-bars-1oz-10oz-1kg-to-100oz----/91"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# ── Skip / filter rules ───────────────────────────────────────────────────────

SKIP_KEYWORDS = [
    "proof",
    "sovereign",
    "pre-decimal",
    "ancient",
    "ex-set",
    "graded",
    "corona",
    "francs",
    "5 pfennig",
    "combibar",   # multi-piece bars: piece weight ≠ product weight
]

# ── Weight parsing ─────────────────────────────────────────────────────────────

def parse_weight(title):
    t = title.lower()
    # kg  e.g. "1 kg"
    m = re.search(r"(\d+(?:\.\d+)?)\s*kg\b", t)
    if m:
        kg  = float(m.group(1))
        oz  = round(kg * 1000 * OZ_PER_G, 4)
        lbl = f"{int(kg)}kg" if kg == int(kg) else f"{kg}kg"
        return oz, lbl
    # grams e.g. "30 g", "1 g"
    m = re.search(r"(\d+(?:\.\d+)?)\s*g\b", t)
    if m:
        g   = float(m.group(1))
        oz  = round(g * OZ_PER_G, 4)
        lbl = f"{int(g)}g" if g == int(g) else f"{g}g"
        return oz, lbl
    # fractional oz
    FRACS = [
        (r"1/20\s*oz",  0.05,  "1/20oz"),
        (r"1/10\s*oz",  0.1,   "1/10oz"),
        (r"1/4\s*oz",   0.25,  "1/4oz"),
        (r"1/2\s*oz",   0.5,   "1/2oz"),
    ]
    for pat, val, lbl in FRACS:
        if re.search(pat, t):
            return val, lbl
    # whole or decimal oz e.g. "1 oz", "100 oz", "4 oz"
    m = re.search(r"(\d+(?:\.\d+)?)\s*oz\b", t)
    if m:
        oz  = float(m.group(1))
        lbl = f"{int(oz)}oz" if oz == int(oz) else f"{oz}oz"
        return oz, lbl
    return None, None


def extract_year(title):
    m = re.search(r"\b(20\d{2})\b", title)
    return int(m.group(1)) if m else None


# ── Classification ────────────────────────────────────────────────────────────

LUNAR_ANIMALS = [
    ("horse", "Horse"), ("snake", "Snake"), ("dragon", "Dragon"),
    ("rabbit", "Rabbit"), ("hare", "Rabbit"), ("tiger", "Tiger"),
    ("ox", "Ox"), ("rat", "Mouse"), ("mouse", "Mouse"),
    ("pig", "Pig"), ("dog", "Dog"), ("rooster", "Rooster"),
    ("cock", "Rooster"), ("monkey", "Monkey"), ("goat", "Goat"),
    ("sheep", "Goat"), ("ram", "Goat"),
]

def _lunar_coin_type(t):
    for kw, name in LUNAR_ANIMALS:
        if f"year of the {kw}" in t or f"lunar {kw}" in t:
            return f"Lunar {name}"
    if "lunar" in t or "year of the" in t:
        m = re.search(r'\b(20\d\d)\b', t)
        if m:
            yr_map = {2026:"Horse",2025:"Snake",2024:"Dragon",2023:"Rabbit",
                      2022:"Tiger",2021:"Ox",2020:"Mouse",2019:"Pig",
                      2018:"Dog",2017:"Rooster",2016:"Monkey",2015:"Goat",2014:"Horse"}
            animal = yr_map.get(int(m.group(1)))
            if animal:
                return f"Lunar {animal}"
    return None

COIN_TYPES = [
    ("wedge.tailed eagle",  "Wedge-Tailed Eagle"),
    ("wedge tailed eagle",  "Wedge-Tailed Eagle"),
    ("kangaroo",            "Kangaroo"),
    ("nugget",              "Kangaroo"),   # old name for Kangaroo
    ("kookaburra",          "Kookaburra"),
    ("koala",               "Koala"),
    ("american eagle",      "American Eagle"),
    ("eagle",               "American Eagle"),
    ("maple leaf",          "Maple Leaf"),
    ("maple",               "Maple Leaf"),
    ("philharmonic",        "Philharmonic"),
    ("krugerrand",          "Krugerrand"),
    ("britannia",           "Britannia"),
    ("panda",               "Panda"),
    ("buffalo",             "Buffalo"),
    ("dragon",              "Dragon"),
    ("emu",                 "Emu"),
    ("swan",                "Swan"),
    ("brumby",              "Brumby"),
    ("outback",             "Outback"),
    ("super pit",           "Super Pit"),
]

BAR_BRANDS = [
    ("perth mint",   "Perth Mint"),
    ("abc bullion",  "ABC Bullion"),
    ("abc",          "ABC Bullion"),
    ("pamp",         "PAMP"),
    ("valcambi",     "Valcambi"),
    ("scottsdale",   "Scottsdale"),
    ("silvertowne",  "SilverTowne"),
    ("metalor",      "Metalor"),
    ("heraeus",      "Heraeus"),
    ("umicore",      "Umicore"),
]


def classify(title):
    t = title.lower()
    is_bar = "bar" in t or (
        "round" not in t and "coin" not in t and "bar" in t
    )
    is_coin = "coin" in t or "round" in t

    if is_bar and not is_coin:
        bar_type = ("minted" if "minted" in t
                    else "cast" if "cast" in t
                    else None)
        bar_brand = None
        for kw, brand in BAR_BRANDS:
            if kw in t:
                bar_brand = brand
                break
        return {"category": "bar", "coin_type": None,
                "bar_brand": bar_brand, "bar_type": bar_type}

    coin_type = _lunar_coin_type(t)
    if coin_type is None:
        for kw, ct in COIN_TYPES:
            if kw in t:
                coin_type = ct
                break
    return {"category": "coin", "coin_type": coin_type,
            "bar_brand": None, "bar_type": None}


# ── HTML parsing patterns ─────────────────────────────────────────────────────

CARD_PAT  = re.compile(r'data-productid="(\d+)"(.*?)(?=data-productid="|</main)', re.S)
TITLE_PAT = re.compile(r'class="text-dark"[^>]*href="([^"]+)"[^>]*>\s*(.*?)\s*</a>', re.S)
PRICE_PAT = re.compile(r'd-block font-weight-bold h5">\$([\d,]+(?:\.\d{2})?)')
BADGE_PAT = re.compile(r'badge(?:-success|-warning|-secondary|-danger)[^"]*float-left[^>]*>([^<]+)<')


def fetch_page(url):
    req = urllib.request.Request(url, headers=HEADERS)
    return urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")


def scrape_category(metal, base_path, seen_ids):
    products = []
    for page in range(1, 10):
        url  = f"{BASE_URL}{base_path}/{page}"
        html = fetch_page(url)

        cards_found = 0
        for m in CARD_PAT.finditer(html):
            pid, card_html = m.group(1), m.group(2)
            if pid in seen_ids:
                continue
            cards_found += 1

            title_m = TITLE_PAT.search(card_html)
            price_m = PRICE_PAT.search(card_html)
            badge_m = BADGE_PAT.search(card_html)

            if not title_m or not price_m:
                continue

            prod_url = title_m.group(1)
            title    = re.sub(r"\s+", " ", title_m.group(2)).strip()
            buy_price = float(price_m.group(1).replace(",", ""))
            badge    = badge_m.group(1).strip() if badge_m else ""

            # Skip sold-out and out-of-stock
            if any(x in badge.lower() for x in ("sold out", "out of stock")):
                continue

            # Must contain "Bullion"
            if "bullion" not in title.lower():
                continue

            # Skip numismatic / collector items
            t_lower = title.lower()
            if any(kw in t_lower for kw in SKIP_KEYWORDS):
                continue

            weight_oz, weight_label = parse_weight(title)
            if weight_oz is None:
                continue

            meta = classify(title)
            year = extract_year(title) if meta["category"] == "coin" else None

            seen_ids.add(pid)
            products.append({
                "metal":        metal,
                "category":     meta["category"],
                "coin_type":    meta["coin_type"],
                "bar_brand":    meta["bar_brand"],
                "bar_type":     meta["bar_type"],
                "weight_oz":    weight_oz,
                "weight_label": weight_label,
                "year":         year,
                "buy_price":    buy_price,
                "sell_price":   None,
                "buy_url":      prod_url,
                "available":    True,
            })

        if cards_found == 0:
            break  # no more pages

    return products


def fetch_products():
    all_products = []
    seen_ids = set()
    for metal, base_path in CATEGORY_PATHS:
        all_products.extend(scrape_category(metal, base_path, seen_ids))
    return all_products


if __name__ == "__main__":
    products = fetch_products()
    print(f"{len(products)} products scraped:")
    for p in products:
        label = p.get("coin_type") or f"{p.get('bar_brand')} {p.get('bar_type')}"
        yr    = f" {p['year']}" if p.get("year") else ""
        print(f"  {'G' if p['metal']=='gold' else 'S'} {p['category']:4}  "
              f"{str(label):25}  {p['weight_label']:6}  ${p['buy_price']:>10,.2f}{yr}")