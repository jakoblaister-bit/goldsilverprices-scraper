"""patch_v5.py — fix Swan, KJC, Perth Mint URLs"""

with open("scraper_v5.py", "r", encoding="utf-8") as f:
    code = f.read()

changes = [
    # 1. Swan — fix category URLs
    (
        '{"url": "https://swanbullion.com/buy-gold/",\n             "link_sel": "a[href*=\'swanbullion.com\'][href$=\'/\']",\n             "wait": 5000},\n            {"url": "https://swanbullion.com/buy-silver/",\n             "link_sel": "a[href*=\'swanbullion.com\'][href$=\'/\']",\n             "wait": 5000},',
        '{"url": "https://swanbullion.com/gold-bullion/",\n             "link_sel": "a.woocommerce-loop-product__link",\n             "wait": 5000},\n            {"url": "https://swanbullion.com/silver-bullion/",\n             "link_sel": "a.woocommerce-loop-product__link",\n             "wait": 5000},',
    ),

    # 2. KJC — use their actual URL structure
    (
        '{"url": "https://www.kjc-gold-silver-bullion.com.au/Gold/Coins",',
        '{"url": "https://www.kjc-gold-silver-bullion.com.au/CT/gold-bullion/41/1",',
    ),
    (
        '"url": "https://www.kjc-gold-silver-bullion.com.au/Silver/Coins",',
        '"url": "https://www.kjc-gold-silver-bullion.com.au/CT/silver-bullion/42/1",',
    ),
    (
        '"url": "https://www.kjc-gold-silver-bullion.com.au/Gold/Bars",',
        '"url": "https://www.kjc-gold-silver-bullion.com.au/CT/gold-bars/43/1",',
    ),

    # 3. Perth Mint — fix selector
    (
        '"link_sel": "a.product-item-link",\n             "wait": 12000, "networkidle": True},\n            {"url": "https://www.perthmint.com/shop/bullion/cast-bars/",\n             "link_sel": "a.product-item-link",',
        '"link_sel": "a[href*=\'/shop/bullion/\'][href*=\'-coin\'], a[href*=\'/shop/bullion/\'][href*=\'-bar\']",\n             "wait": 12000, "networkidle": True},\n            {"url": "https://www.perthmint.com/shop/bullion/cast-bars/",\n             "link_sel": "a[href*=\'/shop/bullion/cast-bars/\']",',
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

with open("scraper_v5.py", "w", encoding="utf-8") as f:
    f.write(code)

print(f"\n  {applied} changes applied. Now run: python scraper_v5.py")