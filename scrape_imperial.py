"""
scrape_imperial.py
Scrapes Imperial Bullion's shop pages to discover which products are currently
listed, then fetches live prices from their JSON pricing feed.

Shop pages supply the direct product URLs. The JSON feed supplies prices.
Only products that appear on the live shop AND have a known JSON key are included.

JSON feed convention:  BuyPrice  = what they pay you (our sell_price)
                       SellPrice = what you pay them  (our buy_price)
"""

import json, re, time, urllib.request

DEALER   = "Imperial Bullion"
FEED_URL = "https://pricing.imperialbullion.com.au/pricing-feed.json"
_BASE    = "https://imperialbullion.com.au/product/"
OZ_PER_G = 1 / 31.1035

# Maps shop slug -> list of JSON pricing-feed keys for that product.
# A slug maps to multiple keys when minted/cast variants share one product page.
SLUG_TO_JSON = {
    # Perth Mint gold bars
    "pm-au-1g":                          ["PMAU1g"],
    "perth-mint-gold-minted-bullion-5-gram": ["PMAU5g"],
    "perth-mint-gold-bullion-100-grams-2":   ["PMAU100g", "PMAU100gMinted"],
    "pm-au-1oz":                         ["PMAU1oz", "PMAU1ozMinted"],
    # ABC gold bars
    "abc-gold-bullion-1-2oz":            ["ABCAU05oz"],
    "abc-gold-bullion-1oz":              ["ABCAU1oz", "ABCAU1ozMinted"],
    "abc-gold-bullion-2oz":              ["ABCAU2oz"],
    "abc-gold-bullion-5oz":              ["ABCAU5oz"],
    "abc-gold-bullion-10oz":             ["ABCAU10oz"],
    "abc-gold-minted-bullion-50-grams":  ["ABCAU50g"],
    "abc-gold-minted-bullion-100-grams": ["ABCAU100g", "ABCAU100gMinted"],
    "abc-gold-bullion-250-gram":         ["ABCAU250g"],
    "abc-gold-bullion-500-gram":         ["ABCAU500g"],
    "abc-gold-bullion-1kg":              ["ABCAU1kg"],
    # Imperial Bullion gold bars
    "imperial-bullion-gold-bullion-1-oz": ["IBAU1oz", "IBAU1ozMinted"],
    # Lunar gold coins (current year)
    "australian-lunar-series-iii-2026-year-of-the-horse-1-10oz-gold-bullion-coin": ["PMAULunar01oz"],
    "australian-lunar-series-iii-2026-year-of-the-horse-1-4oz-gold-bullion-coin":  ["PMAULunar025oz"],
    "australian-lunar-series-iii-2026-year-of-the-horse-2oz-gold-bullion-coin":    ["PMAULunar2oz"],
    # Perth Mint silver kangaroo
    "pm-ag-1oz-kangaroo":                ["PMAG1ozKangaroo"],
    # ABC silver bars
    "abc-silver-bullion-5oz-cast-bar":   ["ABCAG5oz"],
    "abc-silver-bullion-10oz-cast-bar":  ["ABCAG10oz"],
    "abc-silver-bullion-1kg-cast-bar":   ["ABCAG1kg"],
    "abc-silver-bullion-100oz-cast-bar": ["ABCAG100oz"],
    # Imperial Bullion silver bars
    "imperial-bullion-silver-bullion-10-oz": ["IBAG10oz"],
    "imperial-bullion-silver-bullion-1-kg":  ["IBAG1kg"],
    # Generic silver 1oz coins
    "imperial-bullion-silver-bullion-1-oz-britannia-coin":  ["GENAG1ozBritannia"],
    "imperial-bullion-silver-bullion-1-oz-maple-coin":      ["GENAG1ozMaple"],
    "imperial-bullion-silver-bullion-1-oz-krugerand-coin":  ["GENAG1ozKrugerrand"],
    "imperial-bullion-silver-bullion-1-oz-liberty-coin":    ["GENAG1ozLiberty"],
    # Lunar silver coins (current year)
    "australian-lunar-series-iii-2026-year-of-the-horse-2oz-silver-bullion-coin":   ["PMAGLunar2oz"],
    "australian-lunar-series-iii-2026-year-of-the-horse-1kg-silver-bullion-coin-2": ["PMAGLunar1kg"],
}

# Classification data for each JSON pricing-feed key
PRODUCTS = {
    # Perth Mint gold bars (minted)
    "PMAU1g":          ("bar", None, "Perth Mint", "minted", "gold",   1*OZ_PER_G,    "1g"),
    "PMAU5g":          ("bar", None, "Perth Mint", "minted", "gold",   5*OZ_PER_G,    "5g"),
    "PMAU100g":        ("bar", None, "Perth Mint", "minted", "gold",   100*OZ_PER_G,  "100g"),
    "PMAU100gMinted":  ("bar", None, "Perth Mint", "minted", "gold",   100*OZ_PER_G,  "100g"),
    "PMAU1oz":         ("bar", None, "Perth Mint", "cast",   "gold",   1.0,           "1oz"),
    "PMAU1ozMinted":   ("bar", None, "Perth Mint", "minted", "gold",   1.0,           "1oz"),
    # ABC gold bars
    "ABCAU05oz":       ("bar", None, "ABC Bullion", "cast",   "gold",  0.5,           "1/2oz"),
    "ABCAU1oz":        ("bar", None, "ABC Bullion", "cast",   "gold",  1.0,           "1oz"),
    "ABCAU1ozMinted":  ("bar", None, "ABC Bullion", "minted", "gold",  1.0,           "1oz"),
    "ABCAU2oz":        ("bar", None, "ABC Bullion", "cast",   "gold",  2.0,           "2oz"),
    "ABCAU5oz":        ("bar", None, "ABC Bullion", "cast",   "gold",  5.0,           "5oz"),
    "ABCAU10oz":       ("bar", None, "ABC Bullion", "cast",   "gold",  10.0,          "10oz"),
    "ABCAU50g":        ("bar", None, "ABC Bullion", "minted", "gold",  50*OZ_PER_G,   "50g"),
    "ABCAU100g":       ("bar", None, "ABC Bullion", "minted", "gold",  100*OZ_PER_G,  "100g"),
    "ABCAU100gMinted": ("bar", None, "ABC Bullion", "minted", "gold",  100*OZ_PER_G,  "100g"),
    "ABCAU250g":       ("bar", None, "ABC Bullion", "cast",   "gold",  250*OZ_PER_G,  "250g"),
    "ABCAU500g":       ("bar", None, "ABC Bullion", "cast",   "gold",  500*OZ_PER_G,  "500g"),
    "ABCAU1kg":        ("bar", None, "ABC Bullion", "cast",   "gold",  32.1507,       "1kg"),
    # Imperial Bullion gold bars
    "IBAU1oz":         ("bar", None, "Imperial Bullion", "cast",   "gold", 1.0,       "1oz"),
    "IBAU1ozMinted":   ("bar", None, "Imperial Bullion", "minted", "gold", 1.0,       "1oz"),
    # Lunar gold coins
    "PMAULunar01oz":   ("coin", "Lunar", None, None, "gold", 0.1,    "1/10oz"),
    "PMAULunar025oz":  ("coin", "Lunar", None, None, "gold", 0.25,   "1/4oz"),
    "PMAULunar2oz":    ("coin", "Lunar", None, None, "gold", 2.0,    "2oz"),
    # Perth Mint silver kangaroo
    "PMAG1ozKangaroo": ("coin", "Kangaroo",    None, None, "silver", 1.0,    "1oz"),
    # ABC silver bars
    "ABCAG5oz":        ("bar", None, "ABC Bullion", "cast", "silver", 5.0,    "5oz"),
    "ABCAG10oz":       ("bar", None, "ABC Bullion", "cast", "silver", 10.0,   "10oz"),
    "ABCAG1kg":        ("bar", None, "ABC Bullion", "cast", "silver", 32.1507,"1kg"),
    "ABCAG100oz":      ("bar", None, "ABC Bullion", "cast", "silver", 100.0,  "100oz"),
    # Imperial Bullion silver bars
    "IBAG10oz":        ("bar", None, "Imperial Bullion", "cast", "silver", 10.0,    "10oz"),
    "IBAG1kg":         ("bar", None, "Imperial Bullion", "cast", "silver", 32.1507, "1kg"),
    # Generic silver 1oz coins
    "GENAG1ozBritannia":  ("coin", "Britannia",    None, None, "silver", 1.0, "1oz"),
    "GENAG1ozMaple":      ("coin", "Maple Leaf",   None, None, "silver", 1.0, "1oz"),
    "GENAG1ozKrugerrand": ("coin", "Krugerrand",   None, None, "silver", 1.0, "1oz"),
    "GENAG1ozLiberty":    ("coin", "American Eagle", None, None, "silver", 1.0, "1oz"),
    # Lunar silver coins
    "PMAGLunar2oz":    ("coin", "Lunar", None, None, "silver", 2.0,    "2oz"),
    "PMAGLunar1kg":    ("coin", "Lunar", None, None, "silver", 32.1507,"1kg"),
}


def fetch_shop_slugs():
    """Scrape all shop pages and return the set of product slugs currently listed."""
    slugs = set()
    for page in range(1, 6):
        url = f"https://imperialbullion.com.au/shop/page/{page}/"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", errors="replace")
            found = re.findall(
                r'href="https://imperialbullion\.com\.au/product/([^/"]+)/"', html
            )
            if not found:
                break
            slugs.update(found)
        except Exception:
            break
    return slugs


def fetch_json_prices():
    cb  = int(time.time() * 1000)
    url = f"{FEED_URL}?v={cb}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read().decode())


def fetch_products():
    live_slugs  = fetch_shop_slugs()
    price_data  = fetch_json_prices()
    seen_keys   = set()
    results     = []

    for slug, json_keys in SLUG_TO_JSON.items():
        if slug not in live_slugs:
            continue  # product not currently on the shop
        product_url = _BASE + slug + "/"

        for key in json_keys:
            if key in seen_keys:
                continue
            entry = price_data.get(key)
            spec  = PRODUCTS.get(key)
            if not entry or not spec:
                continue

            category, coin_type, bar_brand, bar_type, metal, weight_oz, weight_label = spec
            buy_price  = entry.get("SellPrice")   # SellPrice = what you pay them
            sell_price = entry.get("BuyPrice")    # BuyPrice  = what they pay you
            if (not buy_price or buy_price == 0) and (not sell_price or sell_price == 0):
                continue

            seen_keys.add(key)
            results.append({
                "dealer":       DEALER,
                "metal":        metal,
                "category":     category,
                "coin_type":    coin_type,
                "year":         None,
                "bar_brand":    bar_brand,
                "bar_type":     bar_type,
                "weight_oz":    round(weight_oz, 4),
                "weight_label": weight_label,
                "buy_price":    buy_price  if buy_price  and buy_price  > 0 else None,
                "sell_price":   sell_price if sell_price and sell_price > 0 else None,
                "buy_url":      product_url,
                "available":    True,
            })

    return results


if __name__ == "__main__":
    products = fetch_products()
    print(f"\n{DEALER}: {len(products)} products\n")
    for p in sorted(products, key=lambda x: (x["metal"], x["category"], x["weight_oz"])):
        label = p.get("coin_type") or f"{p['bar_brand']} {p['bar_type']}"
        bp    = f"buy=${p['buy_price']:>10,.2f}" if p["buy_price"] else "buy=         N/A"
        sp    = f"sell=${p['sell_price']:>10,.2f}" if p["sell_price"] else ""
        print(f"  {'G' if p['metal']=='gold' else 'S'} {p['category']:4}  "
              f"{label:28}  {p['weight_label']:8}  {bp}  {sp}")
    gold   = sum(1 for p in products if p["metal"] == "gold")
    silver = sum(1 for p in products if p["metal"] == "silver")
    coins  = sum(1 for p in products if p["category"] == "coin")
    bars   = sum(1 for p in products if p["category"] == "bar")
    print(f"\n  gold={gold}  silver={silver}  coins={coins}  bars={bars}")