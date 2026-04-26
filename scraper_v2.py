import asyncio
import json
import re
import urllib.request
from datetime import datetime
from collections import Counter
from playwright.async_api import async_playwright

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL = "https://cjxkhvkvhgnlnviykoad.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNqeGtodmt2aGdubG52aXlrb2FkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY1ODIyMDYsImV4cCI6MjA5MjE1ODIwNn0.eCg-JzEshidI-l7pVsumO_SsXbDOh_s--zvH1jc78g0"
DB_HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=minimal",
}

results = []


def save_to_db(row):
    try:
        payload = json.dumps(row).encode("utf-8")
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/prices_v2",
            data=payload, headers=DB_HEADERS, method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 201)
    except Exception as e:
        print(f"    [DB ERROR] {e}")
        return False


def extract_price(text, min_val, max_val):
    all_matches = []
    all_matches += re.findall(r'A?\$\s*([\d]{1,3}(?:,[\d]{3})*(?:\.[\d]{2})?)', text)
    all_matches += re.findall(r'AUD\s*([\d]{3,6}(?:\.[\d]{2})?)', text)
    all_matches += re.findall(r'([\d]{3,5}\.[\d]{2})/oz', text)
    all_matches += re.findall(r'\b([\d]{1,2},[\d]{3}(?:\.[\d]{2})?)\b', text)

    prices = []
    for m in all_matches:
        try:
            val = float(m.replace(",", ""))
            if min_val <= val <= max_val:
                prices.append(val)
        except:
            pass

    if not prices:
        return None

    count     = Counter(prices)
    max_count = max(count.values())
    candidates = [p for p, c in count.items() if c == max_count]
    retail    = [p for p in candidates if p >= min_val * 1.005]
    chosen    = min(retail) if retail else min(candidates)
    return chosen


async def scrape(page, dealer, product):
    url     = product["url"]
    min_val = product.get("min_val", product["min_aud"])
    max_val = product.get("max_val", product["max_aud"])

    try:
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        if product.get("networkidle"):
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except:
                pass
        await page.wait_for_timeout(product.get("wait", 4000))

        text  = await page.inner_text("body")
        price = extract_price(text, min_val, max_val)

        if price:
            row = {
                "dealer":    dealer,
                "metal":     product["metal"],
                "category":  product["category"],
                "coin_type": product.get("coin_type"),
                "bar_brand": product.get("bar_brand"),
                "bar_type":  product.get("bar_type"),
                "weight_oz": product.get("weight_oz"),
                "weight_g":  product.get("weight_g"),
                "buy_price": price,
                "url":       url,
                "in_stock":  True,
                "status":    "OK",
            }
            results.append({**row, "price_fmt": f"${price:,.2f}"})
            saved = save_to_db(row)
            tick  = "✓ db" if saved else "✗ db"
            print(f"  ✓ {dealer:25s} ${price:>10,.2f}  [{tick}]")
        else:
            results.append({
                "dealer": dealer, "metal": product["metal"],
                "category": product["category"],
                "coin_type": product.get("coin_type"),
                "price_fmt": "NOT FOUND", "url": url,
            })
            print(f"  ✗ {dealer:25s} NOT FOUND")
            preview = " ".join(text.split())[:200]
            print(f"    Preview: {preview}")

    except Exception as e:
        print(f"  ✗ {dealer:25s} ERROR: {str(e)[:80]}")


# ── PRODUCT CATALOGUE ─────────────────────────────────────────────────────────
# Each "product" is a specific coin/bar at a specific dealer.
# metal: gold | silver
# category: coin | bar
# coin_type: Kangaroo | Maple Leaf | Krugerrand | Britannia | Kookaburra
# bar_brand: Perth Mint | ABC Bullion | PAMP
# bar_type: cast | minted
# weight_oz: 1, 0.5, 0.25, 0.1, 0.05 (for coins/bars in oz)
# weight_g:  1, 5, 10, 50, 100 (for gram bars)
# min_aud / max_aud: plausible price range

CATALOGUE = {

    # ══════════════════════════════════════════════════════════════════════════
    # GOLD COINS — Kangaroo 1oz
    # ══════════════════════════════════════════════════════════════════════════
    "Gold Kangaroo 1oz": {
        "metal": "gold", "category": "coin", "coin_type": "Kangaroo",
        "weight_oz": 1.0, "min_aud": 6700, "max_aud": 9000,
        "dealers": [
            {"dealer": "KJC Bullion",     "url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-australian-kangaroo-gold-bullion-coin/3003878"},
            {"dealer": "Perth Mint",      "url": "https://www.perthmint.com/shop/bullion/bullion-coins/australian-kangaroo-2026-1oz-gold-bullion-coin/", "wait": 8000},
            {"dealer": "ABC Bullion",     "url": "https://www.abcbullion.com.au/store/Bullion-Coins/gn011oz-perth-mint-kangaroo-gold-coin-9999", "networkidle": True, "min_val": 5500},
            {"dealer": "Ainslie Bullion", "url": "https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Gold-Coin-2026-Kangaroo-Perth-Mint/ID/673"},
            {"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/product/australian-kangaroo-2026-1-oz-gold-bullion-coin/"},
            {"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/2026-1oz-perth-mint-gold-kangaroo-coin/"},
            {"dealer": "Swan Bullion",    "url": "https://swanbullion.com/2026-australian-kangaroo-1oz-gold-coin/"},
            {"dealer": "Guardian Gold",   "url": "https://guardian-gold.com.au/product/1oz-gold-kang-coin-2026/", "wait": 8000},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # GOLD COINS — Maple Leaf 1oz
    # ══════════════════════════════════════════════════════════════════════════
    "Gold Maple Leaf 1oz": {
        "metal": "gold", "category": "coin", "coin_type": "Maple Leaf",
        "weight_oz": 1.0, "min_aud": 6700, "max_aud": 9000,
        "dealers": [
            {"dealer": "KJC Bullion",     "url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-canadian-maple-leaf-gold-bullion-coin/3003907"},
            {"dealer": "ABC Bullion",     "url": "https://www.abcbullion.com.au/store/Bullion-Coins/world-coins", "networkidle": True, "min_val": 5500},
            {"dealer": "Ainslie Bullion", "url": "https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Maple-Leaf-Gold-Coin/ID/37"},
            {"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/buy/gold/all-1oz/", "min_val": 6500},
            {"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/1oz-canadian-gold-maple-leaf-coin/"},
            {"dealer": "Guardian Gold",   "url": "https://guardian-gold.com.au/product/1oz-gold-maple-leaf-coin-2023/"},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # GOLD COINS — Krugerrand 1oz
    # ══════════════════════════════════════════════════════════════════════════
    "Gold Krugerrand 1oz": {
        "metal": "gold", "category": "coin", "coin_type": "Krugerrand",
        "weight_oz": 1.0, "min_aud": 6700, "max_aud": 9000,
        "dealers": [
            {"dealer": "KJC Bullion",     "url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-south-africa-krugerrand-gold-bullion-coin--mixed-dates/2207805"},
            {"dealer": "Ainslie Bullion", "url": "https://ainsliebullion.com.au/buy/view/product/name/krugerand-gold-coin-incl-gst-/id/51"},
            {"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/buy/gold/gold-coins/", "min_val": 6500},
            {"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/1oz-south-african-gold-krugerrand/"},
            {"dealer": "Swan Bullion",    "url": "https://swanbullion.com/product/south-african-krugerrand-1oz-gold-coin-random-year"},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # GOLD COINS — Britannia 1oz
    # ══════════════════════════════════════════════════════════════════════════
    "Gold Britannia 1oz": {
        "metal": "gold", "category": "coin", "coin_type": "Britannia",
        "weight_oz": 1.0, "min_aud": 6700, "max_aud": 9000,
        "dealers": [
            {"dealer": "KJC Bullion",     "url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2024-britannia-gold-bullion-coin/3003321"},
            {"dealer": "ABC Bullion",     "url": "https://www.abcbullion.com.au/store/Bullion-Coins/royal-mint", "networkidle": True, "min_val": 6700},
            {"dealer": "Ainslie Bullion", "url": "https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Gold-Britannia-Coin/ID/674"},
            {"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/product/royal-mint-1oz-gold-britannia-coin/"},
            {"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/2023-1oz-great-britain-britannia-gold-coin-king-charles"},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # SILVER COINS — Kangaroo 1oz
    # ══════════════════════════════════════════════════════════════════════════
    "Silver Kangaroo 1oz": {
        "metal": "silver", "category": "coin", "coin_type": "Kangaroo",
        "weight_oz": 1.0, "min_aud": 110, "max_aud": 250,
        "dealers": [
            {"dealer": "KJC Bullion",     "url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-australian-kangaroo-silver-bullion-coin/3003876"},
            {"dealer": "Perth Mint",      "url": "https://www.perthmint.com/shop/bullion/bullion-coins/australian-kangaroo-2026-1oz-silver-bullion-coin-in-pouch/", "wait": 8000},
            {"dealer": "ABC Bullion",     "url": "https://www.abcbullion.com.au/store/Bullion-Coins/silver-coins", "networkidle": True},
            {"dealer": "Ainslie Bullion", "url": "https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Silver-Coin-2026-Kangaroo-Perth-Mint/ID/677"},
            {"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/product/perth-mint-2026-kangaroo-silver-coin-1-oz/"},
            {"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/2026-1oz-perth-mint-silver-kangaroo-coin/"},
            {"dealer": "Swan Bullion",    "url": "https://swanbullion.com/2026-australian-kangaroo-1oz-silver-coin/"},
            {"dealer": "Guardian Gold",   "url": "https://guardian-gold.com.au/product/1oz-silver-kangaroo-coin-2026/"},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # SILVER COINS — Kookaburra 1oz
    # ══════════════════════════════════════════════════════════════════════════
    "Silver Kookaburra 1oz": {
        "metal": "silver", "category": "coin", "coin_type": "Kookaburra",
        "weight_oz": 1.0, "min_aud": 110, "max_aud": 250,
        "dealers": [
            {"dealer": "KJC Bullion",     "url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-australian-kookaburra-silver-bullion-coin/3003879"},
            {"dealer": "Perth Mint",      "url": "https://www.perthmint.com/shop/bullion/bullion-coins/australian-kookaburra-2026-1oz-silver-bullion-coin/", "wait": 8000},
            {"dealer": "Ainslie Bullion", "url": "https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Silver-Kookaburra-Coin-2026-Perth-Mint/ID/678"},
            {"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/product/perth-mint-kookaburra-silver-coin-2026-1oz/"},
            {"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/2026-kookaburra-1oz-silver-coin/"},
            {"dealer": "Swan Bullion",    "url": "https://swanbullion.com/2026-kookaburra-1oz-silver-coin/"},
            {"dealer": "Guardian Gold",   "url": "https://guardian-gold.com.au/product/1oz-silver-kookaburra-coin-2026/", "wait": 8000},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # SILVER COINS — Maple Leaf 1oz
    # ══════════════════════════════════════════════════════════════════════════
    "Silver Maple Leaf 1oz": {
        "metal": "silver", "category": "coin", "coin_type": "Maple Leaf",
        "weight_oz": 1.0, "min_aud": 110, "max_aud": 250,
        "dealers": [
            {"dealer": "KJC Bullion",     "url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-canadian-maple-leaf-silver-bullion-coin/3003908"},
            {"dealer": "ABC Bullion",     "url": "https://www.abcbullion.com.au/store/Bullion-Coins/silver-coins", "networkidle": True},
            {"dealer": "Ainslie Bullion", "url": "https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Silver-Maple-Leaf-2026/ID/679"},
            {"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/product/rcm-silver-maple-leaf-1oz-coin/"},
            {"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/2026-maple-leaf-1oz-silver-coin/"},
            {"dealer": "Swan Bullion",    "url": "https://swanbullion.com/2026-canadian-maple-leaf-1oz-silver-coin/"},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # GOLD BARS — Perth Mint 1oz Cast
    # ══════════════════════════════════════════════════════════════════════════
    "Gold Bar Perth Mint 1oz": {
        "metal": "gold", "category": "bar", "bar_brand": "Perth Mint",
        "bar_type": "cast", "weight_oz": 1.0, "min_aud": 6700, "max_aud": 9000,
        "dealers": [
            {"dealer": "KJC Bullion",     "url": "https://www.kjc-gold-silver-bullion.com.au/CT/perth-mint-gold-bars-1oz-gold/220241/1"},
            {"dealer": "Perth Mint",      "url": "https://www.perthmint.com/shop/bullion/cast-bars/perth-mint-1oz-gold-cast-bar/", "wait": 8000},
            {"dealer": "ABC Bullion",     "url": "https://www.abcbullion.com.au/store/gold/gabg011oz-abc-gold-cast-bar-9999", "networkidle": True, "min_val": 5500},
            {"dealer": "Ainslie Bullion", "url": "https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Perth-Mint-Gold-Cast-Bar/ID/32"},
            {"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/buy/gold/all-1oz/", "min_val": 6500},
            {"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/1oz-perth-mint-gold-minted-bar/"},
            {"dealer": "Swan Bullion",    "url": "https://swanbullion.com/perth-mint-1oz-gold-minted-bar/"},
            {"dealer": "Guardian Gold",   "url": "https://guardian-gold.com.au/product/1oz-perth-mint-gold-cast-bar/", "wait": 8000},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # GOLD BARS — Perth Mint 1g Minted
    # ══════════════════════════════════════════════════════════════════════════
    "Gold Bar Perth Mint 1g": {
        "metal": "gold", "category": "bar", "bar_brand": "Perth Mint",
        "bar_type": "minted", "weight_g": 1.0, "min_aud": 200, "max_aud": 600,
        "dealers": [
            {"dealer": "KJC Bullion",     "url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-g-perth-mint-gold-bullion-minted-bar/2417"},
            {"dealer": "Perth Mint",      "url": "https://www.perthmint.com/shop/bullion/minted-bars/kangaroo-1g-minted-gold-bar/", "wait": 8000},
            {"dealer": "Ainslie Bullion", "url": "https://ainsliebullion.com.au/Buy/View/Product/Name/1g-Minted-Gold-Bar-Perth-Mint/ID/25"},
            {"dealer": "Gold Stackers",   "url": "https://www.goldstackers.com.au/product/perth-mint-kangaroo-gold-bar-1g/"},
            {"dealer": "Jaggards",        "url": "https://www.jaggards.com.au/product/1g-perth-mint-gold-minted-bar/"},
            {"dealer": "Swan Bullion",    "url": "https://swanbullion.com/perth-mint-1g-gold-minted-bar/"},
            {"dealer": "Guardian Gold",   "url": "https://guardian-gold.com.au/product/1g-perth-mint-gold-minted-bar/"},
        ],
    },
}


async def main():
    print("=" * 65)
    print("  GoldSilverPrices.com.au — Scraper v2 (new architecture)")
    print(f"  {sum(len(p['dealers']) for p in CATALOGUE.values())} total scrapes")
    print("=" * 65)
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Test DB
    print("  Testing database connection...")
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/prices_v2?select=id&limit=1",
            headers=DB_HEADERS, method="GET",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        print("  ✓ Supabase connected\n")
    except Exception as e:
        print(f"  ✗ DB failed: {e}")
        return

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            extra_http_headers={
                "Accept-Language": "en-AU,en;q=0.9",
            }
        )
        page = await context.new_page()

        for product_name, product_def in CATALOGUE.items():
            print(f"\n{'─'*65}")
            weight = (
                f"{product_def['weight_oz']}oz" if product_def.get("weight_oz")
                else f"{product_def['weight_g']}g"
            )
            print(f"  {product_def['metal'].upper()} {product_def['category'].upper()} — "
                  f"{product_def.get('coin_type') or product_def.get('bar_brand')} {weight}")
            print(f"{'─'*65}")

            for dealer_entry in product_def["dealers"]:
                product = {**product_def, **dealer_entry}
                await scrape(page, dealer_entry["dealer"], product)

        await browser.close()

    # Summary
    print(f"\n{'='*65}")
    print("  RESULTS")
    print(f"{'='*65}")
    ok  = [r for r in results if r.get("price_fmt") != "NOT FOUND"]
    bad = [r for r in results if r.get("price_fmt") == "NOT FOUND"]
    total = sum(len(p["dealers"]) for p in CATALOGUE.values())
    print(f"\n  ✓ {len(ok)}/{total} prices captured")
    if bad:
        print(f"\n  ✗ Missed:")
        for r in bad:
            print(f"    {r['dealer']:25s} {r.get('coin_type') or r.get('bar_brand','')}")
    print(f"{'='*65}")


if __name__ == "__main__":
    asyncio.run(main())