"""
scrape_abc.py
Discovers products from ABC Bullion category pages (gold, silver, coins),
then fetches each individual product page for price + availability.
"""

import re, time, urllib.request, urllib.error

DEALER   = "ABC Bullion"
BASE_URL = "https://www.abcbullion.com.au"
OZ_PER_G = 1 / 31.1035
DELAY    = 0.35

CATEGORY_PAGES = [
    f"{BASE_URL}/store/gold",
    f"{BASE_URL}/store/silver",
    f"{BASE_URL}/store/Bullion-Coins",
]

# ── Slug-level skip filters ────────────────────────────────────────────────────

SKIP_SLUG = [
    "pool-allocated",        # unallocated metal, not physical
    "luong", "tael",         # non-standard Asian weights
    "400oz",                 # 400oz institutional bar
    "blister-pack",          # packaging variant — same coin, different pack
    "monster-box",           # bulk packaging
    "box-of-",               # bulk boxes
    "high-relief",           # numismatic variant
    "platinum", "palladium",
    "eureka",                # ABC novelty brand (not widely recognised bullion)
]

INCLUDE_SLUG = [
    "gold", "silver",        # at least one metal keyword
    "bar", "cast", "minted", "tablet",
    "kangaroo", "kookaburra", "koala", "maple", "britannia",
    "krugerrand", "philharmonic", "lunar", "emu",
    "southern-cross", "kiwi", "lizard", "sailfish", "kangaroo",
]

# ── Weight parsing ─────────────────────────────────────────────────────────────

FRAC_MAP = {"1/20": 0.05, "1/10": 0.1, "1/4": 0.25, "1/2": 0.5}


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

COIN_TYPES = [
    (r"kangaroo",                   "Kangaroo"),
    (r"kookaburra",                 "Kookaburra"),
    (r"koala",                      "Koala"),
    (r"emu(?!\w)",                  "Emu"),
    (r"outback",                    "Outback"),
    (r"southern.cross",             "Southern Cross"),
    (r"lunar|year.of.the|snake|horse|dragon|rabbit|tiger|ox", "Lunar"),
    (r"britannia",                  "Britannia"),
    (r"maple",                      "Maple Leaf"),
    (r"krugerrand",                 "Krugerrand"),
    (r"philharmonic",               "Philharmonic"),
    (r"kiwi",                       "Kiwi"),
    (r"thorny.lizard|lizard",       "Thorny Lizard"),
    (r"sailfish",                   "Sailfish"),
]

BAR_BRANDS = [
    ("perth mint",   "Perth Mint"),
    ("abc bullion",  "ABC Bullion"),
    ("abc",          "ABC Bullion"),
    ("pamp",         "PAMP"),
    ("britannia",    "Britannia"),    # Britannia minted bar (not coin)
]


def classify(title):
    t = title.lower()
    is_bar = any(w in t for w in ("bar", "tablet", "cast", "minted bar"))
    # Minted coins have "minted" too — distinguish by "bar" being present
    if "minted bar" in t or "cast bar" in t:
        is_bar = True
    if "coin" in t:
        is_bar = False
    if is_bar:
        bar_type  = "minted" if "minted" in t or "tablet" in t else "cast"
        bar_brand = next((b for kw, b in BAR_BRANDS if kw in t), "ABC Bullion")
        return {"category": "bar", "bar_brand": bar_brand, "bar_type": bar_type, "coin_type": None}
    coin_type = next((ct for pat, ct in COIN_TYPES if re.search(pat, t)), None)
    if coin_type is None:
        return None
    return {"category": "coin", "coin_type": coin_type, "bar_brand": None, "bar_type": None}


def metal_from_title(title):
    t = title.lower()
    return "silver" if "silver" in t else "gold" if "gold" in t else None


# ── Product discovery ──────────────────────────────────────────────────────────

def get_product_urls():
    seen_slugs = set()
    urls = []

    for cat_url in CATEGORY_PAGES:
        req = urllib.request.Request(cat_url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")

        raw = re.findall(r'/store/([^"\'<>\s,]+)', html)
        for s in raw:
            parts = s.strip("/").split("/")
            # Use the longest segment as the slug
            slug = max(parts, key=len) if parts else ""
            if len(slug) < 8 or not any(c.isdigit() for c in slug):
                continue
            if slug in seen_slugs:
                continue
            if any(kw in slug for kw in SKIP_SLUG):
                continue
            if not any(kw in slug for kw in INCLUDE_SLUG):
                continue
            seen_slugs.add(slug)
            # Determine canonical category path
            if slug.startswith("g"):
                cat = "gold" if "gold" in slug else "Bullion-Coins"
            else:
                cat = "silver"
            urls.append(f"{BASE_URL}/store/{cat}/{slug}")

    return urls


# ── Individual product page scraping ──────────────────────────────────────────

def scrape_product(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError:
        return None

    # ABC uses: <p class="price-container" itemprop="price">$<span class="price">NNNN</span>
    price_m = re.search(r'class="price[^"]*"[^>]*>\$?\s*<span[^>]*>([\d,]+\.?\d*)</span>', html)
    if not price_m:
        return None

    # Title
    title_m = re.search(r'<h1[^>]*class="[^"]*page-header[^"]*"[^>]*>(.*?)</h1>', html, re.S)
    if not title_m:
        title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
    if not title_m:
        return None

    price = float(price_m.group(1).replace(',', ''))
    title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
    return {"title": title, "price": price, "url": url}


# ── Main ──────────────────────────────────────────────────────────────────────

def fetch_products():
    urls = get_product_urls()
    print(f"  {len(urls)} candidate product URLs")

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
        key = (metal, meta["category"], meta.get("coin_type"),
               meta.get("bar_brand"), meta.get("bar_type"), weight_oz)
        if key in seen_keys:
            continue
        seen_keys.add(key)
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
            "buy_url":      result["url"],
            "available":    True,
        })

    return products


if __name__ == "__main__":
    products = fetch_products()
    print(f"\n{len(products)} products scraped from ABC Bullion:")
    for p in sorted(products, key=lambda x: (x["metal"], x["category"], x["weight_oz"])):
        label = p.get("coin_type") or f"{p['bar_brand']} {p['bar_type']}"
        print(f"  {'G' if p['metal']=='gold' else 'S'} {p['category']:4}  "
              f"{label:25}  {p['weight_label']:8}  ${p['buy_price']:>10,.2f}  {p['buy_url']}")