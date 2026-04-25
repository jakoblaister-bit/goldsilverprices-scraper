"""patch_scraper_v2.py — fix Jaggards URLs + add Britannia and Silver Kookaburra"""

with open("scraper_v2.py", "r", encoding="utf-8") as f:
    code = f.read()

changes = [

    # 1. Jaggards Maple Leaf — direct product URL
    (
        '{"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/category/canadian-mint/gold-maple-coins/"},',
        '{"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/1oz-gold-maple-leaf-coin/"},',
    ),

    # 2. Jaggards Krugerrand — direct product URL
    (
        '{"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/category/gold/world-gold-coins/"},',
        '{"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/1oz-krugerrand-gold-coin/"},',
    ),

    # 3. Add Gold Britannia after Krugerrand block
    (
        '    # ══════════════════════════════════════════════════════════════════════════\n    # SILVER COINS — Kangaroo 1oz',
        '''    # ══════════════════════════════════════════════════════════════════════════
    # GOLD COINS — Britannia 1oz
    # ══════════════════════════════════════════════════════════════════════════
    "Gold Britannia 1oz": {
        "metal": "gold", "category": "coin", "coin_type": "Britannia",
        "weight_oz": 1.0, "min_aud": 6700, "max_aud": 9000,
        "dealers": [
            {"dealer": "KJC Bullion",     "url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2024-britannia-gold-bullion-coin/3003321"},
            {"dealer": "ABC Bullion",     "url": "https://www.abcbullion.com.au/store/Bullion-Coins/royal-mint", "networkidle": True, "min_val": 6700},
            {"dealer": "Ainslie Bullion", "url": "https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Britannia-Gold-Coin/ID/674"},
            {"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/product/royal-mint-britannia-gold-coin-1oz/"},
            {"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/1oz-gold-britannia-coin/"},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # SILVER COINS — Kangaroo 1oz''',
    ),

    # 4. Add Silver Kookaburra after Silver Kangaroo block
    (
        '    # ══════════════════════════════════════════════════════════════════════════\n    # GOLD BARS — Perth Mint 1oz Cast',
        '''    # ══════════════════════════════════════════════════════════════════════════
    # SILVER COINS — Kookaburra 1oz
    # ══════════════════════════════════════════════════════════════════════════
    "Silver Kookaburra 1oz": {
        "metal": "silver", "category": "coin", "coin_type": "Kookaburra",
        "weight_oz": 1.0, "min_aud": 110, "max_aud": 250,
        "dealers": [
            {"dealer": "KJC Bullion",     "url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-australian-kookaburra-silver-bullion-coin/3003879"},
            {"dealer": "Perth Mint",      "url": "https://www.perthmint.com/shop/bullion/bullion-coins/australian-kookaburra-2026-1oz-silver-bullion-coin/", "wait": 8000},
            {"dealer": "Ainslie Bullion", "url": "https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Silver-Coin-2026-Kookaburra-Perth-Mint/ID/678"},
            {"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/product/perth-mint-2026-kookaburra-silver-coin-1-oz/"},
            {"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/2026-1oz-perth-mint-silver-kookaburra-coin/"},
            {"dealer": "Swan Bullion",    "url": "https://swanbullion.com/2026-kookaburra-1oz-silver-coin/"},
            {"dealer": "Guardian Gold",   "url": "https://guardian-gold.com.au/product/1oz-silver-kookaburra-coin-2026/", "wait": 8000},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # SILVER COINS — Maple Leaf 1oz
    # ══════════════════════════════════════════════════════════════════════════
    "Silver Maple Leaf 1oz": {
        "metal": "silver", "category": "coin", "coin_type": "Maple Leaf",
        "weight_oz": 1.0, "min_aud": 110, "max_aud": 250,
        "dealers": [
            {"dealer": "KJC Bullion",     "url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-canadian-maple-leaf-silver-bullion-coin/3003908"},
            {"dealer": "ABC Bullion",     "url": "https://www.abcbullion.com.au/store/Bullion-Coins/silver-coins", "networkidle": True},
            {"dealer": "Ainslie Bullion", "url": "https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Silver-Maple-Leaf-2026/ID/679"},
            {"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/product/rcm-silver-maple-leaf-coin-1oz/"},
            {"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/2026-1oz-silver-maple-leaf-coin/"},
            {"dealer": "Swan Bullion",    "url": "https://swanbullion.com/2026-maple-leaf-1oz-silver-coin/"},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # GOLD BARS — Perth Mint 1oz Cast''',
    ),
]

applied = 0
for i, (old, new) in enumerate(changes, 1):
    if old in code:
        code = code.replace(old, new)
        print(f"  ✓ Change {i} applied")
        applied += 1
    else:
        print(f"  ✗ Change {i} not found")

with open("scraper_v2.py", "w", encoding="utf-8") as f:
    f.write(code)

print(f"\n  Done — {applied} changes applied")
print("  Now run: python scraper_v2.py")