"""
scraper_v4.py — CSS selector based, per-dealer validation, deduplication
"""

import asyncio
import json
import re
import urllib.request
from datetime import datetime
from playwright.async_api import async_playwright
import os

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://cjxkhvkvhgnlnviykoad.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNqeGtodmt2aGdubG52aXlrb2FkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY1ODIyMDYsImV4cCI6MjA5MjE1ODIwNn0.eCg-JzEshidI-l7pVsumO_SsXbDOh_s--zvH1jc78g0")
DB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

# ── Validation rules per metal ────────────────────────────────────────────────
PRICE_RULES = {
    # (metal, category, weight_oz, weight_g): (min_aud, max_aud)
    ("gold",   "coin", 1.0,   None): (6500,  9500),
    ("gold",   "coin", 0.5,   None): (3300,  5000),
    ("gold",   "coin", 0.25,  None): (1650,  2600),
    ("gold",   "coin", 0.1,   None): (680,   1100),
    ("gold",   "coin", 0.05,  None): (360,   600),
    ("gold",   "bar",  1.0,   None): (6500,  9500),
    ("gold",   "bar",  0.5,   None): (3300,  5000),
    ("gold",   "bar",  None,  1.0):  (210,   400),
    ("gold",   "bar",  None,  5.0):  (1000,  1800),
    ("gold",   "bar",  None,  10.0): (2000,  3500),
    ("gold",   "bar",  None,  20.0): (4000,  7000),
    ("gold",   "bar",  None,  50.0): (10000, 17000),
    ("gold",   "bar",  None,  100.0):(20000, 34000),
    ("silver", "coin", 1.0,   None): (110,   200),
    ("silver", "coin", 2.0,   None): (220,   400),
    ("silver", "bar",  1.0,   None): (110,   200),
    ("silver", "bar",  None,  100.0):(1000,  2000),
}

COIN_TYPES = {
    "kangaroo": "Kangaroo", "nugget": "Kangaroo",
    "kookaburra": "Kookaburra",
    "koala": "Koala",
    "maple": "Maple Leaf",
    "krugerrand": "Krugerrand",
    "britannia": "Britannia",
    "philharmonic": "Philharmonic",
    "american eagle": "American Eagle",
    "buffalo": "Buffalo",
    "lunar": "Lunar",
    "emu": "Emu",
    "swan": "Swan",
    "panda": "Panda",
    "libertad": "Libertad",
}

WEIGHT_PATTERNS = [
    (r'1/20\s*oz', 0.05, None), (r'1/10\s*oz', 0.1, None),
    (r'1/4\s*oz',  0.25, None), (r'1/2\s*oz',  0.5, None),
    (r'\b2\s*oz',  2.0,  None), (r'\b5\s*oz',  5.0, None),
    (r'\b10\s*oz', 10.0, None), (r'\b1\s*oz',  1.0, None),
    (r'1\s*kg',    32.15,None),
    (r'(\d+(?:\.\d+)?)\s*g\b', None, 'g'),
]

def parse_name(name):
    name_lower = name.lower()

    # Metal
    if any(w in name_lower for w in ["gold", " au "]):
        metal = "gold"
    elif any(w in name_lower for w in ["silver", " ag "]):
        metal = "silver"
    elif "platinum" in name_lower:
        metal = "platinum"
    else:
        return None

    # Skip proof/collector
    skip = ["proof", "coloured", "colored", "gilded", "antique", "piedfort",
            "high relief", "specimen", "privy", "mintmark", "capsule only"]
    if any(s in name_lower for s in skip):
        return None

    # Category
    if any(w in name_lower for w in ["bar", "cast", "minted", "ingot", "tablet"]):
        category = "bar"
        bar_type = "minted" if "minted" in name_lower else "cast"
        bar_brand = None
        for brand, kw in [("Perth Mint","perth"),("PAMP","pamp"),
                          ("ABC Bullion","abc"),("Baird","baird"),
                          ("Heraeus","heraeus"),("Valcambi","valcambi")]:
            if kw in name_lower:
                bar_brand = brand
                break
        bar_brand = bar_brand or "Generic"
        coin_type = None
    else:
        category = "coin"
        bar_type = bar_brand = None
        coin_type = None
        for kw, ct in COIN_TYPES.items():
            if kw in name_lower:
                coin_type = ct
                break
        if not coin_type:
            return None

    # Weight
    weight_oz = weight_g = None
    for pattern, oz, gflag in WEIGHT_PATTERNS:
        m = re.search(pattern, name_lower)
        if m:
            if gflag:
                weight_g = float(m.group(1))
            else:
                weight_oz = oz
            break

    if weight_oz is None and weight_g is None:
        return None

    # Year
    year = None
    ym = re.search(r'\b(20\d{2})\b', name)
    if ym:
        year = int(ym.group(1))

    return {
        "metal": metal, "category": category,
        "coin_type": coin_type, "bar_brand": bar_brand, "bar_type": bar_type,
        "weight_oz": weight_oz, "weight_g": weight_g, "year": year,
    }

def validate_price(parsed, price):
    """Check if price is plausible for this product."""
    metal    = parsed["metal"]
    category = parsed["category"]
    woz      = parsed["weight_oz"]
    wg       = parsed["weight_g"]

    for (m, c, wo, wgo), (mn, mx) in PRICE_RULES.items():
        if m != metal or c != category:
            continue
        if wo is not None and woz is not None and abs(woz - wo) < 0.001:
            return mn <= price <= mx, mn, mx
        if wgo is not None and wg is not None and abs(wg - wgo) < 0.01:
            return mn <= price <= mx, mn, mx

    # Fallback — rough check
    if metal == "gold":
        return 100 < price < 200000, 100, 200000
    else:
        return 50 < price < 5000, 50, 5000

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
        print(f"      [DB ERROR] {e}")
        return False

# ── Per-dealer scrape config ──────────────────────────────────────────────────
DEALERS = [
    {
        "name": "Ainslie Bullion",
        "pages": [
            {
                "url": "https://ainsliebullion.com.au/Buy/Keyword/Gold-Coins/ID/13",
                "link_sel": "a[href*='/Buy/View/Product/']",
                "price_sel": ".price, .product-price, span[class*='price']",
                "wait": 4000,
            },
            {
                "url": "https://ainsliebullion.com.au/Buy/Keyword/Silver-Coins/ID/14",
                "link_sel": "a[href*='/Buy/View/Product/']",
                "price_sel": ".price, .product-price, span[class*='price']",
                "wait": 4000,
            },
            {
                "url": "https://ainsliebullion.com.au/Buy/Keyword/Gold-Bars/ID/15",
                "link_sel": "a[href*='/Buy/View/Product/']",
                "price_sel": ".price, .product-price, span[class*='price']",
                "wait": 4000,
            },
        ],
        "base_url": "https://ainsliebullion.com.au",
    },
    {
        "name": "Gold Stackers",
        "pages": [
            {
                "url": "https://www.goldstackers.com.au/buy/gold/gold-coins/",
                "link_sel": "a.woocommerce-loop-product__link",
                "price_sel": ".price .amount, .woocommerce-Price-amount",
                "wait": 4000,
            },
            {
                "url": "https://www.goldstackers.com.au/buy/silver/silver-coins/",
                "link_sel": "a.woocommerce-loop-product__link",
                "price_sel": ".price .amount, .woocommerce-Price-amount",
                "wait": 4000,
            },
            {
                "url": "https://www.goldstackers.com.au/buy/gold/gold-bars/",
                "link_sel": "a.woocommerce-loop-product__link",
                "price_sel": ".price .amount, .woocommerce-Price-amount",
                "wait": 4000,
            },
        ],
        "base_url": "https://www.goldstackers.com.au",
    },
    {
        "name": "ABC Bullion",
        "pages": [
            {
                "url": "https://www.abcbullion.com.au/store/Bullion-Coins/gold-coins",
                "link_sel": "a[href*='/store/'][href*='-gold-']",
                "price_sel": ".price, .product-price, [class*='price']",
                "wait": 6000,
                "networkidle": True,
            },
            {
                "url": "https://www.abcbullion.com.au/store/Bullion-Coins/silver-coins",
                "link_sel": "a[href*='/store/'][href*='-silver-']",
                "price_sel": ".price, .product-price, [class*='price']",
                "wait": 6000,
                "networkidle": True,
            },
            {
                "url": "https://www.abcbullion.com.au/store/gold/gold-bars",
                "link_sel": "a[href*='/store/gold/']",
                "price_sel": ".price, .product-price, [class*='price']",
                "wait": 6000,
                "networkidle": True,
            },
        ],
        "base_url": "https://www.abcbullion.com.au",
    },
    {
        "name": "Jaggards",
        "pages": [
            {
                "url": "https://www.jaggards.com.au/category/gold/gold-coins/1oz-gold-coins/",
                "link_sel": "a.woocommerce-loop-product__link",
                "price_sel": ".woocommerce-Price-amount",
                "wait": 3000,
            },
            {
                "url": "https://www.jaggards.com.au/category/gold/gold-coins/1-2oz-gold-coins/",
                "link_sel": "a.woocommerce-loop-product__link",
                "price_sel": ".woocommerce-Price-amount",
                "wait": 3000,
            },
            {
                "url": "https://www.jaggards.com.au/category/gold/gold-coins/1-4oz-gold-coins/",
                "link_sel": "a.woocommerce-loop-product__link",
                "price_sel": ".woocommerce-Price-amount",
                "wait": 3000,
            },
            {
                "url": "https://www.jaggards.com.au/category/gold/gold-coins/1-10oz-gold-coins/",
                "link_sel": "a.woocommerce-loop-product__link",
                "price_sel": ".woocommerce-Price-amount",
                "wait": 3000,
            },
            {
                "url": "https://www.jaggards.com.au/category/silver/silver-coins/1oz-silver-coins/",
                "link_sel": "a.woocommerce-loop-product__link",
                "price_sel": ".woocommerce-Price-amount",
                "wait": 3000,
            },
            {
                "url": "https://www.jaggards.com.au/category/gold/gold-bars/",
                "link_sel": "a.woocommerce-loop-product__link",
                "price_sel": ".woocommerce-Price-amount",
                "wait": 3000,
            },
        ],
        "base_url": "https://www.jaggards.com.au",
    },
    {
        "name": "Swan Bullion",
        "pages": [
            {
                "url": "https://swanbullion.com/buy-gold/?per_page=100",
                "link_sel": "a.woocommerce-loop-product__link",
                "price_sel": ".woocommerce-Price-amount bdi",
                "wait": 4000,
            },
            {
                "url": "https://swanbullion.com/buy-silver/?per_page=100",
                "link_sel": "a.woocommerce-loop-product__link",
                "price_sel": ".woocommerce-Price-amount bdi",
                "wait": 4000,
            },
        ],
        "base_url": "https://swanbullion.com",
    },
    {
        "name": "KJC Bullion",
        "pages": [
            {
                "url": "https://www.kjc-gold-silver-bullion.com.au/CT/gold-bullion-coins/41/1",
                "link_sel": "a[href*='/PD/']",
                "price_sel": ".price, .product-price, span[itemprop='price']",
                "wait": 5000,
                "networkidle": True,
            },
            {
                "url": "https://www.kjc-gold-silver-bullion.com.au/CT/silver-bullion-coins/42/1",
                "link_sel": "a[href*='/PD/']",
                "price_sel": ".price, .product-price, span[itemprop='price']",
                "wait": 5000,
                "networkidle": True,
            },
            {
                "url": "https://www.kjc-gold-silver-bullion.com.au/CT/gold-bullion-bars/43/1",
                "link_sel": "a[href*='/PD/']",
                "price_sel": ".price, .product-price, span[itemprop='price']",
                "wait": 5000,
                "networkidle": True,
            },
        ],
        "base_url": "https://www.kjc-gold-silver-bullion.com.au",
    },
    {
        "name": "Perth Mint",
        "pages": [
            {
                "url": "https://www.perthmint.com/shop/bullion/bullion-coins/",
                "link_sel": "a[href*='/shop/bullion/']",
                "price_sel": ".price-box .price, [data-price-amount], .product-price",
                "wait": 10000,
                "networkidle": True,
            },
            {
                "url": "https://www.perthmint.com/shop/bullion/cast-bars/",
                "link_sel": "a[href*='/shop/bullion/']",
                "price_sel": ".price-box .price, [data-price-amount], .product-price",
                "wait": 10000,
                "networkidle": True,
            },
            {
                "url": "https://www.perthmint.com/shop/bullion/minted-bars/",
                "link_sel": "a[href*='/shop/bullion/']",
                "price_sel": ".price-box .price, [data-price-amount], .product-price",
                "wait": 10000,
                "networkidle": True,
            },
        ],
        "base_url": "https://www.perthmint.com",
    },
]

async def get_links(page, page_config, base_url):
    """Get all product links from a category page."""
    try:
        await page.goto(page_config["url"], timeout=60000, wait_until="domcontentloaded")
        if page_config.get("networkidle"):
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except:
                pass
        await page.wait_for_timeout(page_config.get("wait", 3000))

        links = await page.eval_on_selector_all(
            page_config["link_sel"],
            "els => els.map(e => ({href: e.href, text: e.innerText.trim()}))"
        )

        seen = set()
        results = []
        for link in links:
            href = link.get("href", "")
            if not href or href in seen or base_url not in href:
                continue
            # Skip category/pagination pages
            if any(s in href for s in [
                "/category/", "/tag/", "/page/", "?per_page", "?orderby",
                "/buy/gold/gold-coins/", "/buy/silver/", "/buy/gold/gold-bars/",
                "/Keyword/", "/product-category/",
            ]):
                continue
            seen.add(href)
            results.append({"href": href, "text": link.get("text", "")})
        return results
    except Exception as e:
        print(f"      [LINK ERROR] {e}")
        return []

async def scrape_product(page, dealer_name, url, text, price_sel, wait=3000):
    """Visit product page, extract price using CSS selector first, fallback to regex."""
    try:
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(wait)

        # Get product title from h1
        title = ""
        try:
            title = await page.inner_text("h1")
        except:
            pass
        if not title:
            title = text

        parsed = parse_name(title)
        if not parsed:
            return None

        # Try CSS selector first
        price = None
        for sel in price_sel.split(","):
            sel = sel.strip()
            try:
                els = await page.query_selector_all(sel)
                for el in els:
                    txt = await el.inner_text()
                    # Extract number
                    nums = re.findall(r'[\d,]+\.?\d*', txt.replace(",", ""))
                    for n in nums:
                        try:
                            val = float(n.replace(",", ""))
                            ok, mn, mx = validate_price(parsed, val)
                            if ok:
                                price = val
                                break
                        except:
                            pass
                    if price:
                        break
            except:
                pass
            if price:
                break

        # Fallback — body text regex
        if not price:
            body = await page.inner_text("body")
            matches = re.findall(r'A?\$\s*([\d,]+\.?\d*)', body)
            for m in matches:
                try:
                    val = float(m.replace(",", ""))
                    ok, mn, mx = validate_price(parsed, val)
                    if ok:
                        price = val
                        break
                except:
                    pass

        if not price:
            return None

        return {**parsed, "dealer": dealer_name, "buy_price": price,
                "url": url, "status": "OK", "in_stock": True}

    except Exception as e:
        return None

async def main():
    print("=" * 65)
    print("  GoldSilverPrices — Scraper v4 (CSS selector + validation)")
    print("=" * 65)
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Test DB
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

    total_saved = total_skipped = total_invalid = 0

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
        )
        page = await context.new_page()

        for dealer in DEALERS:
            print(f"\n{'─'*65}")
            print(f"  {dealer['name']}")
            print(f"{'─'*65}")

            # Collect all product links
            all_links = []
            for page_config in dealer["pages"]:
                print(f"  Scanning: {page_config['url']}")
                links = await get_links(page, page_config, dealer["base_url"])
                print(f"  → {len(links)} products found")
                all_links.extend(links)

            # Deduplicate
            seen = set()
            unique = []
            for l in all_links:
                if l["href"] not in seen:
                    seen.add(l["href"])
                    unique.append(l)

            print(f"  Total unique: {len(unique)}\n")

            # Track what we've saved this run — prevent duplicates
            saved_this_run = set()

            for link in unique:
                # Use first page config's price_sel and wait
                cfg = dealer["pages"][0]
                result = await scrape_product(
                    page, dealer["name"],
                    link["href"], link["text"],
                    cfg["price_sel"],
                    cfg.get("wait", 3000),
                )

                if result:
                    # Dedup key — dealer + coin_type/bar_brand + weight + metal
                    dedup_key = (
                        dealer["name"],
                        result.get("coin_type") or result.get("bar_brand"),
                        result.get("weight_oz"),
                        result.get("weight_g"),
                        result.get("metal"),
                    )
                    if dedup_key in saved_this_run:
                        total_skipped += 1
                        continue

                    saved_this_run.add(dedup_key)
                    saved = save_to_db(result)
                    weight = (f"{result['weight_oz']}oz" if result.get("weight_oz")
                              else f"{result.get('weight_g')}g")
                    name = result.get("coin_type") or result.get("bar_brand") or "?"
                    tick = "✓ db" if saved else "✗ db"
                    print(f"  ✓ {name:20s} {weight:8s} ${result['buy_price']:>10,.2f}  [{tick}]")
                    total_saved += 1
                else:
                    total_invalid += 1

            print(f"\n  → {len(saved_this_run)} saved for {dealer['name']}")

        await browser.close()

    print(f"\n{'='*65}")
    print(f"  DONE — {total_saved} saved · {total_skipped} deduped · {total_invalid} invalid/skipped")
    print(f"{'='*65}")

if __name__ == "__main__":
    asyncio.run(main())