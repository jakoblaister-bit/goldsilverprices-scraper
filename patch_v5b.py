"""patch_v5b.py — fix Swan, KJC, Perth Mint"""

with open("scraper_v5.py", "r", encoding="utf-8") as f:
    code = f.read()

# Print current Swan URLs to debug
import re
swan_section = re.search(r'"name": "Swan Bullion".*?"base_url".*?"https://swanbullion\.com"', code, re.DOTALL)
if swan_section:
    print("Current Swan config:")
    print(swan_section.group()[:300])
else:
    print("Swan section not found")

# Find and replace Swan URLs using regex
code = re.sub(
    r'("name": "Swan Bullion".*?"pages": \[.*?)"url": "https://swanbullion\.com/[^"]*"(.*?)"link_sel": "[^"]*"',
    r'\1"url": "https://swanbullion.com/gold-bullion/"\2"link_sel": "a.woocommerce-loop-product__link"',
    code, count=1, flags=re.DOTALL
)

code = re.sub(
    r'("url": "https://swanbullion\.com/gold-bullion/".*?"link_sel": "a\.woocommerce-loop-product__link".*?)"url": "https://swanbullion\.com/[^"]*"(.*?)"link_sel": "[^"]*"',
    r'\1"url": "https://swanbullion.com/silver-bullion/"\2"link_sel": "a.woocommerce-loop-product__link"',
    code, count=1, flags=re.DOTALL
)

# Fix KJC — try their sitemap approach
code = code.replace(
    '"url": "https://www.kjc-gold-silver-bullion.com.au/Gold/Coins",',
    '"url": "https://www.kjc-gold-silver-bullion.com.au/CT/australian-bullion-gold-coins/41/1",',
)
code = code.replace(
    '"url": "https://www.kjc-gold-silver-bullion.com.au/CT/gold-bullion/41/1",',
    '"url": "https://www.kjc-gold-silver-bullion.com.au/CT/australian-bullion-gold-coins/41/1",',
)
code = code.replace(
    '"url": "https://www.kjc-gold-silver-bullion.com.au/Silver/Coins",',
    '"url": "https://www.kjc-gold-silver-bullion.com.au/CT/australian-bullion-silver-coins/42/1",',
)
code = code.replace(
    '"url": "https://www.kjc-gold-silver-bullion.com.au/CT/silver-bullion/42/1",',
    '"url": "https://www.kjc-gold-silver-bullion.com.au/CT/australian-bullion-silver-coins/42/1",',
)
code = code.replace(
    '"url": "https://www.kjc-gold-silver-bullion.com.au/Gold/Bars",',
    '"url": "https://www.kjc-gold-silver-bullion.com.au/CT/perth-mint-gold-minted-bars/272/1",',
)
code = code.replace(
    '"url": "https://www.kjc-gold-silver-bullion.com.au/CT/gold-bars/43/1",',
    '"url": "https://www.kjc-gold-silver-bullion.com.au/CT/perth-mint-gold-minted-bars/272/1",',
)

# Fix Perth Mint — use simpler selector that works
code = code.replace(
    '"link_sel": "a[href*=\'/shop/bullion/\'][href*=\'-coin\'], a[href*=\'/shop/bullion/\'][href*=\'-bar\']",',
    '"link_sel": "a.product-item-link, a[href*=\'/shop/bullion/bullion-coins/\']",',
)

with open("scraper_v5.py", "w", encoding="utf-8") as f:
    f.write(code)

print("\nDone. Now run: python scraper_v5.py")