with open("scraper.py", "r", encoding="utf-8") as f:
    code = f.read()

# Print current rules to see exact strings
import re
rules = re.findall(r'    \("gold".*?\n', code)
for r in rules:
    print(repr(r))