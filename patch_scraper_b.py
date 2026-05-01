"""
patch_scraper_b.py — 3 changes to scraper_v3.py:
1. Populate DEALER_PRICE_SELECTORS with WooCommerce/Magento selectors
2. Add selector fallback in scrape_product (use full text if element not found)
3. Add Silver Lunar 1oz, Gold Lunar 1oz, Silver Koala 1oz, Silver Bar 100oz to CATALOGUE
"""
with open("scraper_v3.py", "r", encoding="utf-8") as f:
    c = f.read().replace("\r\n", "\n")

errors = []

# ── 1. Populate DEALER_PRICE_SELECTORS ──────────────────────────────────────
OLD1 = 'DEALER_PRICE_SELECTORS = {}'

NEW1 = \
'DEALER_PRICE_SELECTORS = {\n' \
'    # WooCommerce dealers: p.price scopes to the product price, avoiding spot-price widgets\n' \
'    "Guardian Gold":  "p.price",\n' \
'    "Gold Stackers":  "p.price",\n' \
'    "Swan Bullion":   "p.price",\n' \
'    "Jaggards":       "p.price",\n' \
'    # Magento (KJC): finalPrice data attribute holds the true product price\n' \
'    "KJC Bullion":    "[data-price-type=\'finalPrice\'] .price",\n' \
'}'

if OLD1 in c:
    c = c.replace(OLD1, NEW1)
    print("✅ DEALER_PRICE_SELECTORS populated")
else:
    errors.append("❌ DEALER_PRICE_SELECTORS anchor not found")

# ── 2. Add fallback in scrape_product if selector element not found ──────────
OLD2 = \
'        sel = DEALER_PRICE_SELECTORS.get(dealer)\n' \
'        if sel:\n' \
'            el = await page.query_selector(sel)\n' \
'            price_text = await el.inner_text() if el else ""\n' \
'            price = extract_price(price_text, min_val, max_val) if price_text else None\n' \
'        else:\n' \
'            price = extract_price(text, min_val, max_val)'

NEW2 = \
'        sel = DEALER_PRICE_SELECTORS.get(dealer)\n' \
'        if sel:\n' \
'            el = await page.query_selector(sel)\n' \
'            if el:\n' \
'                price_text = await el.inner_text()\n' \
'                price = extract_price(price_text, min_val, max_val)\n' \
'            else:\n' \
'                price = extract_price(text, min_val, max_val)  # element not found — fall back\n' \
'        else:\n' \
'            price = extract_price(text, min_val, max_val)'

if OLD2 in c:
    c = c.replace(OLD2, NEW2)
    print("✅ scrape_product selector fallback added")
else:
    errors.append("❌ scrape_product selector block anchor not found")

# ── 3. Add new CATALOGUE entries before closing brace ───────────────────────
OLD3 = \
'    "Silver Buyback 1oz Bar": {\n' \
'        "metal":"silver","category":"bar","bar_brand":"Generic","bar_type":"buyback",\n' \
'        "weight_oz":1.0,"min_aud":80,"max_aud":180,\n' \
'        "dealers":[\n' \
'            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/buyback-silver-bar-1-oz/"},\n' \
'        ],\n' \
'    },\n' \
'\n' \
'}'

NEW3 = \
'    "Silver Buyback 1oz Bar": {\n' \
'        "metal":"silver","category":"bar","bar_brand":"Generic","bar_type":"buyback",\n' \
'        "weight_oz":1.0,"min_aud":80,"max_aud":180,\n' \
'        "dealers":[\n' \
'            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/buyback-silver-bar-1-oz/"},\n' \
'        ],\n' \
'    },\n' \
'\n' \
'    # ══════════════════════════════════════════════════════════════════════════\n' \
'    # LUNAR — Silver + Gold (Perth Mint annual series, 2026 Year of the Horse)\n' \
'    # ══════════════════════════════════════════════════════════════════════════\n' \
'\n' \
'    "Silver Lunar 1oz": {\n' \
'        "metal":"silver","category":"coin","coin_type":"Lunar",\n' \
'        "weight_oz":1.0,"min_aud":95,"max_aud":250,\n' \
'        "dealers":[\n' \
'            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-australian-year-of-the-horse-silver-bullion-coin/3003811"},\n' \
'            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/bullion-coins/australian-lunar-series-iii-2026-year-of-the-horse-1oz-silver-bullion-coin/", "wait":8000},\n' \
'            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Silver-Coin-2026-Year-of-the-Horse-Perth-Mint/ID/637"},\n' \
'            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/perth-mint-2026-lunar-horse-silver-coin-1-oz/"},\n' \
'        ],\n' \
'    },\n' \
'\n' \
'    "Gold Lunar 1oz": {\n' \
'        "metal":"gold","category":"coin","coin_type":"Lunar",\n' \
'        "weight_oz":1.0,"min_aud":5500,"max_aud":10000,\n' \
'        "dealers":[\n' \
'            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-australian-year-of-the-horse-gold-bullion-coin/3003807"},\n' \
'            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/bullion-coins/Australian-Lunar-Series-III-2026-Year-of-the-Horse-1oz-Gold-Bullion-Coin/", "wait":8000},\n' \
'            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Gold-Coin-2026-Year-of-the-Horse-Perth-Mint/ID/644"},\n' \
'        ],\n' \
'    },\n' \
'\n' \
'    # ══════════════════════════════════════════════════════════════════════════\n' \
'    # KOALA — Silver (Perth Mint, releasing 6 May 2026 — verify URLs before first scrape)\n' \
'    # ══════════════════════════════════════════════════════════════════════════\n' \
'\n' \
'    "Silver Koala 1oz": {\n' \
'        "metal":"silver","category":"coin","coin_type":"Koala",\n' \
'        "weight_oz":1.0,"min_aud":95,"max_aud":250,\n' \
'        "dealers":[\n' \
'            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/bullion-coins/australian-koala-2026-1oz-silver-bullion-coin/", "wait":8000},\n' \
'            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/perth-mint-2026-koala-silver-coin-1-oz/"},\n' \
'            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/2026-1oz-perth-mint-silver-koala-coin/"},\n' \
'        ],\n' \
'    },\n' \
'\n' \
'    # ══════════════════════════════════════════════════════════════════════════\n' \
'    # SILVER BARS — 100oz\n' \
'    # ══════════════════════════════════════════════════════════════════════════\n' \
'\n' \
'    "Silver Bar Generic 100oz": {\n' \
'        "metal":"silver","category":"bar","bar_brand":"Generic","bar_type":"cast",\n' \
'        "weight_oz":100.0,"min_aud":8500,"max_aud":16000,\n' \
'        "dealers":[\n' \
'            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/generic-silver-100oz/"},\n' \
'            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/100oz-Ainslie-Silver-Bullion/ID/95"},\n' \
'        ],\n' \
'    },\n' \
'\n' \
'}'

if OLD3 in c:
    c = c.replace(OLD3, NEW3)
    print("✅ 4 new CATALOGUE entries added (Silver Lunar, Gold Lunar, Silver Koala, Silver Bar 100oz)")
else:
    errors.append("❌ Silver Buyback closing anchor not found")

if errors:
    for e in errors:
        print(e)
    import sys; sys.exit(1)

with open("scraper_v3.py", "w", encoding="utf-8") as f:
    f.write(c)
print("✅ scraper_v3.py written")