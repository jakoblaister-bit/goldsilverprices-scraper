c = open("scraper.py").read()
import re
urls = [m.group(1) for m in re.finditer(r'"url":\s*"(https://(?:www\.jaggards|www\.goldstackers)[^"]+)"', c)]
for u in urls:
    print(u)