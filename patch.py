"""patch.py — fix last 2 URLs"""

with open("scraper.py", "r", encoding="utf-8") as f:
    code = f.read()

changes = [
    # Gold Stackers 1oz bar — use their actual Perth Mint cast bar URL
    (
        '"url":  "https://www.goldstackers.com.au/product/perth-mint-cast-gold-bar-1oz/",',
        '"url":  "https://www.goldstackers.com.au/product/perth-mint-cast-gold-bar-1-oz/",',
    ),
    # ABC Bullion 1g — use their general gold store page which shows prices
    (
        '"url":  "https://www.abcbullion.com.au/store/gold/gabcmint1g-abc-bullion-1g-gold-minted-bar",',
        '"url":  "https://www.abcbullion.com.au/store/gold/abc-bullion-gold",',
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