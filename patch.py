"""patch.py — fix KJC download issue + Perth Mint selector"""

with open("scraper.py", "r", encoding="utf-8") as f:
    code = f.read()

# First rename scraper_v5 to scraper if needed
import os
if not os.path.exists("scraper.py"):
    import shutil
    shutil.copy("scraper_v5.py", "scraper.py")
    print("Copied scraper_v5.py to scraper.py")

changes = [
    # 1. KJC — skip download links, add download handling
    (
        'async with async_playwright() as pw:\n        browser = await pw.chromium.launch(\n            headless=True,\n            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",\n                  "--disable-web-security"]\n        )',
        'async with async_playwright() as pw:\n        browser = await pw.chromium.launch(\n            headless=True,\n            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",\n                  "--disable-web-security", "--disable-downloads"]\n        )',
    ),
    # 2. KJC — add download abort to context
    (
        '        context = await browser.new_context(\n            user_agent=(\n                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "\n                "AppleWebKit/537.36 (KHTML, like Gecko) "\n                "Chrome/124.0.0.0 Safari/537.36"\n            ),\n            viewport={"width": 1280, "height": 900},\n            extra_http_headers={"Accept-Language": "en-AU,en;q=0.9"},\n        )',
        '        context = await browser.new_context(\n            user_agent=(\n                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "\n                "AppleWebKit/537.36 (KHTML, like Gecko) "\n                "Chrome/124.0.0.0 Safari/537.36"\n            ),\n            viewport={"width": 1280, "height": 900},\n            extra_http_headers={"Accept-Language": "en-AU,en;q=0.9"},\n            accept_downloads=False,\n        )',
    ),
    # 3. KJC — fix link selector to avoid PDF/download links
    (
        '"link_sel": "a[href*=\'/PD/\'], a[href*=\'kjc\'][href*=\'gold\']",\n             "wait": 6000, "networkidle": True},\n            {"url": "https://www.kjc-gold-silver-bullion.com.au/CT/australian-bullion-silver-coins/42/1",\n             "link_sel": "a[href*=\'/PD/\'], a[href*=\'kjc\'][href*=\'silver\']",',
        '"link_sel": "a[href*=\'/PD/\']",\n             "wait": 6000, "networkidle": True},\n            {"url": "https://www.kjc-gold-silver-bullion.com.au/CT/australian-bullion-silver-coins/42/1",\n             "link_sel": "a[href*=\'/PD/\']",',
    ),
    # 4. Perth Mint — use JS to find links after page loads
    (
        '"link_sel": "a.product-item-link, a[href*=\'/shop/bullion/bullion-coins/\']",\n             "wait": 12000, "networkidle": True},\n            {"url": "https://www.perthmint.com/shop/bullion/cast-bars/",\n             "link_sel": "a[href*=\'/shop/bullion/cast-bars/\']",',
        '"link_sel": "a[href*=\'/shop/bullion/\'][href*=\'-coin\'], a[href*=\'/shop/bullion/\'][href*=\'-bar\'], a[href*=\'/shop/bullion/\'][href*=\'-bullion\']",\n             "wait": 15000, "networkidle": True},\n            {"url": "https://www.perthmint.com/shop/bullion/cast-bars/",\n             "link_sel": "a[href*=\'/shop/bullion/cast-bars/\']",',
    ),
    # 5. Add skip for download URLs in get_links
    (
        '            if any(s in href for s in [\n                "/category/", "/tag/", "/page/", "product-category",\n                "/buy/gold/$", "/buy/silver/$",\n                "javascript:", "mailto:",\n            ]):',
        '            if any(s in href for s in [\n                "/category/", "/tag/", "/page/", "product-category",\n                "/buy/gold/$", "/buy/silver/$",\n                "javascript:", "mailto:",\n                ".pdf", ".zip", ".xlsx", ".doc",\n            ]):',
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

with open("scraper.py", "w", encoding="utf-8") as f:
    f.write(code)

print(f"\n  {applied} changes applied. Now run: python scraper.py")