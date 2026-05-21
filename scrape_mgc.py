"""
scrape_mgc.py
Scrapes Melbourne Gold Company product listing pages for direct URLs and buy prices.
Sell prices (buyback) are cross-referenced from the price list pages.

Listing pages (price + direct product URL per item):
  buy-gold-bullion-bars-items.php      (gold bars)
  buy-silver-bullion-bars-items.php    (silver bars)
  buy-gold-coins-silver-coins-items.php (gold + silver coins)

Price list pages (sell/buyback prices, no individual URLs):
  gold-price-aud.php
  silver-price-aud.php
"""

import re, urllib.request

DEALER   = "Melbourne Gold Company"
OZ_PER_G = 1 / 31.1035
_MGC     = "https://www.melbournegoldcompany.com.au/buy-bullion/"

LISTING_PAGES = [
    (_MGC + "buy-gold-bullion-bars-items.php",        "gold"),
    (_MGC + "buy-silver-bullion-bars-items.php",      "silver"),
    (_MGC + "buy-gold-coins-silver-coins-items.php",  None),   # metal detected from price class
]

PRICE_PAGES = [
    ("https://www.melbournegoldcompany.com.au/gold-price-aud.php",   "gold"),
    ("https://www.melbournegoldcompany.com.au/silver-price-aud.php", "silver"),
]

FRAC_MAP = {"1/20": 0.05, "1/10": 0.1, "1/4": 0.25, "1/2": 0.5}

LUNAR_ANIMALS = [
    ("horse", "Horse"), ("snake", "Snake"), ("dragon", "Dragon"),
    ("rabbit", "Rabbit"), ("tiger", "Tiger"), ("ox", "Ox"),
    ("mouse", "Mouse"), ("rat", "Mouse"), ("pig", "Pig"), ("dog", "Dog"),
    ("rooster", "Rooster"), ("monkey", "Monkey"), ("goat", "Goat"), ("sheep", "Goat"),
]

COIN_TYPES = [
    (r"kangaroo",        "Kangaroo"),
    (r"kookaburra",      "Kookaburra"),
    (r"koala",           "Koala"),
    (r"emu(?!\w)",       "Emu"),
    (r"outback",         "Outback"),
    (r"southern.cross",  "Southern Cross"),
    (r"maple",           "Maple Leaf"),
    (r"britannia",       "Britannia"),
    (r"krugerrand",      "Krugerrand"),
    (r"philharmonic",    "Philharmonic"),
    (r"american eagle|us eagle", "American Eagle"),
    (r"lunar",           "Lunar"),
]

BAR_BRANDS = [
    ("agc",                     "Melbourne Gold Company"),
    ("australian gold capital", "Melbourne Gold Company"),
    ("perth mint",              "Perth Mint"),
    ("abc bullion",             "ABC Bullion"),
    ("abc ",                    "ABC Bullion"),
    ("pamp",                    "PAMP"),
    ("valcambi",                "Valcambi"),
]

SKIP_KEYWORDS = [
    "granules", "unallocated", "pool allocated", "pool-allocated",
    "luong", "tael", "37.5g", "375g",
    "proof", "numismatic", "collector",
    "20oz", "50oz", "100oz", "400oz", "5kg", "10kg", "15kg",
    "platinum", "palladium",
    "coin set", "jewellery",
    "24 karat",
    "canada goose", "1966", "50c piece", "dealers choice",
    "untamed landscape", "diwali", "wonders of australia",
]


def _lunar_type(t):
    for kw, name in LUNAR_ANIMALS:
        if kw in t and ("lunar" in t or "year of" in t or "horse coin" in t or
                        "snake coin" in t or "dragon coin" in t or "rabbit coin" in t):
            return f"Lunar {name}"
    return None


def parse_weight(t):
    m = re.search(r'(\d+/\d+)\s*oz', t)
    if m:
        frac = m.group(1)
        oz = FRAC_MAP.get(frac)
        if oz is None:
            n, d = frac.split("/"); oz = round(int(n) / int(d), 6)
        return oz, f"{frac}oz"
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:kg|kilogram)', t)
    if m:
        kg = float(m.group(1))
        return round(kg * 1000 * OZ_PER_G, 4), f"{int(kg) if kg == int(kg) else kg}kg"
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:gram|grams|g)\b', t)
    if m:
        g = float(m.group(1))
        return round(g * OZ_PER_G, 4), f"{int(g) if g == int(g) else g}g"
    m = re.search(r'(\d+(?:\.\d+)?)\s*oz\b', t)
    if m:
        oz = float(m.group(1))
        return oz, f"{int(oz) if oz == int(oz) else oz}oz"
    return None, None


def parse_price(s):
    if not s or "n/a" in s.lower():
        return None
    val = s.replace("$", "").replace(",", "").replace("AUD", "").strip()
    m = re.search(r'[\d]+(?:\.\d+)?', val)
    return float(m.group(0)) if m else None


def classify(title, metal):
    t = title.lower()
    if any(kw in t for kw in SKIP_KEYWORDS):
        return None
    lunar = _lunar_type(t)
    if lunar:
        return {"category": "coin", "coin_type": lunar, "bar_brand": None, "bar_type": None}
    coin = next((ct for pat, ct in COIN_TYPES if re.search(pat, t)), None)
    if coin:
        return {"category": "coin", "coin_type": coin, "bar_brand": None, "bar_type": None}
    is_bar = any(kw in t for kw in ("bar", "cast", "minted", "tablet", "certicard"))
    if not is_bar:
        return None
    brand = next((b for kw, b in BAR_BRANDS if kw in t), "Melbourne Gold Company")
    bt = "minted" if any(kw in t for kw in ("minted", "tablet", "certicard")) else "cast"
    return {"category": "bar", "bar_brand": brand, "bar_type": bt, "coin_type": None}


def _fetch_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        return urllib.request.urlopen(req, timeout=20).read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  ERROR fetching {url}: {e}")
        return ""


def fetch_listing(url, metal_hint):
    """Scrape one listing page. Returns list of {slug, name, buy_price, metal}."""
    html = _fetch_html(url)
    if not html:
        return []

    items = []
    # Split on product-level <li> boundaries (avoids nested bulk-pricing <li> elements)
    li_blocks = re.split(r'<li>\s*<div class="cart-item-img">', html)
    for block in li_blocks[1:]:
        # Slug from first info.php href
        slug_m = re.search(r'href=["\']([^"\']+info\.php)["\']', block)
        if not slug_m:
            continue
        slug = slug_m.group(1)

        # Product name - strip inner HTML tags (e.g. <small>oz</small>)
        name_m = re.search(
            r'class="product-name"[^>]*>.*?<a[^>]*>(.*?)</a>', block, re.DOTALL
        )
        if not name_m:
            continue
        name = re.sub(r'<[^>]+>', '', name_m.group(1)).strip()
        name = re.sub(r'\s+', ' ', name)

        # Price (coins page uses product-price-gold for everything)
        price_m = re.search(
            r'class="product-price-(?:gold|silver)"[^>]*>.*?\$([\d,]+(?:\.\d+)?)',
            block, re.DOTALL
        )
        if not price_m:
            continue
        try:
            buy_price = float(price_m.group(1).replace(",", ""))
        except ValueError:
            continue

        if metal_hint:
            metal = metal_hint
        else:
            # Mixed coins page: detect from name since all use product-price-gold
            t = name.lower()
            if "silver" in t:
                metal = "silver"
            elif "gold" in t:
                metal = "gold"
            else:
                continue  # cannot determine metal

        items.append({"slug": slug, "name": name, "buy_price": buy_price, "metal": metal})

    return items


def fetch_sell_prices():
    """Scrape price list pages for buyback prices.
    Returns dict keyed by (metal, category, coin_type, bar_brand, bar_type, weight_label)."""
    sell_map = {}
    for url, metal in PRICE_PAGES:
        html = _fetch_html(url)
        if not html:
            continue
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S)
        for row in rows:
            cells_raw = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
            if len(cells_raw) < 3:
                continue
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells_raw]
            name = cells[0]
            if not name or len(name) < 5:
                continue
            t = name.lower()
            weight_oz, weight_label = parse_weight(t)
            if weight_oz is None:
                continue
            meta = classify(name, metal)
            if meta is None:
                continue
            sell_price = parse_price(cells[2])
            if sell_price is None:
                continue
            key = (metal, meta["category"], meta.get("coin_type"),
                   meta.get("bar_brand"), meta.get("bar_type"), weight_label)
            sell_map.setdefault(key, sell_price)
    return sell_map


def fetch_products():
    seen_keys = set()
    results = []

    sell_prices = fetch_sell_prices()

    for url, metal_hint in LISTING_PAGES:
        for item in fetch_listing(url, metal_hint):
            name   = item["name"]
            metal  = item["metal"]
            t      = name.lower()

            weight_oz, weight_label = parse_weight(t)
            if weight_oz is None:
                continue
            meta = classify(name, metal)
            if meta is None:
                continue

            dedup_key = (metal, meta["category"], meta.get("coin_type"),
                         meta.get("bar_brand"), meta.get("bar_type"), weight_oz)
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            sell_key  = (metal, meta["category"], meta.get("coin_type"),
                         meta.get("bar_brand"), meta.get("bar_type"), weight_label)
            sell_price = sell_prices.get(sell_key)

            results.append({
                "dealer":       DEALER,
                "metal":        metal,
                "category":     meta["category"],
                "coin_type":    meta["coin_type"],
                "year":         None,
                "bar_brand":    meta["bar_brand"],
                "bar_type":     meta["bar_type"],
                "weight_oz":    weight_oz,
                "weight_label": weight_label,
                "buy_price":    item["buy_price"],
                "sell_price":   sell_price,
                "buy_url":      _MGC + item["slug"],
                "available":    True,
            })

    return results


if __name__ == "__main__":
    products = fetch_products()
    print(f"\n{DEALER}: {len(products)} products\n")
    for p in sorted(products, key=lambda x: (x["metal"], x["category"], x["weight_oz"])):
        label = p.get("coin_type") or f"{p['bar_brand']} {p['bar_type']}"
        bp    = f"${p['buy_price']:>10,.2f}" if p["buy_price"] else "         N/A"
        sp    = f"sell=${p['sell_price']:>10,.2f}" if p["sell_price"] else ""
        url   = p["buy_url"].split("/buy-bullion/")[-1]
        print(f"  {'G' if p['metal']=='gold' else 'S'} {p['category']:4}  "
              f"{label:30}  {p['weight_label']:8}  buy={bp}  {sp}  {url}")
    gold   = sum(1 for p in products if p["metal"] == "gold")
    silver = sum(1 for p in products if p["metal"] == "silver")
    coins  = sum(1 for p in products if p["category"] == "coin")
    bars   = sum(1 for p in products if p["category"] == "bar")
    print(f"\n  gold={gold}  silver={silver}  coins={coins}  bars={bars}")