import re

with open("scraper.py", "r", encoding="utf-8") as f:
    c = f.read()

# Remove the 3 bad KJC URLs
for fragment in [
    '{"url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-british-britannia-gold-bullion-coin/3003905"',
    '{"url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-south-african-krugerrand-gold-bullion-coin/3003903"',
    '{"url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-austrian-philharmonic-gold-bullion-coin/3003906"',
]:
    start = c.find(fragment)
    if start == -1:
        print(f"❌ Not found: {fragment[:60]}")
        continue
    end = c.find("},", start) + 2
    c = c[:start] + c[end:]
    print(f"✅ Removed: {fragment[60:90]}...")

with open("scraper.py", "w", encoding="utf-8") as f:
    f.write(c)
print("✅ KJC bad URLs removed")