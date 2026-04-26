with open('scraper_v3.py', 'r') as f:
    code = f.read()

# Fix 1 — add networkidle to KJC
code = code.replace(
    '{"name": "KJC Bullion",',
    '{"name": "KJC Bullion", "networkidle": True,'
)

# Fix 2 — Jaggards price floor
code = code.replace(
    '"price_range": (110, 15000),',
    '"price_range": (115, 15000),'
)

with open('scraper_v3.py', 'w') as f:
    f.write(code)

print('fixed')