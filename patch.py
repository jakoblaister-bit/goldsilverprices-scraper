# patch.py
with open("scraper.py", "r", encoding="utf-8") as f:
    c = f.read()

OLD = "datetime.utcnow().isoformat()"
NEW = "datetime.now(timezone.utc).isoformat()"

count = c.count(OLD)
if count == 0:
    print("❌ No instances found")
else:
    c = c.replace(OLD, NEW)
    with open("scraper.py", "w", encoding="utf-8") as f:
        f.write(c)
    print(f"✅ Replaced {count} instances of datetime.utcnow() with datetime.now(timezone.utc)")