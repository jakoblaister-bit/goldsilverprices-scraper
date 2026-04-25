"""patch.py — fix Gold Stackers 1oz bar URL"""

with open("scraper.py", "r", encoding="utf-8") as f:
    code = f.read()

old = '"url":  "https://www.goldstackers.com.au/product/perth-mint-cast-gold-bar-1-oz/",'
new = '"url":  "https://www.goldstackers.com.au/product/perth-mint-cast-gold-bar-1oz/",'

if old in code:
    code = code.replace(old, new)
    print("  ✓ Fixed")
else:
    print("  ✗ Not found")

with open("scraper.py", "w", encoding="utf-8") as f:
    f.write(code)