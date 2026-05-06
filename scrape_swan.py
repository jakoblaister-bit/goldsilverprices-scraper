"""
scrape_swan.py
Fetches live buy prices from swanbullion.com/gold-bullion/ and /silver-bullion/
Returns list of product dicts ready for push_swan.py.
"""

import re, urllib.request

DEALER   = "Swan Bullion"
OZ_PER_G = 1 / 31.1035

CATEGORY_PAGES = [
    ("gold",   "https://swanbullion.com/gold-bullion/"),
    ("silver", "https://swanbullion.com/silver-bullion/"),
]

# ── Weight parsing ─────────────────────────────────────────────────────────────

WEIGHT_TABLE = [
    # pattern                                      oz           label
    (r'\b(\d+(?:\.\d+)?)\s*kg\b',                 None,        None),   # handled below
    (r'\b(\d+)\s*g\b',                             None,        None),   # handled below
    (r'1/20\s*oz',  0.05,    "1/20oz"),
    (r'1/10\s*oz',  0.1,     "1/10oz"),
    (r'1/4\s*oz',   0.25,    "1/4oz"),
    (r'1/2\s*oz',   0.5,     "1/2oz"),
    (r'\b1\s*oz\b', 1.0,     "1oz"),
    (r'\b2\s*oz\b', 2.0,     "2oz"),
    (r'\b5\s*oz\b', 5.0,     "5oz"),
    (r'\b10\s*oz\b',10.0,    "10oz"),
]


def parse_weight(title):
    t = title.lower()
    # kg
    m = re.search(r'(\d+(?:\.\d+)?)\s*kg', t)
    if m:
        kg = float(m.group(1))
        oz = round(kg * 1000 * OZ_PER_G, 4)
        label = f"{int(kg)}kg" if kg == int(kg) else f"{kg}kg"
        return oz, label
    # grams
    m = re.search(r'(\d+(?:\.\d+)?)\s*g\b', t)
    if m:
        g = float(m.group(1))
        oz = round(g * OZ_PER_G, 4)
        label = f"{int(g)}g" if g == int(g) else f"{g}g"
        return oz, label
    # fractional and whole oz
    for pattern, oz_val, label in WEIGHT_TABLE:
        if oz_val and re.search(pattern, t):
            return oz_val, label
    return None, None


# ── Product classification ─────────────────────────────────────────────────────

COIN_TYPES = [
    ("kangaroo",            "Kangaroo"),
    ("kookaburra",          "Kookaburra"),
    ("koala",               "Koala"),
    ("year of the horse",   "Lunar"),
    ("year of the snake",   "Lunar"),
    ("year of the dragon",  "Lunar"),
    ("year of the rabbit",  "Lunar"),
    ("year of the tiger",   "Lunar"),
    ("year of the ox",      "Lunar"),
    ("lunar",               "Lunar"),
    ("outback",             "Outback"),
    ("krugerrand",          "Krugerrand"),
    ("philharmonic",        "Philharmonic"),
    ("britannia",           "Britannia"),
    ("maple",               "Maple Leaf"),
    ("american eagle",      "American Eagle"),
]

BAR_BRANDS = [
    ("perth mint",   "Perth Mint"),
    ("abc bullion",  "ABC Bullion"),
    ("abc",          "ABC Bullion"),
    ("pamp",         "PAMP"),
]

SKIP_KEYWORDS = [
    "secondary market",   # buyback aggregation listing, not a retail product
]


def classify(title, metal):
    t = title.lower()

    # Skip non-retail listings
    for kw in SKIP_KEYWORDS:
        if kw in t:
            return None

    # Bar or coin?
    is_bar  = "bar" in t
    is_coin = "coin" in t or (not is_bar)

    if is_bar:
        bar_type = "minted" if "minted" in t else "cast"
        bar_brand = None
        for kw, brand in BAR_BRANDS:
            if kw in t:
                bar_brand = brand
                break
        return {
            "category": "bar",
            "bar_brand": bar_brand,
            "bar_type":  bar_type,
            "coin_type": None,
        }
    else:
        coin_type = None
        for kw, ct in COIN_TYPES:
            if kw in t:
                coin_type = ct
                break
        return {
            "category": "coin",
            "coin_type": coin_type,
            "bar_brand": None,
            "bar_type":  None,
        }


# ── Page scraping ──────────────────────────────────────────────────────────────

LINK_PAT  = re.compile(
    r'href="(https://swanbullion\.com/[^"]+)"[^>]*'
    r'class="woocommerce-LoopProduct-link[^"]*">(.*?)</a>',
    re.S
)
PRICE_PAT = re.compile(r'<bdi>.*?</span>([\d,]+\.?\d*)</bdi>', re.S)


def scrape_page(url, metal):
    req  = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")

    seen_keys = set()   # deduplicate (dealer, metal, category, coin_type/brand/type, weight_oz)
    products  = []

    for m in LINK_PAT.finditer(html):
        prod_url = m.group(1)
        title    = re.sub(r'<[^>]+>', '', m.group(2)).strip()

        pm = PRICE_PAT.search(html, m.end(), m.end() + 800)
        if not pm:
            continue
        price = float(pm.group(1).replace(',', ''))
        if price <= 0:
            continue   # $0.00 = out of stock

        weight_oz, weight_label = parse_weight(title)
        if weight_oz is None:
            continue

        meta = classify(title, metal)
        if meta is None:
            continue   # skipped

        # Deduplicate: skip second entry if same product (e.g., two Koala slugs)
        dedup_key = (metal, meta["category"],
                     meta.get("coin_type"), meta.get("bar_brand"),
                     meta.get("bar_type"), weight_oz)
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        products.append({
            "dealer":       DEALER,
            "metal":        metal,
            "category":     meta["category"],
            "coin_type":    meta["coin_type"],
            "bar_brand":    meta["bar_brand"],
            "bar_type":     meta["bar_type"],
            "weight_oz":    weight_oz,
            "weight_label": weight_label,
            "buy_price":    price,
            "buy_url":      prod_url,
            "available":    True,
        })

    return products


def fetch_products():
    all_products = []
    for metal, url in CATEGORY_PAGES:
        all_products.extend(scrape_page(url, metal))
    return all_products


if __name__ == "__main__":
    products = fetch_products()
    print(f"{len(products)} products scraped:")
    for p in products:
        label = p.get("coin_type") or f"{p['bar_brand']} {p['bar_type']}"
        print(f"  {'G' if p['metal']=='gold' else 'S'} {p['category']:4}  {label:20}  {p['weight_label']:6}  ${p['buy_price']:>10,.2f}  {p['buy_url']}")