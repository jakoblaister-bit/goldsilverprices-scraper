"""
scrape_guardian.py
Discovers all products from guardian-gold.com.au/shop/ (paginated WooCommerce),
filters to in-stock bullion, fetches each product page for live price + stock.
"""

import re, time, urllib.request, urllib.error

DEALER   = "Guardian Gold"
SHOP_URL = "https://guardian-gold.com.au/shop/"
OZ_PER_G = 1 / 31.1035
DELAY    = 0.35

# ── URL-level skip filters ────────────────────────────────────────────────────

SKIP_URL = [
    "buyback", "buybacks",      # sell-to-dealer prices — not retail buy prices
    "platinum", "palladium",
    "proof", "numismatic",
    "monster-box",
    "luong", "tael",
    "sale",                     # "sale" items may be mispriced or clearance
    "copy",                     # WordPress duplicate slug suffix
]

INCLUDE_URL = [
    "gold", "silver",
    "bar", "cast", "minted",
    "kangaroo", "kookaburra", "koala", "emu",
    "outback", "britannia", "maple", "krugerrand", "philharmonic",
    "lunar", "horse", "snake", "dragon",
]

# ── Weight parsing ─────────────────────────────────────────────────────────────

FRAC_MAP = {"1/20": 0.05, "1/10": 0.1, "1/4": 0.25, "1/2": 0.5}


def extract_year(title):
    m = re.search(r'\b(20\d{2})\b', title)
    return int(m.group(1)) if m else None


def parse_weight(title):
    t = title.lower()
    m = re.search(r'(\d+(?:\.\d+)?)\s*kilo\b|\b(\d+(?:\.\d+)?)\s*kg\b', t)
    if m:
        kg = float(m.group(1) or m.group(2))
        return round(kg * 1000 * OZ_PER_G, 4), f"{int(kg) if kg==int(kg) else kg}kg"
    m = re.search(r'(\d+(?:\.\d+)?)\s*g\b', t)
    if m:
        g = float(m.group(1))
        return round(g * OZ_PER_G, 4), f"{int(g) if g==int(g) else g}g"
    m = re.search(r'(\d+/\d+)\s*oz', t)
    if m:
        frac = m.group(1); oz = FRAC_MAP.get(frac)
        if oz is None:
            n, d = frac.split("/"); oz = round(int(n)/int(d), 6)
        return oz, f"{frac}oz"
    m = re.search(r'(\d+(?:\.\d+)?)\s*oz\b', t)
    if m:
        oz = float(m.group(1))
        return oz, f"{int(oz) if oz==int(oz) else oz}oz"
    return None, None


# ── Classification ─────────────────────────────────────────────────────────────

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
    (r"kangaroo",           "Kangaroo"),
    (r"kookaburra",         "Kookaburra"),
    (r"koala",              "Koala"),
    (r"emu(?!\w)",          "Emu"),
    (r"outback",            "Outback"),
    (r"southern.cross",     "Southern Cross"),
    (r"britannia",          "Britannia"),
    (r"maple",              "Maple Leaf"),
    (r"krugerrand",         "Krugerrand"),
    (r"philharmonic",       "Philharmonic"),
]

BAR_BRANDS = [
    ("perth mint",    "Perth Mint"),
    ("abc bullion",   "ABC Bullion"),
    ("abc",           "ABC Bullion"),
    ("pamp",          "PAMP"),
    ("valcambi",      "Valcambi"),
    ("guardian",      "Guardian Gold"),
]


def classify(title):
    t = title.lower()
    is_bar = "bar" in t or ("cast" in t and "coin" not in t) or "minted bar" in t
    if "coin" in t:
        is_bar = False
    if is_bar:
        bar_type  = "minted" if "minted" in t else "cast"
        bar_brand = next((b for kw, b in BAR_BRANDS if kw in t), None)
        return {"category": "bar", "bar_brand": bar_brand, "bar_type": bar_type, "coin_type": None}
    coin_type = _lunar_coin_type(t) or next((ct for pat, ct in COIN_TYPES if re.search(pat, t)), None)
    if coin_type is None:
        return None
    return {"category": "coin", "coin_type": coin_type, "bar_brand": None, "bar_type": None}


def metal_from_title(title):
    t = title.lower()
    return "silver" if "silver" in t else "gold" if "gold" in t else None


# ── Shop page discovery ────────────────────────────────────────────────────────

def get_product_urls():
    seen = set()
    urls = []
    page = 1

    while True:
        shop = SHOP_URL if page == 1 else f"{SHOP_URL}page/{page}/"
        req  = urllib.request.Request(shop, headers={"User-Agent": "Mozilla/5.0"})
        try:
            html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                break
            raise

        found = re.findall(r'href="(https://guardian-gold\.com\.au/product/[^"]+)"', html)
        new_on_page = 0
        for u in found:
            slug = u.rstrip("/").split("/")[-1]
            if slug in seen:
                continue
            if any(kw in slug for kw in SKIP_URL):
                continue
            if not any(kw in slug for kw in INCLUDE_URL):
                continue
            seen.add(slug)
            urls.append(u)
            new_on_page += 1

        next_page = f"/shop/page/{page+1}/" in html
        if not next_page:
            break
        page += 1
        time.sleep(0.2)

    return urls


# ── Individual product page scraping ──────────────────────────────────────────

def scrape_product(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError:
        return None

    # Out-of-stock check
    if "out-of-stock" in html or "outofstock" in html:
        return None

    # Guardian Gold WooCommerce price: inside .price > bdi
    price_m = re.search(r'<p class="price[^"]*">.*?<bdi>.*?</span>([\d,]+\.?\d*)</bdi>', html, re.S)
    if not price_m:
        price_m = re.search(r'<bdi>.*?</span>([\d,]+\.?\d*)</bdi>', html, re.S)
    if not price_m:
        return None

    # Title
    title_m = re.search(r'<h1[^>]*class="[^"]*product_title[^"]*"[^>]*>(.*?)</h1>', html, re.S)
    if not title_m:
        title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
    if not title_m:
        return None

    price = float(price_m.group(1).replace(',', ''))
    title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()

    # Extract buyback (sell) price from addon--buyback div
    buyback_m = re.search(r'addon--buyback[^>]*>\s*\$([\d,]+\.?\d*)', html)
    sell_price = float(buyback_m.group(1).replace(',', '')) if buyback_m else None

    return {"title": title, "price": price, "sell_price": sell_price, "url": url}


# ── Main ──────────────────────────────────────────────────────────────────────

def fetch_products():
    urls = get_product_urls()
    print(f"  {len(urls)} candidate URLs after shop discovery + filter")

    seen_keys = set()
    products  = []

    for url in urls:
        result = scrape_product(url)
        time.sleep(DELAY)
        if not result:
            continue
        title, price = result["title"], result["price"]
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
            "sell_price":   result.get("sell_price"),
            "buy_url":      result["url"],
            "available":    True,
        })

    return products


if __name__ == "__main__":
    products = fetch_products()
    print(f"\n{len(products)} products scraped from Guardian Gold:")
    for p in sorted(products, key=lambda x: (x["metal"], x["category"], x["weight_oz"])):
        label = p.get("coin_type") or f"{p['bar_brand']} {p['bar_type']}"
        print(f"  {'G' if p['metal']=='gold' else 'S'} {p['category']:4}  "
              f"{label:25}  {p['weight_label']:8}  ${p['buy_price']:>10,.2f}  {p['buy_url']}")