with open("scraper_v3.py", "r", encoding="utf-8") as f:
    c = f.read().replace("\r\n", "\n")

OLD = \
'        await page.wait_for_timeout(dealer_entry.get("wait", 4000))\n' \
'\n' \
'        text      = await page.inner_text("body")\n' \
'        available = detect_availability(text)'

NEW = \
'        await page.wait_for_timeout(dealer_entry.get("wait", 4000))\n' \
'\n' \
'        # URL drift: product removed → page redirects to home/category. Bail out early.\n' \
'        final_url = page.url\n' \
'        if not final_url.startswith(url[:40]):\n' \
'            print(f"  ! {dealer:25s} URL redirected → {final_url[:70]}")\n' \
'            return "error"\n' \
'\n' \
'        text      = await page.inner_text("body")\n' \
'        available = detect_availability(text)'

if OLD in c:
    c = c.replace(OLD, NEW)
    print("✅ URL drift check added to scrape_product")
else:
    print("❌ anchor not found")
    import sys; sys.exit(1)

with open("scraper_v3.py", "w", encoding="utf-8") as f:
    f.write(c)
print("✅ scraper_v3.py written")