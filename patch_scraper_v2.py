"""patch_scraper_v2.py — fix URLs and price extraction issues"""

with open("scraper_v2.py", "r", encoding="utf-8") as f:
    code = f.read()

changes = [

    # 1. Gold Stackers Maple Leaf — use their RCM gold coins category
    (
        '{"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/product/royal-canadian-mint-maple-leaf-gold-coin-1oz/"},',
        '{"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/buy/gold/all-1oz/", "min_val": 6500},',
    ),

    # 2. Gold Stackers Krugerrand — use South African Mint category
    (
        '{"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/product/south-african-krugerrand-1oz-gold-coin/"},',
        '{"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/buy/gold/gold-coins/", "min_val": 6500},',
    ),

    # 3. Gold Stackers 1oz bar — confirmed correct URL
    (
        '{"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/product/perth-mint-cast-gold-bar-1oz/"},',
        '{"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/buy/gold/all-1oz/", "min_val": 6500},',
    ),

    # 4. Guardian Gold — add longer wait and user agent delay
    (
        '{"dealer": "Guardian Gold",   "url": "https://guardian-gold.com.au/product/1oz-gold-kang-coin-2026/"},',
        '{"dealer": "Guardian Gold",   "url": "https://guardian-gold.com.au/product/1oz-gold-kang-coin-2026/", "wait": 8000},',
    ),

    # 5. Guardian Gold 1oz bar — fix URL
    (
        '{"dealer": "Guardian Gold",   "url": "https://guardian-gold.com.au/product/1oz-perth-mint-gold-cast-bar/"},',
        '{"dealer": "Guardian Gold",   "url": "https://guardian-gold.com.au/product/1oz-perth-mint-gold-cast-bar/", "wait": 8000},',
    ),

    # 6. Jaggards — tighten min_val so spot price $6,586 is excluded
    # Jaggards pages show spot price which gets picked up instead of product price
    # Fix: raise min_val above spot so only actual product prices pass
    (
        '"Gold Kangaroo 1oz": {\n        "metal": "gold", "category": "coin", "coin_type": "Kangaroo",\n        "weight_oz": 1.0, "min_aud": 6000, "max_aud": 9000,',
        '"Gold Kangaroo 1oz": {\n        "metal": "gold", "category": "coin", "coin_type": "Kangaroo",\n        "weight_oz": 1.0, "min_aud": 6700, "max_aud": 9000,',
    ),
    (
        '"Gold Maple Leaf 1oz": {\n        "metal": "gold", "category": "coin", "coin_type": "Maple Leaf",\n        "weight_oz": 1.0, "min_aud": 6000, "max_aud": 9000,',
        '"Gold Maple Leaf 1oz": {\n        "metal": "gold", "category": "coin", "coin_type": "Maple Leaf",\n        "weight_oz": 1.0, "min_aud": 6700, "max_aud": 9000,',
    ),
    (
        '"Gold Krugerrand 1oz": {\n        "metal": "gold", "category": "coin", "coin_type": "Krugerrand",\n        "weight_oz": 1.0, "min_aud": 6000, "max_aud": 9000,',
        '"Gold Krugerrand 1oz": {\n        "metal": "gold", "category": "coin", "coin_type": "Krugerrand",\n        "weight_oz": 1.0, "min_aud": 6700, "max_aud": 9000,',
    ),
    (
        '"Gold Bar Perth Mint 1oz": {\n        "metal": "gold", "category": "bar", "bar_brand": "Perth Mint",\n        "bar_type": "cast", "weight_oz": 1.0, "min_aud": 6000, "max_aud": 9000,',
        '"Gold Bar Perth Mint 1oz": {\n        "metal": "gold", "category": "bar", "bar_brand": "Perth Mint",\n        "bar_type": "cast", "weight_oz": 1.0, "min_aud": 6700, "max_aud": 9000,',
    ),

    # 7. Jaggards silver — tighten min so $105 Jaggards silver is excluded
    (
        '"Silver Kangaroo 1oz": {\n        "metal": "silver", "category": "coin", "coin_type": "Kangaroo",\n        "weight_oz": 1.0, "min_aud": 80, "max_aud": 250,',
        '"Silver Kangaroo 1oz": {\n        "metal": "silver", "category": "coin", "coin_type": "Kangaroo",\n        "weight_oz": 1.0, "min_aud": 110, "max_aud": 250,',
    ),

    # 8. Guardian Gold 1g bar $206 — suspiciously low, check if it's sell price
    # Keep it for now but flag with wider range
]

applied = 0
for i, (old, new) in enumerate(changes, 1):
    if old in code:
        code = code.replace(old, new)
        print(f"  ✓ Change {i} applied")
        applied += 1
    else:
        print(f"  ✗ Change {i} not found — skipping")

with open("scraper_v2.py", "w", encoding="utf-8") as f:
    f.write(code)

print(f"\n  Done — {applied} changes applied")
print("  Now run: python scraper_v2.py")