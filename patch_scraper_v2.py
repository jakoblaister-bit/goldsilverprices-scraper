"""patch_scraper_v2.py — fix URLs for new products"""

with open("scraper_v2.py", "r", encoding="utf-8") as f:
    code = f.read()

changes = [

    # 1. Jaggards Maple Leaf — use their category page sorted by price
    (
        '{"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/1oz-gold-maple-leaf-coin/"},',
        '{"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/1oz-canadian-gold-maple-leaf-coin/"},',
    ),

    # 2. Jaggards Krugerrand — use their secondary Krugerrand page
    (
        '{"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/1oz-krugerrand-gold-coin/"},',
        '{"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/1oz-south-african-gold-krugerrand/"},',
    ),

    # 3. Jaggards Britannia — use their 2023 product (random year available)
    (
        '{"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/1oz-gold-britannia-coin/"},',
        '{"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/2023-1oz-great-britain-britannia-gold-coin-king-charles"},',
    ),

    # 4. Ainslie Britannia — fix URL
    (
        '{"dealer": "Ainslie Bullion", "url": "https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Britannia-Gold-Coin/ID/674"},',
        '{"dealer": "Ainslie Bullion", "url": "https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Gold-Britannia-Coin/ID/674"},',
    ),

    # 5. Gold Stackers Britannia — fix URL
    (
        '{"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/product/royal-mint-britannia-gold-coin-1oz/"},',
        '{"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/product/royal-mint-1oz-gold-britannia-coin/"},',
    ),

    # 6. Ainslie Kookaburra — fix URL
    (
        '{"dealer": "Ainslie Bullion", "url": "https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Silver-Coin-2026-Kookaburra-Perth-Mint/ID/678"},',
        '{"dealer": "Ainslie Bullion", "url": "https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Silver-Kookaburra-Coin-2026-Perth-Mint/ID/678"},',
    ),

    # 7. Gold Stackers Kookaburra — fix URL
    (
        '{"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/product/perth-mint-2026-kookaburra-silver-coin-1-oz/"},',
        '{"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/product/perth-mint-kookaburra-silver-coin-2026-1oz/"},',
    ),

    # 8. Jaggards Kookaburra — fix URL
    (
        '{"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/2026-1oz-perth-mint-silver-kookaburra-coin/"},',
        '{"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/2026-kookaburra-1oz-silver-coin/"},',
    ),

    # 9. Gold Stackers Silver Maple Leaf — fix URL
    (
        '{"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/product/rcm-silver-maple-leaf-coin-1oz/"},',
        '{"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/product/rcm-silver-maple-leaf-1oz-coin/"},',
    ),

    # 10. Jaggards Silver Maple Leaf — fix URL
    (
        '{"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/2026-1oz-silver-maple-leaf-coin/"},',
        '{"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/2026-maple-leaf-1oz-silver-coin/"},',
    ),

    # 11. Swan Silver Maple Leaf — fix URL
    (
        '{"dealer": "Swan Bullion",    "url": "https://swanbullion.com/2026-maple-leaf-1oz-silver-coin/"},',
        '{"dealer": "Swan Bullion",    "url": "https://swanbullion.com/2026-canadian-maple-leaf-1oz-silver-coin/"},',
    ),
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