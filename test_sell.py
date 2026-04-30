# patch.py
c = open("scraper.py", encoding="utf-8").read()

start = c.find("async def scrape_melbourne_gold_sell(page):")
end   = c.find("\nasync def scrape_imperial_sell", start)

NEW_MGC = '''async def scrape_melbourne_gold_sell(page):
    """Melbourne Gold Company — bullion rates from li elements"""
    results = []
    try:
        await page.goto("https://www.melbournegoldcompany.com.au/gold-buyers-melbourne.html",
                       wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)
        items = await page.query_selector_all("li")
        for item in items:
            txt = (await item.inner_text()).strip()
            if not any(x in txt for x in ["Gold Bar","Silver","oz 999","kg 999"]):
                continue
            if any(x in txt for x in ["Purity","Per Gram","Round Coin","We Pay"]):
                continue
            lines = [l.strip() for l in txt.split("\\n") if l.strip()]
            if len(lines) < 2:
                continue
            name      = lines[0]
            price_str = lines[1].replace("$","").replace(",","").strip()
            try:
                price = float(price_str)
            except:
                continue
            if price <= 0:
                continue
            metal = "silver" if "silver" in name.lower() else "gold"
            frac  = {"1/20oz":0.05,"1/10oz":0.1,"1/4oz":0.25,"1/2oz":0.5}
            weight_oz = None
            name_l = name.lower().replace(" ","")
            for k,v in frac.items():
                if k in name_l:
                    weight_oz = v
                    break
            if not weight_oz:
                wm = re.search(r"(\\d+(?:\\.\\d+)?)(oz|g|kg)", name.lower())
                if wm:
                    wval  = float(wm.group(1))
                    wunit = wm.group(2)
                    weight_oz = wval if "oz" in wunit else wval/31.1035 if wunit=="g" else wval*32.1507
            if not weight_oz:
                continue
            results.append({
                "dealer":"Melbourne Gold Company","metal":metal,
                "sell_price":price,"weight_oz":round(weight_oz,4),"category":"bar",
                "status":"OK","scraped_at":datetime.utcnow().isoformat(),
            })
            print(f"  ✓ Melbourne Gold buyback {metal} {weight_oz:.4f}oz @ A${price:.2f}")
    except Exception as e:
        print(f"  ✗ Melbourne Gold sell error: {e}")
    return results

'''

c = c[:start] + NEW_MGC + c[end:]
open("scraper.py", "w", encoding="utf-8").write(c)
print("✅ Melbourne Gold fixed")