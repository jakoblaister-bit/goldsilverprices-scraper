"""
scrape_jaggards.py
Discovers products from the WP sitemap, filters to bullion, then fetches each
individual product page for price + live stock status.
"""

import re, time, urllib.request, urllib.error

DEALER    = "Jaggards"
SITEMAP   = "https://www.jaggards.com.au/wp-sitemap-posts-product-1.xml"
OZ_PER_G  = 1 / 31.1035
DELAY     = 0.35   # seconds between product page fetches

# ── URL-level pre-filter (applied before any HTTP fetch) ───────────────────────

SKIP_URL = [
    "platinum", "palladium", "rhodium",
    "proof", "pcgs", "ngc",             # graded / proof coins
    "sovereign", "half-sovereign",       # old British sovereigns
    "panda", "niue",                     # novelty / collector
    "luong", "tael",                     # non-standard Asian weights
    "secondary-bullion",
    "gallipoli", "world-cup", "kimberley", "lenticular",
    "piedfort", "year-set", "gold-royal-mint",
]

# Only include products that match at least one of these
INCLUDE_URL = [
    "bar", "cast", "minted", "tablet",  # any bar
    "kangaroo", "kookaburra", "koala", "emu",
    "outback", "britannia", "maple", "krugerrand", "philharmonic",
    "lunar", "horse", "snake", "dragon", "rabbit", "tiger",
    "southern-cross",
]

# ── Weight + classification ────────────────────────────────────────────────────

FRAC_MAP = {"1/20": 0.05, "1/10": 0.1, "1/4": 0.25, "1/2": 0.5}

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
    (r"kangaroo",          "Kangaroo"),
    (r"kookaburra",        "Kookaburra"),
    (r"koala",             "Koala"),
    (r"emu(?!\w)",         "Emu"),
    (r"outback",           "Outback"),
    (r"southern.cross",    "Southern Cross"),
    (r"britannia",         "Britannia"),
    (r"maple",             "Maple Leaf"),
    (r"krugerrand",        "Krugerrand"),
    (r"philharmonic",      "Philharmonic"),
]

BAR_BRANDS = [
    ("perth mint",   "Perth Mint"),
    ("abc bullion",  "ABC Bullion"),
    ("abc",          "ABC Bullion"),
    ("pamp",         "PAMP"),
    ("valcambi",     "Valcambi"),
]


def extract_year(title):
    m = re.search(r'\b(20\d{2})\b', title)
    return int(m.group(1)) if m else None


def parse_weight(title):
    t = title.lower()
    m = re.search(r'(\d+(?:\.\d+)?)\s*kg\b', t)
    if m:
        kg = float(m.group(1))
        return round(kg * 1000 * OZ_PER_G, 4), f"{int(kg) if kg==int(kg) else kg}kg"
    m = re.search(r'(\d+(?:\.\d+)?)\s*g\b', t)
    if m:
        g = float(m.group(1))
        return round(g * OZ_PER_G, 4), f"{int(g) if g==int(g) else g}g"
    m = re.search(r'(\d+/\d+)\s*oz', t)
    if m:
        frac = m.group(1)
        oz = FRAC_MAP.get(frac)
        if oz is None:
            n, d = frac.split("/"); oz = round(int(n)/int(d), 6)
        return oz, f"{frac}oz"
    m = re.search(r'(\d+(?:\.\d+)?)\s*oz\b', t)
    if m:
        oz = float(m.group(1))
        return oz, f"{int(oz) if oz==int(oz) else oz}oz"
    return None, None


def classify(title):
    t = title.lower()
    is_bar = "bar" in t or "tablet" in t
    if is_bar:
        bar_type = "minted" if "minted" in t or "tablet" in t else "cast"
        bar_brand = next((brand for kw, brand in BAR_BRANDS if kw in t), None)
        return {"category": "bar", "bar_brand": bar_brand, "bar_type": bar_type, "coin_type": None}
    coin_type = _lunar_coin_type(t) or next((ct for pat, ct in COIN_TYPES if re.search(pat, t)), None)
    if coin_type is None:
        return None
    return {"category": "coin", "coin_type": coin_type, "bar_brand": None, "bar_type": None}


def metal_from_title(title):
    t = title.lower()
    return "silver" if "silver" in t else "gold" if "gold" in t else None


# ── Individual product page scraping ──────────────────────────────────────────

PRICE_PAT = re.compile(r'<p class="price[^"]*">.*?<bdi>.*?</span>([\d,]+\.?\d*)</bdi>', re.S)
TITLE_PAT = re.compile(r'<h1[^>]*class="[^"]*product_title[^"]*"[^>]*>(.*?)</h1>', re.S)


def scrape_product(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", errors="ignore")
    except Exception:
        return None

    # Stock check first — skip before price extraction
    if "out-of-stock" in html or 'class="stock out-of-stock"' in html:
        return None

    price_m = PRICE_PAT.search(html)
    if not price_m:
        # Fallback: first bdi with a realistic price
        bdi = re.search(r'<bdi>.*?</span>([\d,]+\.?\d*)</bdi>', html, re.S)
        if not bdi:
            return None
        price_m = bdi

    title_m = TITLE_PAT.search(html)
    if not title_m:
        title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
    if not title_m:
        return None

    price = float(price_m.group(1).replace(',', ''))
    title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
    return {"title": title, "price": price, "url": url}


# ── Sitemap discovery + filtering ─────────────────────────────────────────────

def get_product_urls():
    req = urllib.request.Request(SITEMAP, headers={"User-Agent": "Mozilla/5.0"})
    xml = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", errors="ignore")
    all_urls = re.findall(r'<loc>(https://www\.jaggards\.com\.au/product/[^<]+)</loc>', xml)

    filtered = []
    for u in all_urls:
        slug = u.rstrip("/").split("/")[-1]
        if any(kw in slug for kw in SKIP_URL):
            continue
        if not any(kw in slug for kw in INCLUDE_URL):
            continue
        filtered.append(u)
    return filtered


# ── Main ──────────────────────────────────────────────────────────────────────

def fetch_products():
    urls = get_product_urls()
    print(f"  {len(urls)} candidate URLs after URL filter")

    seen_keys = set()
    products  = []

    for url in urls:
        result = scrape_product(url)
        time.sleep(DELAY)
        if not result:
            continue

        title, price, prod_url = result["title"], result["price"], result["url"]
        metal = metal_from_title(title)
        if metal not in ("gold", "silver"):
            continue
        weight_oz, weight_label = parse_weight(title)
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

        products.append({
            "dealer":       DEALER,
            "metal":        metal,
            "category":     meta["category"],
            "coin_type":    meta["coin_type"],
            "year":         year,
            "bar_brand":    meta["bar_brand"],
            "bar_type":     meta["bar_type"],
            "weight_oz":    weight_oz,
            "weight_label": weight_label,
            "buy_price":    price,
            "buy_url":      prod_url,
            "available":    True,
        })

    return products


if __name__ == "__main__":
    products = fetch_products()
    print(f"\n{len(products)} products scraped from Jaggards:")
    for p in sorted(products, key=lambda x: (x["metal"], x["category"], x["weight_oz"])):
        label = p.get("coin_type") or f"{p['bar_brand']} {p['bar_type']}"
        print(f"  {'G' if p['metal']=='gold' else 'S'} {p['category']:4}  "
              f"{label:25}  {p['weight_label']:8}  ${p['buy_price']:>10,.2f}  {p['buy_url']}")