import re

with open("scraper.py", "r", encoding="utf-8") as f:
    code = f.read()

# Find KJC pages list and add product names directly
# Since H1 is empty on KJC, we hardcode names with URLs
KJC_PAGES = [
    ("https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-australian-kangaroo-gold-bullion-coin/3003878", "1oz 2026 Australian Kangaroo Gold Bullion Coin"),
    ("https://www.kjc-gold-silver-bullion.com.au/PD/12-oz-2026-australian-kangaroo-gold-bullion-coin/3003879", "1/2oz 2026 Australian Kangaroo Gold Bullion Coin"),
    ("https://www.kjc-gold-silver-bullion.com.au/PD/14-oz-2026-australian-kangaroo-gold-bullion-coin/3003880", "1/4oz 2026 Australian Kangaroo Gold Bullion Coin"),
    ("https://www.kjc-gold-silver-bullion.com.au/PD/1-10-oz-2026-australian-kangaroo-gold-bullion-coin/3003881", "1/10oz 2026 Australian Kangaroo Gold Bullion Coin"),
    ("https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-australian-kangaroo-silver-bullion-coin/3003876", "1oz 2026 Australian Kangaroo Silver Bullion Coin"),
    ("https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-australian-kookaburra-silver-bullion-coin/3003877", "1oz 2026 Australian Kookaburra Silver Bullion Coin"),
    ("https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-canadian-maple-leaf-gold-bullion-coin/3003907", "1oz 2026 Canadian Maple Leaf Gold Bullion Coin"),
    ("https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-canadian-maple-leaf-silver-bullion-coin/3003908", "1oz 2026 Canadian Maple Leaf Silver Bullion Coin"),
    ("https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-british-britannia-gold-bullion-coin/3003905", "1oz 2026 British Britannia Gold Bullion Coin"),
    ("https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-south-african-krugerrand-gold-bullion-coin/3003903", "1oz 2026 South African Krugerrand Gold Bullion Coin"),
    ("https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-austrian-philharmonic-gold-bullion-coin/3003906", "1oz 2026 Austrian Philharmonic Gold Bullion Coin"),
    ("https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-australian-year-of-the-horse-gold-bullion-coin/3003807", "1oz 2026 Australian Lunar Horse Gold Bullion Coin"),
    ("https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-perth-mint-gold-bar/3003900", "1oz Perth Mint Gold Minted Bar"),
    ("https://www.kjc-gold-silver-bullion.com.au/PD/1g-perth-mint-gold-minted-bar/3003901", "1g Perth Mint Gold Minted Bar"),
]

# Build new pages list
pages_str = "[\n"
for url, name in KJC_PAGES:
    pages_str += f'            {{"url": "{url}", "link_sel": "h1", "wait": 5000, "is_direct": True, "name": "{name}"}},\n'
pages_str += "        ]"

# Replace KJC pages using regex
new_code = re.sub(
    r'("name": "KJC Bullion".*?"pages": )\[.*?\]',
    lambda m: m.group(1) + pages_str,
    code,
    flags=re.DOTALL
)

if new_code == code:
    print("✗ Regex didn't match — trying direct replacement")
else:
    print("✓ KJC pages replaced")
    code = new_code

# Fix scrape_product to use page_config "name" if title is empty
# Find the title extraction block
old_title = '''        # Get title
        title = ""
        try:
            title = await page.inner_text("h1")
            title = title.strip()
        except:
            pass'''

new_title = '''        # Get title — use hardcoded name if available (for JS-rendered sites)
        title = page_config.get("name", "") if hasattr(page_config, "get") else ""
        if not title:
            try:
                title = await page.inner_text("h1")
                title = title.strip()
            except:
                pass'''

# Fix scrape_product signature to accept page_config
old_sig = "async def scrape_product(page, dealer, url, text, price_sels, wait=3000, use_meta=False):"
new_sig = "async def scrape_product(page, dealer, url, text, price_sels, wait=3000, use_meta=False, page_config=None):"

code = code.replace(old_sig, new_sig)
print("✓ scrape_product signature updated" if old_sig in code or new_sig in code else "✗ signature not found")

code = code.replace(old_title, new_title)
print("✓ title extraction fixed" if old_title not in code else "✗ title not replaced")

# Pass page_config to scrape_product call
old_call = """                result, reason = await scrape_product(
                    page, dealer, link["href"], link["text"],
                    dealer["price_sels"],
                    cfg.get("wait", 3000),
                    dealer.get("use_meta_price", False),
                )"""

new_call = """                result, reason = await scrape_product(
                    page, dealer, link["href"], link["text"],
                    dealer["price_sels"],
                    cfg.get("wait", 3000),
                    dealer.get("use_meta_price", False),
                    page_config=cfg,
                )"""

if old_call in code:
    code = code.replace(old_call, new_call)
    print("✓ scrape_product call updated")
else:
    print("✗ call not found")

with open("scraper.py", "w", encoding="utf-8") as f:
    f.write(code)

print("\nDone. Run: python scraper.py --debug kjc --nosave")