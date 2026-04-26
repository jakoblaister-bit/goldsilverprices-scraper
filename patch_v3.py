"""patch_v3.py — apply v4 improvements to scraper_v3.py"""

with open("scraper_v3.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Add validation rules
old_parse = 'def extract_price(text, min_val, max_val):'
new_validate = '''PRICE_RULES = {
    ("gold",   "coin", 1.0,  None): (6500, 9500),
    ("gold",   "coin", 0.5,  None): (3300, 5000),
    ("gold",   "coin", 0.25, None): (1650, 2600),
    ("gold",   "coin", 0.1,  None): (680,  1100),
    ("gold",   "coin", 0.05, None): (360,  600),
    ("gold",   "bar",  1.0,  None): (6500, 9500),
    ("gold",   "bar",  None, 1.0):  (210,  400),
    ("gold",   "bar",  None, 5.0):  (1000, 1800),
    ("gold",   "bar",  None, 10.0): (2000, 3500),
    ("gold",   "bar",  None, 20.0): (4000, 7000),
    ("gold",   "bar",  None, 50.0): (10000,17000),
    ("silver", "coin", 1.0,  None): (110,  200),
    ("silver", "coin", 2.0,  None): (220,  400),
    ("silver", "bar",  1.0,  None): (110,  200),
}

def validate_price(parsed, price):
    metal = parsed.get("metal")
    cat   = parsed.get("category")
    woz   = parsed.get("weight_oz")
    wg    = parsed.get("weight_g")
    for (m, c, wo, wgo), (mn, mx) in PRICE_RULES.items():
        if m != metal or c != cat:
            continue
        if wo is not None and woz is not None and abs(woz - wo) < 0.001:
            return mn <= price <= mx
        if wgo is not None and wg is not None and abs(wg - wgo) < 0.01:
            return mn <= price <= mx
    # Fallback
    if metal == "gold":   return 200 < price < 200000
    if metal == "silver": return 100 < price < 5000
    return True

def extract_price(text, min_val, max_val):'''

code = code.replace(old_parse, new_validate)

# 2. Add deduplication inside main()
old_save = '''if result:
                    saved = save_to_db(result)
                    status = "✓ db" if saved else "✗ db"
                    weight = (f"{result['weight_oz']}oz" if result.get("weight_oz")
                              else f"{result.get('weight_g')}g")
                    name = result.get("coin_type") or result.get("bar_brand") or "?"
                    print(f"  ✓ {name:20s} {weight:8s} ${result['buy_price']:>10,.2f}  [{tick}]")
                    total_saved += 1
                else:
                    total_failed += 1'''

new_save = '''if result:
                    # Validate price
                    ok = validate_price(result, result["buy_price"])
                    if not ok:
                        print(f"  ✗ INVALID PRICE ${result['buy_price']:,.2f} — skipped")
                        total_failed += 1
                        continue

                    # Dedup key
                    dedup = (
                        dealer["name"],
                        result.get("coin_type") or result.get("bar_brand"),
                        result.get("weight_oz"),
                        result.get("weight_g"),
                        result.get("metal"),
                    )
                    if dedup in saved_this_run:
                        total_failed += 1
                        continue
                    saved_this_run.add(dedup)

                    saved = save_to_db(result)
                    status = "✓ db" if saved else "✗ db"
                    weight = (f"{result['weight_oz']}oz" if result.get("weight_oz")
                              else f"{result.get('weight_g')}g")
                    name = result.get("coin_type") or result.get("bar_brand") or "?"
                    print(f"  ✓ {name:20s} {weight:8s} ${result['buy_price']:>10,.2f}  [{status}]")
                    total_saved += 1
                else:
                    total_failed += 1'''

code = code.replace(old_save, new_save)

# 3. Add saved_this_run set per dealer
code = code.replace(
    '            for link in unique_links:',
    '            saved_this_run = set()\n            for link in unique_links:'
)

# 4. Fix Jaggards price selector — target WooCommerce price directly
code = code.replace(
    '"name": "Jaggards",',
    '"name": "Jaggards", "price_sel": ".woocommerce-Price-amount bdi",'
)

# 5. Fix Swan price selector
code = code.replace(
    '"name": "Swan Bullion",',
    '"name": "Swan Bullion", "price_sel": ".woocommerce-Price-amount bdi",'
)

with open("scraper_v3.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Done — now run: python scraper_v3.py")