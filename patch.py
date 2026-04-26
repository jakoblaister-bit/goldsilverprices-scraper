with open("scraper.py", "r", encoding="utf-8") as f:
    code = f.read()

# Add missing Perth Mint products and fix cast bar URL
code = code.replace(
    '{"url": "https://www.perthmint.com/shop/bullion/cast-bars/kangaroo-1oz-cast-gold-bar/", "link_sel": "h1", "wait": 8000, "networkidle": True, "is_direct": True, "name": "1oz Perth Mint Kangaroo Cast Gold Bar"},',
    '{"url": "https://www.perthmint.com/shop/bullion/cast-bars/kangaroo-1oz-cast-gold-bar/", "link_sel": "h1", "wait": 12000, "networkidle": True, "is_direct": True, "name": "1oz Perth Mint Kangaroo Cast Gold Bar"},',
)
code = code.replace(
    '{"url": "https://www.perthmint.com/shop/bullion/cast-bars/kangaroo-cast-gold-bar-100g/", "link_sel": "h1", "wait": 8000, "networkidle": True, "is_direct": True, "name": "100g Perth Mint Kangaroo Cast Gold Bar"},',
    '{"url": "https://www.perthmint.com/shop/bullion/cast-bars/kangaroo-cast-gold-bar-100g/", "link_sel": "h1", "wait": 12000, "networkidle": True, "is_direct": True, "name": "100g Perth Mint Kangaroo Cast Gold Bar"},\n            {"url": "https://www.perthmint.com/shop/bullion/minted-bars/kangaroo-5g-minted-gold-bar/", "link_sel": "h1", "wait": 12000, "networkidle": True, "is_direct": True, "name": "5g Perth Mint Kangaroo Minted Gold Bar"},',
)

with open("scraper.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Done")