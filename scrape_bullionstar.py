"""
scrape_bullionstar.py
Fetches all products from BullionStar NZ via the filter/desktop API (paginated).
Each product carries originalPrice (the true 1-piece retail price) and fineWeight.

API:
  GET /product/filter/desktop?currency=AUD&locationId=3&name={gold|silver}&page={n}
  → result.groups[] each containing products[]
  Paginate until pagination.nextPage is absent.
"""

import re, json, time, urllib.request, urllib.error

DEALER   = "BullionStar"
BASE_URL = "https://www.bullionstar.co.nz"
UA       = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
OZ_PER_G = 1 / 31.1035

# ── Groups to skip entirely ───────────────────────────────────────────────────

SKIP_GROUP_KEYWORDS = [
    "bullion savings program",   # BSP — digital grams, not physical
    "lbma good delivery",        # 400oz institutional bars
    "pre-owned",                 # second-hand
    "1,000 oz",                  # institutional 1000oz bar
    "queen's beast",             # UK limited collector series
    "walking liberty",           # novelty rounds
    "niue",                      # collector coin
    "silver fern",               # NZ collector coin
    "double dragon",             # collector
    "australian double dragon",
]

# ── Product-level skip (checked against title and fineWeight) ─────────────────

SKIP_PRODUCT_KEYWORDS = [
    "combibar",          # multi-piece wafer — individual piece weight != listed weight
    " anda ",            # ANDA show special proof (space-padded to avoid matching "panda")
    "circulated",        # used/circulated
    "proof coin set",
    "proof set",
]

# ── Coin type patterns ────────────────────────────────────────────────────────

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

COIN_TYPE_PATTERNS = [
    (r"kangaroo|nugget",  "Kangaroo"),
    (r"kookaburra",       "Kookaburra"),
    (r"koala",            "Koala"),
    (r"philharmonic",     "Philharmonic"),
    (r"britannia",        "Britannia"),
    (r"maple.leaf",       "Maple Leaf"),
    (r"krugerrand",       "Krugerrand"),
    (r"silver.eagle|gold.eagle|american.eagle", "American Eagle"),
    (r"gold.buffalo|silver.buffalo|american.buffalo", "American Buffalo"),
    (r"panda",            "Panda"),
    (r"libertad",         "Libertad"),
]

# ── Bar brand keywords ────────────────────────────────────────────────────────

BAR_BRAND_KEYWORDS = [
    ("pamp",              "PAMP"),
    ("perth mint",        "Perth Mint"),
    ("argor-heraeus",     "Argor-Heraeus"),
    ("argor",             "Argor-Heraeus"),
    ("heraeus",           "Heraeus"),
    ("valcambi",          "Valcambi"),
    ("abc bullion",       "ABC Bullion"),
    ("abc",               "ABC Bullion"),
    ("scottsdale",        "Scottsdale"),
    ("johnson matthey",   "Johnson Matthey"),
    ("royal canadian mint","Royal Canadian Mint"),
    ("nzpure",            "NZPure"),
    ("new zealand pure",  "NZPure"),
    ("morris and watson", "Morris & Watson"),
    ("morris & watson",   "Morris & Watson"),
    ("britannia bar",     "Royal Mint"),
    ("bullionstar",       "BullionStar"),
]


# ── Classification ────────────────────────────────────────────────────────────

def classify_group(title):
    """Return classification dict or None to skip this group."""
    t = title.lower()

    metal = "gold" if "gold" in t else ("silver" if "silver" in t else None)
    if metal is None:
        return None

    is_coin = any(w in t for w in ("coin", "coins", "round", "rounds"))
    is_bar  = any(w in t for w in ("bar", "bars"))

    if not is_coin and not is_bar:
        return None

    category = "coin" if is_coin else "bar"

    if category == "coin":
        coin_type = _lunar_coin_type(t) or next(
            (ct for pat, ct in COIN_TYPE_PATTERNS if re.search(pat, t)),
            None
        )
        if coin_type is None:
            return None
        return {"metal": metal, "category": "coin",
                "coin_type": coin_type, "bar_brand": None, "bar_type": None}

    else:
        bar_brand = next(
            (brand for kw, brand in BAR_BRAND_KEYWORDS if kw in t),
            "BullionStar"
        )
        return {"metal": metal, "category": "bar",
                "coin_type": None, "bar_brand": bar_brand, "bar_type": None}


# ── Weight parsing from fineWeight field ──────────────────────────────────────

def parse_fine_weight(fw_text):
    """Parse fineWeight like '1 troy oz (31.1 gram)', '50 gram (1.608 troy oz)', '1 kg (32.151 troy oz)'.
    Returns (weight_oz, weight_label, suffix) where suffix is text after ' - '.
    """
    if not fw_text:
        return None, None, ""

    parts = fw_text.split(" - ", 1)
    weight_part = parts[0].strip()
    suffix = parts[1].strip() if len(parts) > 1 else ""
    t = weight_part.lower()

    # kg: "1 kg", "3.11 kg (100 troy oz)"
    m = re.search(r'(\d+(?:\.\d+)?)\s*kg', t)
    if m:
        kg = float(m.group(1))
        oz = round(kg * 1000 * OZ_PER_G, 4)
        # Prefer whole-number troy oz label (e.g. "100oz" over "3.11kg")
        mt = re.search(r'(\d+(?:\.\d+)?)\s*troy\s*oz', t)
        if mt:
            troy = float(mt.group(1))
            if troy == int(troy) and abs(troy - oz) < 1:
                return oz, f"{int(troy)}oz", suffix
        lbl = f"{int(kg) if kg == int(kg) else kg}kg"
        return oz, lbl, suffix

    # troy oz: "1 troy oz", "0.5 troy oz", "1.608 troy oz (50 gram)"
    m = re.search(r'(\d+(?:\.\d+)?)\s*troy\s*oz', t)
    if m:
        oz = float(m.group(1))
        FRACS = {0.05: "1/20oz", 0.1: "1/10oz", 0.25: "1/4oz", 0.5: "1/2oz"}
        # Standard troy oz sizes — keep as oz label
        STANDARD_OZ = {0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 32.15}
        is_standard = any(abs(oz - s) < 0.015 for s in STANDARD_OZ)
        if not is_standard:
            # Non-standard oz (e.g. 1.608oz = 50g bar) — prefer gram label if present
            mg = re.search(r'(\d+(?:\.\d+)?)\s*gram', t)
            if mg:
                g = float(mg.group(1))
                g_oz = round(g * OZ_PER_G, 4)
                if abs(g_oz - oz) < 0.003:
                    lbl = f"{int(g) if g == int(g) else g}g"
                    return g_oz, lbl, suffix
        lbl = FRACS.get(oz, f"{int(oz) if oz == int(oz) else oz}oz")
        return oz, lbl, suffix

    # grams: "50 gram", "30 gram"
    m = re.search(r'(\d+(?:\.\d+)?)\s*gram', t)
    if m:
        g = float(m.group(1))
        oz = round(g * OZ_PER_G, 4)
        lbl = f"{int(g) if g == int(g) else g}g"
        return oz, lbl, suffix

    return None, None, suffix


def parse_aud_price(price_str):
    """'AU$1,234.56' → 1234.56"""
    if not price_str:
        return None
    cleaned = re.sub(r'[^\d.]', '', str(price_str))
    try:
        return float(cleaned)
    except ValueError:
        return None


# ── API calls ─────────────────────────────────────────────────────────────────

def fetch_pages(metal):
    """Fetch all paginated result groups for one metal (gold or silver)."""
    all_groups = []
    page = 1
    while True:
        url = (f"{BASE_URL}/product/filter/desktop"
               f"?currency=AUD&locationId=3&name={metal}&page={page}")
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        groups = data["result"]["groups"]
        all_groups.extend(groups)
        nxt = data.get("pagination", {}).get("nextPage")
        if not nxt:
            break
        page += 1
        time.sleep(0.25)
    return all_groups


# ── Main scrape ───────────────────────────────────────────────────────────────

def fetch_products():
    # Collect all candidates first, then deduplicate keeping cheapest per key
    candidates = {}   # key → product dict (cheapest available wins)

    for metal in ("gold", "silver"):
        print(f"  Fetching {metal}…")
        groups = fetch_pages(metal)
        print(f"    {len(groups)} groups from API")

        for group in groups:
            group_title = group.get("title", "")

            # Skip entire groups
            if any(kw in group_title.lower() for kw in SKIP_GROUP_KEYWORDS):
                continue

            classification = classify_group(group_title)
            if classification is None:
                continue

            for prod in group.get("products", []):
                status    = prod.get("status", "")
                available = status in ("IN_STOCK", "PRE_SALE")

                title    = prod.get("title", "")
                title_lc = " " + title.lower() + " "
                fw_raw   = prod.get("fineWeight", "")
                fw_lc    = " " + fw_raw.lower() + " "

                # Product-level skips
                if any(kw in title_lc or kw in fw_lc for kw in SKIP_PRODUCT_KEYWORDS):
                    continue

                weight_oz, weight_label, suffix = parse_fine_weight(fw_raw)
                if weight_oz is None or weight_oz <= 0:
                    continue

                # bar_type from suffix ("Cast Bar" → cast, else minted)
                bar_type = None
                if classification["category"] == "bar":
                    bar_type = "cast" if "cast" in suffix.lower() else "minted"

                buy_price = parse_aud_price(
                    prod.get("originalPrice") or prod.get("price")
                )
                if not buy_price:
                    continue

                buy_url = prod.get("url", "")

                key = (
                    classification["metal"],
                    classification["category"],
                    classification.get("coin_type"),
                    classification.get("bar_brand"),
                    bar_type,
                    weight_oz,
                )

                existing = candidates.get(key)
                if existing is None:
                    # First time seeing this key
                    candidates[key] = {
                        "dealer":       DEALER,
                        "metal":        classification["metal"],
                        "category":     classification["category"],
                        "coin_type":    classification.get("coin_type"),
                        "bar_brand":    classification.get("bar_brand"),
                        "bar_type":     bar_type,
                        "weight_oz":    weight_oz,
                        "weight_label": weight_label,
                        "year":         None,
                        "buy_price":    buy_price,
                        "sell_price":   None,
                        "buy_url":      buy_url,
                        "available":    available,
                    }
                else:
                    # Keep the cheaper available price; prefer available over unavailable
                    if available and not existing["available"]:
                        candidates[key] = {**existing, "buy_price": buy_price,
                                           "buy_url": buy_url, "available": True}
                    elif available == existing["available"] and buy_price < existing["buy_price"]:
                        candidates[key] = {**existing, "buy_price": buy_price,
                                           "buy_url": buy_url}

    return list(candidates.values())


if __name__ == "__main__":
    products = fetch_products()
    print(f"\n{len(products)} products from BullionStar:")
    for p in sorted(products, key=lambda x: (x["metal"], x["category"], x["weight_oz"])):
        label = p.get("coin_type") or f"{p.get('bar_brand','')} {p.get('bar_type','')}"
        avail = "✓" if p["available"] else "✗"
        print(f"  {'G' if p['metal']=='gold' else 'S'} {p['category']:4}  "
              f"{label:32}  {p['weight_label']:8}  "
              f"buy=${p['buy_price']:>10,.2f}  {avail}")