"""patch.py — fix Perth Mint silver + Gold Stackers 1oz gold URLs"""

with open("scraper.py", "r", encoding="utf-8") as f:
    code = f.read()

changes = [
    # Perth Mint silver — correct URL
    (
        '"url":  "https://www.perthmint.com/shop/bullion/bullion-coins/kangaroo-2026-1oz-silver-bullion-coin/",',
        '"url":  "https://www.perthmint.com/shop/bullion/bullion-coins/australian-kangaroo-2026-1oz-silver-bullion-coin-in-pouch/",',
    ),
    # Gold Stackers 1oz gold — correct URL
    (
        '"url":  "https://www.goldstackers.com.au/product/perth-mint-australian-kangaroo-2026-1oz-gold-bullion-coin-2/",',
        '"url":  "https://www.goldstackers.com.au/product/australian-kangaroo-2026-1-oz-gold-bullion-coin/",',
    ),
]

for i, (old, new) in enumerate(changes, 1):
    if old in code:
        code = code.replace(old, new)
        print(f"  ✓ Change {i} applied")
    else:
        print(f"  ✗ Change {i} not found")

with open("scraper.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Done.")