"""
scrape_perth.py
Fetches live prices from The Perth Mint's product API.
Returns list of product dicts ready for push_perth.py.
"""

import re, json, urllib.request

DEALER   = "Perth Mint"
BASE_URL = "https://www.perthmint.com"
API_URL  = (
    f"{BASE_URL}/api/search/product/node/1073746516"
    "?pageSize=300&page=1&query=&sortValue=0"
)
OZ_PER_G = 1 / 31.1035

# ── Coin type keywords (checked in order) ─────────────────────────────────────

COIN_TYPES = [
    ("mother and baby kangaroo", "Kangaroo"),
    ("kangaroo",                 "Kangaroo"),
    ("kookaburra",               "Kookaburra"),
    ("koala",                    "Koala"),
    ("brumby",                   "Brumby"),
    ("emu",                      "Emu"),
    ("super pit",                "Super Pit"),
    ("outback",                  "Outback"),
    ("year of the",              "Lunar"),
    ("lunar",                    "Lunar"),
    ("swan",                     "Swan"),
    ("chinese myths",            "Chinese Myths"),
    ("phoenix",                  "Chinese Myths"),
    ("pillar dollar",            "Pillar Dollar"),
    ("dragon",                   "Dragon"),
]

# ── Metal / weight / year helpers ─────────────────────────────────────────────

def extract_metal(title):
    t = title.lower()
    if "platinum" in t: return "platinum"
    if "gold"     in t: return "gold"
    if "silver"   in t: return "silver"
    return None


def extract_year(title):
    m = re.search(r"\b(20\d{2})\b", title)
    return int(m.group(1)) if m else None


def parse_weight(title):
    t = title.lower()
    # "1 Kilo" / "1 kilo"
    m = re.search(r"(\d+(?:\.\d+)?)\s*kilo\b", t)
    if m:
        kg  = float(m.group(1))
        oz  = round(kg * 1000 * OZ_PER_G, 4)
        lbl = f"{int(kg)}kg" if kg == int(kg) else f"{kg}kg"
        return oz, lbl
    # grams (e.g. "1g", "100g")
    m = re.search(r"(\d+(?:\.\d+)?)\s*g\b", t)
    if m:
        g   = float(m.group(1))
        oz  = round(g * OZ_PER_G, 4)
        lbl = f"{int(g)}g" if g == int(g) else f"{g}g"
        return oz, lbl
    # fractional oz
    FRACS = [
        (r"1/20\s*oz", 0.05,  "1/20oz"),
        (r"1/10\s*oz", 0.1,   "1/10oz"),
        (r"1/4\s*oz",  0.25,  "1/4oz"),
        (r"1/2\s*oz",  0.5,   "1/2oz"),
    ]
    for pat, val, lbl in FRACS:
        if re.search(pat, t):
            return val, lbl
    # whole or decimal oz
    m = re.search(r"(\d+(?:\.\d+)?)\s*oz\b", t)
    if m:
        oz  = float(m.group(1))
        lbl = f"{int(oz)}oz" if oz == int(oz) else f"{oz}oz"
        return oz, lbl
    return None, None


# ── Product classification ────────────────────────────────────────────────────

def classify(title, api_category):
    cat = api_category.lower()
    t   = title.lower()

    if "coin" in cat or "bullion" in cat and "bar" not in t:
        coin_type = None
        for kw, ct in COIN_TYPES:
            if kw in t:
                coin_type = ct
                break
        return {"category": "coin", "coin_type": coin_type,
                "bar_brand": None, "bar_type": None}

    bar_type = "cast" if "cast" in cat else ("minted" if "minted" in cat else None)
    if bar_type is None:
        bar_type = "cast" if "cast" in t else "minted" if "minted" in t else None
    return {"category": "bar", "coin_type": None,
            "bar_brand": "Perth Mint", "bar_type": bar_type}


# ── Fetcher ───────────────────────────────────────────────────────────────────

def fetch_products():
    req = urllib.request.Request(API_URL, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                data = json.loads(r.read())
            break
        except Exception as e:
            if attempt == 2:
                raise
            import time; time.sleep(5)

    products  = []
    seen_keys = set()

    for p in data["result"]["products"]:
        if not p.get("canAddToCart"):
            continue

        title = p["title"]
        # Skip bulk tube purchases
        if "in tube" in title.lower():
            continue

        metal = extract_metal(title)
        if metal not in ("gold", "silver"):
            continue

        price_obj = p["prices"].get("basePrice") or p["prices"].get("adjustedPrice")
        if not price_obj:
            continue
        buy_price = price_obj["price"]
        if not buy_price or buy_price <= 0:
            continue

        weight_oz, weight_label = parse_weight(title)
        if weight_oz is None:
            continue

        api_cat = p.get("category", "")
        meta    = classify(title, api_cat)
        year    = extract_year(title) if meta["category"] == "coin" else None

        dedup = (metal, meta["category"], meta["coin_type"],
                 meta["bar_brand"], meta["bar_type"], weight_oz, year)
        if dedup in seen_keys:
            continue
        seen_keys.add(dedup)

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
            "buy_url":      p["link"],
            "available":    True,
        })

    return products


if __name__ == "__main__":
    products = fetch_products()
    print(f"{len(products)} products scraped:")
    for p in products:
        label = p.get("coin_type") or f"{p.get('bar_brand')} {p.get('bar_type')}"
        yr    = f" {p['year']}" if p.get("year") else ""
        print(f"  {'G' if p['metal']=='gold' else 'S'} {p['category']:4}  "
              f"{label:25}  {p['weight_label']:6}  ${p['buy_price']:>10,.2f}  {yr}")