# scraper_v2.py — category page architecture v2
import asyncio, os, re, json
from datetime import datetime, timezone
from playwright.async_api import async_playwright
from supabase import create_client

SUPA_URL = "https://cjxkhvkvhgnlnviykoad.supabase.co"
SUPA_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNqeGtodmt2aGdubG52aXlrb2FkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDQ2MDI0NTIsImV4cCI6MjA2MDE3ODQ1Mn0.xtCsyJtTBWvNaEWFiMNK0CDEM-bEbGKMNmTfiBpKPic"

WEIGHT_MAP = {
    "1/20oz":0.05,"1/10oz":0.1,"1/4oz":0.25,"1/2oz":0.5,
    "1oz":1.0,"2oz":2.0,"5oz":5.0,"10oz":10.0,"1kg":32.1507,
    "100g":3.2151,"50g":1.6076,"20g":0.6430,"10g":0.3215,"5g":0.1608,"2g":0.0643,"1g":0.0321,
}

COIN_MAP = {
    "kangaroo":"Kangaroo","nugget":"Kangaroo","kookaburra":"Kookaburra",
    "koala":"Koala","maple":"Maple Leaf","krugerrand":"Krugerrand",
    "britannia":"Britannia","philharmonic":"Philharmonic","philharmoniker":"Philharmonic",
    "american eagle":"American Eagle","buffalo":"Buffalo","lunar":"Lunar",
    "emu":"Emu","swan":"Swan","panda":"Panda","southern cross":"Southern Cross",
    "dragon":"Lunar","snake":"Lunar","horse":"Lunar",
}

def parse_weight(name):
    name_l = name.lower()
    for label, oz in sorted(WEIGHT_MAP.items(), key=lambda x: -len(x[0])):
        if label in name_l:
            g = round(oz * 31.1035, 4) if oz < 1 else None
            return oz, g, label
    # try Xg pattern
    m = re.search(r'(\d+)\s*g\b', name_l)
    if m:
        g = int(m.group(1))
        return round(g/31.1035,4), g, f"{g}g"
    return None, None, None

def parse_coin_type(name):
    name_l = name.lower()
    for kw, val in COIN_MAP.items():
        if kw in name_l:
            return val
    return None

def parse_price(price_str):
    try:
        return float(re.sub(r'[^\d.]', '', price_str))
    except:
        return None

def validate_price(price, spot, weight_oz):
    if not price or not spot or not weight_oz:
        return False, "missing data"
    base = spot * weight_oz
    if price < base * 1.005:
        return False, f"below spot floor A${base*1.005:.2f}"
    if price > base * 2.5:
        return False, f"above ceiling A${base*2.5:.2f}"
    return True, "ok"

# ── Base class ────────────────────────────────────────────────────────────────
class Dealer:
    name = ""
    def __init__(self, page, gold_spot, silver_spot):
        self.page        = page
        self.gold_spot   = gold_spot
        self.silver_spot = silver_spot
        self.results     = []
        self.saved       = 0
        self.rejected    = 0

    async def scrape(self): raise NotImplementedError

    def save(self, row):
        spot   = self.gold_spot if row["metal"] == "gold" else self.silver_spot
        weight = row.get("weight_oz") or (row.get("weight_g",0)/31.1035)
        ok, reason = validate_price(row["buy_price"], spot, weight)
        label  = row.get("coin_type") or row.get("bar_brand") or "?"
        if not ok:
            print(f"    ✗ REJECT {label} {row.get('weight_oz','?')}oz — {reason}")
            self.rejected += 1
            return
        row.update({
            "dealer":self.name, "status":"OK", "confidence":1,
            "scraped_at":datetime.now(timezone.utc).isoformat()
        })
        self.results.append(row)
        self.saved += 1
        print(f"    ✓ {label} {row.get('weight_oz','?')}oz — A${row['buy_price']:.2f}")

    def report(self):
        print(f"  → {self.saved} saved, {self.rejected} rejected")

# ── ABC Bullion ───────────────────────────────────────────────────────────────
class ABCBullion(Dealer):
    name = "ABC Bullion"
    CATS = [
        {"url":"https://www.abcbullion.com.au/store/gold/gold-coins",    "metal":"gold",   "category":"coin"},
        {"url":"https://www.abcbullion.com.au/store/silver/silver-coins","metal":"silver", "category":"coin"},
        {"url":"https://www.abcbullion.com.au/store/gold/gold-bars",     "metal":"gold",   "category":"bar"},
        {"url":"https://www.abcbullion.com.au/store/silver/silver-bars", "metal":"silver", "category":"bar"},
    ]

    async def scrape(self):
        for cat in self.CATS:
            await self._scrape_cat(cat)

    async def _scrape_cat(self, cat):
        print(f"\n  {cat['url']}")
        try:
            await self.page.goto(cat["url"], wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_timeout(3000)

            # Scroll to load all lazy products
            prev = 0
            for _ in range(20):
                await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await self.page.wait_for_timeout(1500)
                count = len(await self.page.query_selector_all(".module-item"))
                if count == prev:
                    break
                prev = count
            print(f"    Found {prev} products")

            items = await self.page.query_selector_all(".module-item")
            for item in items:
                await self._parse_item(item, cat)
        except Exception as e:
            print(f"    ✗ Failed: {e}")

    async def _parse_item(self, item, cat):
        try:
            # Name
            name_el = await item.query_selector("h2.module-title a")
            if not name_el: return
            name = (await name_el.inner_text()).strip()

            # Price from embedded JSON in <script>
            script_el = await item.query_selector("script")
            if not script_el:
                # Fallback to visible price
                price_el = await item.query_selector(".price")
                if not price_el: return
                price = parse_price(await price_el.inner_text())
            else:
                script = await script_el.inner_text()
                m = re.search(r'JSON\.parse\(\'(.+?)\'\)', script)
                if not m: return
                data = json.loads(m.group(1).replace("\\/","/"))
                # Tier 1 = single unit price
                price = parse_price(data["1"]["price"])

            if not price: return

            weight_oz, weight_g, w_label = parse_weight(name)
            if not weight_oz: 
                print(f"    ? No weight: {name}")
                return

            row = {
                "metal":    cat["metal"],
                "category": cat["category"],
                "buy_price": price,
                "weight_oz": weight_oz,
                "weight_g":  weight_g,
            }

            if cat["category"] == "coin":
                coin_type = parse_coin_type(name)
                if not coin_type:
                    print(f"    ? Unknown coin: {name}")
                    return
                row["coin_type"] = coin_type
            else:
                row["bar_brand"] = "ABC Bullion"
                row["bar_type"]  = "minted" if "minted" in name.lower() else "cast"

            self.save(row)
        except Exception as e:
            print(f"    ✗ Parse error: {e}")

# ── Spot fetch ────────────────────────────────────────────────────────────────
async def fetch_spot():
    import aiohttp
    async with aiohttp.ClientSession() as s:
        g  = await (await s.get("https://api.gold-api.com/price/XAU/AUD")).json()
        sv = await (await s.get("https://api.gold-api.com/price/XAG/AUD")).json()
    gold   = g["price"]  if g.get("price",0)  > 5000 else None
    silver = sv["price"] if sv.get("price",0) > 80   else None
    print(f"Spot — Gold: A${gold} Silver: A${silver}")
    return gold, silver

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    gold_spot, silver_spot = await fetch_spot()
    if not gold_spot or not silver_spot:
        print("❌ Spot fetch failed — aborting"); return

    supabase    = create_client(SUPA_URL, SUPA_KEY)
    all_results = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page    = await browser.new_page()
        await page.set_extra_http_headers({"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

        dealers = [
            ABCBullion(page, gold_spot, silver_spot),
        ]

        for dealer in dealers:
            print(f"\n{'='*55}\n  {dealer.name}\n{'='*55}")
            try:
                await dealer.scrape()
                dealer.report()
                all_results.extend(dealer.results)
            except Exception as e:
                print(f"❌ {dealer.name} crashed: {e}")

        await browser.close()

    if all_results:
        print(f"\nWriting {len(all_results)} rows...")
        supabase.table("prices_v2").upsert(all_results, on_conflict="dealer,metal,category,coin_type,bar_brand,bar_type,weight_oz").execute()
        print("✅ Done")
    else:
        print("⚠️  No results")

    print(f"\nTotal: {len(all_results)} saved")

if __name__ == "__main__":
    asyncio.run(main())