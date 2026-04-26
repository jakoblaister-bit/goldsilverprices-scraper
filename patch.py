with open("scraper.py", "r", encoding="utf-8") as f:
    code = f.read()

# Try different silver URLs for Ainslie
code = code.replace(
    '"url": "https://ainsliebullion.com.au/Buy/Keyword/Silver/ID/14",',
    '"url": "https://ainsliebullion.com.au/Buy/Keyword/Silver-Coins/ID/3",',
)

with open("scraper.py", "w", encoding="utf-8") as f:
    f.write(code)
print("Done")