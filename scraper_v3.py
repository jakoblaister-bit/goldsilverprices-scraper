import asyncio
import json
import re
import urllib.request
from datetime import datetime
from playwright.async_api import async_playwright

# ── Supabase ──────────────────────────────────────────────────────────────────
import os
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://cjxkhvkvhgnlnviykoad.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNqeGtodmt2aGdubG52aXlrb2FkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY1ODIyMDYsImV4cCI6MjA5MjE1ODIwNn0.eCg-JzEshidI-l7pVsumO_SsXbDOh_s--zvH1jc78g0")
DB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

# ── Product name parser ───────────────────────────────────────────────────────
COIN_TYPES = {
    "kangaroo": "Kangaroo", "nugget": "Kangaroo",
    "kookaburra": "Kookaburra",
    "koala": "Koala",
    "maple": "Maple Leaf", "maple leaf": "Maple Leaf",
    "krugerrand": "Krugerrand", "kruger": "Krugerrand",
    "britannia": "Britannia",
    "philharmonic": "Philharmonic", "philharmoniker": "Philharmonic",
    "american eagle": "American Eagle", "eagle": "American Eagle",
    "buffalo": "Buffalo",
    "lunar": "Lunar",
    "emu": "Emu",
    "swan": "Swan",
    "panda": "Panda",
}

WEIGHT_MAP = {
    "1/20": 0.05, "1/10": 0.1, "1/4": 0.25, "1/2": 0.5,
    "2oz": 2.0, "5oz": 5.0, "10oz": 10.0,
    "1oz": 1.0, "1 oz": 1.0,
    "1kg": 32.1507, "1 kg": 32.1507,
    "2 oz": 2.0, "5 oz": 5.0, "10 oz": 10.0,
}

GRAM_MAP = {
    "1g": 1.0, "1 g": 1.0, "1gram": 1.0,
    "2g": 2.0, "2.5g": 2.5,
    "5g": 5.0, "5 g": 5.0,
    "10g": 10.0, "10 g": 10.0,
    "20g": 20.0, "25g": 25.0,
    "50g": 50.0, "100g": 100.0,
    "250g": 250.0, "500g": 500.0,
    "1000g": 1000.0,
}

def parse_product(name, url=""):
    """Parse a product name into structured fields."""
    name_lower = name.lower()
    result = {
        "coin_type": None, "metal": None, "category": None,
        "weight_oz": None, "weight_g": None, "year": None,
        "bar_brand": None, "bar_type": None,
    }

    # Metal
    if any(w in name_lower for w in ["gold", "au "]):
        result["metal"] = "gold"
    elif any(w in name_lower for w in ["silver", "ag "]):
        result["metal"] = "silver"
    elif "platinum" in name_lower:
        result["metal"] = "platinum"
    else:
        return None  # skip unknown metal

    # Category — bar or coin
    if any(w in name_lower for w in ["bar", "cast", "minted", "tablet", "ingot"]):
        result["category"] = "bar"
        # Bar brand
        if "perth mint" in name_lower or "perth" in name_lower:
            result["bar_brand"] = "Perth Mint"
        elif "pamp" in name_lower:
            result["bar_brand"] = "PAMP"
        elif "abc" in name_lower:
            result["bar_brand"] = "ABC Bullion"
        elif "baird" in name_lower:
            result["bar_brand"] = "Baird"
        else:
            result["bar_brand"] = "Generic"
        # Bar type
        result["bar_type"] = "minted" if "minted" in name_lower else "cast"
    else:
        result["category"] = "coin"
        # Coin type
        for keyword, coin_type in COIN_TYPES.items():
            if keyword in name_lower:
                result["coin_type"] = coin_type
                break
        if not result["coin_type"]:
            return None  # skip unknown coin type

    # Year
    year_match = re.search(r'\b(20\d{2})\b', name)
    if year_match:
        result["year"] = int(year_match.group(1))

    # Weight — try oz fractions first
    for pattern, oz in WEIGHT_MAP.items():
        if pattern.lower() in name_lower:
            result["weight_oz"] = oz
            break

    # Weight — try grams if no oz found
    if result["weight_oz"] is None:
        for pattern, g in GRAM_MAP.items():
            if pattern.lower() in name_lower:
                result["weight_g"] = g
                break

    # Must have a weight
    if result["weight_oz"] is None and result["weight_g"] is None:
        return None

    # Skip proof/collector coins
    skip_words = ["proof", "coloured", "colored", "gilded", "antique",
                  "piedfort", "high relief", "specimen", "anniversary",
                  "privy", "mintmark", "capsule only", "display"]
    if any(w in name_lower for w in skip_words):
        return None

    return result


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


PRICE_RULES = {
    ("gold",   "coin", 1.0,  None): (6500, 9500),
    ("gold",   "coin", 0.5,  None): (3300, 5000),
    ("gold",   "coin", 0.25, None): (1650, 2600),
    ("gold",   "coin", 0.1,  None): (680,  1100),
    ("gold",   "coin", 0.05, None): (360,  600),
    ("gold",   "bar",  1.0,  None): (6500, 9500),
    ("gold",   "bar",  None, 1.0):  (210,  400),
    ("gold",   "bar",  None, 5.0):  (1000, 1800),
    ("gold",   "bar",  None, 10.0): (2000, 3500),
    ("gold",   "bar",  None, 20.0): (4000, 7000),
    ("gold",   "bar",  None, 50.0): (10000,17000),
    ("silver", "coin", 1.0,  None): (110,  200),
    ("silver", "coin", 2.0,  None): (220,  400),
    ("silver", "bar",  1.0,  None): (110,  200),
}

def validate_price(parsed, price):
    metal = parsed.get("metal")
    cat   = parsed.get("category")
    woz   = parsed.get("weight_oz")
    wg    = parsed.get("weight_g")
    for (m, c, wo, wgo), (mn, mx) in PRICE_RULES.items():
        if m != metal or c != cat:
            continue
        if wo is not None and woz is not None and abs(woz - wo) < 0.001:
            return mn <= price <= mx
        if wgo is not None and wg is not None and abs(wg - wgo) < 0.01:
            return mn <= price <= mx
    # Fallback
    if metal == "gold":   return 200 < price < 200000
    if metal == "silver": return 100 < price < 5000
    return True

def extract_price(text, min_val, max_val):
    matches = re.findall(r'A?\$\s*([\d]{1,3}(?:,[\d]{3})*(?:\.[\d]{2})?)', text)
    matches += re.findall(r'AUD\s*([\d]{3,6}(?:\.[\d]{2})?)', text)
    prices = []
    for m in matches:
        try:
            val = float(m.replace(",", ""))
            if min_val <= val <= max_val:
                prices.append(val)
        except:
            pass
    if not prices:
        return None
    from collections import Counter
    count = Counter(prices)
    max_count = max(count.values())
    candidates = [p for p, c in count.items() if c == max_count]
    retail = [p for p in candidates if p >= min_val * 1.005]
    return min(retail) if retail else min(candidates)


# ── Dealer catalogue definitions ──────────────────────────────────────────────
DEALERS = [
    {
        "name": "Perth Mint",
        "category_urls": [
            "https://www.perthmint.com/shop/bullion/bullion-coins/",
            "https://www.perthmint.com/shop/bullion/cast-bars/",
            "https://www.perthmint.com/shop/bullion/minted-bars/",
        ],
        "link_selector": "a.product-item-link, a[href*='/bullion/']",
        "base_url": "https://www.perthmint.com",
        "wait": 12000,
        "networkidle": True,
        "price_range": (110, 20000),
    },
    {
        "name": "KJC Bullion",
        "category_urls": [
            "https://www.kjc-gold-silver-bullion.com.au/CT/gold/41/1",
            "https://www.kjc-gold-silver-bullion.com.au/CT/silver/42/1",
            "https://www.kjc-gold-silver-bullion.com.au/CT/gold-bars/43/1",
        ],
        "link_selector": "a[href*='/PD/']",
        "base_url": "https://www.kjc-gold-silver-bullion.com.au",
        "wait": 5000,
        "price_range": (50, 20000),
    },
    {
        "name": "Jaggards", "price_sel": ".woocommerce-Price-amount bdi",
        "category_urls": [
            "https://www.jaggards.com.au/category/gold/gold-coins/1oz-gold-coins/",
            "https://www.jaggards.com.au/category/gold/gold-coins/1-2oz-gold-coins/",
            "https://www.jaggards.com.au/category/gold/gold-coins/1-4oz-gold-coins/",
            "https://www.jaggards.com.au/category/gold/gold-coins/1-10oz-gold-coins/",
            "https://www.jaggards.com.au/category/silver/silver-coins/1oz-silver-coins/",
            "https://www.jaggards.com.au/category/gold/gold-bars/",
        ],
        "link_selector": "a.woocommerce-loop-product__link, .product a",
        "base_url": "https://www.jaggards.com.au",
        "wait": 3000,
        "price_range": (50, 15000),
    },
    {
        "name": "Swan Bullion", "price_sel": ".woocommerce-Price-amount bdi",
        "category_urls": [
            "https://swanbullion.com/buy-gold/?per_page=100",
            "https://swanbullion.com/buy-silver/?per_page=100",
        ],
        "link_selector": "a[href*='swanbullion.com/'][href$='/']:not([href*='category']):not([href*='tag']):not([href*='page'])",
        "base_url": "https://swanbullion.com",
        "wait": 3000,
        "price_range": (50, 15000),
    },
    {
        "name": "Gold Stackers",
        "category_urls": [
            "https://www.goldstackers.com.au/buy/gold/gold-coins/",
            "https://www.goldstackers.com.au/buy/silver/silver-coins/",
            "https://www.goldstackers.com.au/buy/gold/gold-bars/",
        ],
        "link_selector": "a.woocommerce-loop-product__link, .product-item a",
        "base_url": "https://www.goldstackers.com.au",
        "wait": 4000,
        "price_range": (50, 15000),
    },
    {
        "name": "Ainslie Bullion",
        "category_urls": [
            "https://ainsliebullion.com.au/Buy/Keyword/Gold-Coins/ID/13",
            "https://ainsliebullion.com.au/Buy/Keyword/Silver-Coins/ID/14",
            "https://ainsliebullion.com.au/Buy/Keyword/Gold-Bars/ID/15",
        ],
        "link_selector": "a[href*='/Buy/View/Product/']",
        "base_url": "https://ainsliebullion.com.au",
        "wait": 4000,
        "price_range": (50, 15000),
    },
    {
        "name": "ABC Bullion",
        "category_urls": [
            "https://www.abcbullion.com.au/store/Bullion-Coins/gold-coins",
            "https://www.abcbullion.com.au/store/Bullion-Coins/silver-coins",
            "https://www.abcbullion.com.au/store/gold/gold-bars",
        ],
        "link_selector": "a[href*='/store/']",
        "base_url": "https://www.abcbullion.com.au",
        "wait": 5000,
        "networkidle": True,
        "price_range": (50, 15000),
    },
]


async def get_product_links(page, dealer, category_url):
    """Visit a category page and return all product links."""
    try:
        await page.goto(category_url, timeout=60000, wait_until="domcontentloaded")
        if dealer.get("networkidle"):
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except:
                pass
        await page.wait_for_timeout(dealer.get("wait", 3000))

        links = await page.eval_on_selector_all(
            dealer["link_selector"],
            "els => els.map(e => ({href: e.href, text: e.innerText.trim()}))"
        )

        # Filter and deduplicate
        seen = set()
        results = []
        base = dealer["base_url"]
        for link in links:
            href = link.get("href", "")
            text = link.get("text", "")
            if not href or href in seen:
                continue
            # Must be on the same domain
            if base not in href:
                continue
            # Skip category pages
            if any(skip in href for skip in ["/category/", "/CT/", "/buy/gold/gold-coins/",
                                              "/buy/silver/", "/buy/gold/gold-bars/",
                                              "/store/Bullion-Coins", "/store/gold/",
                                              "/Keyword/", "product-category"]):
                continue
            seen.add(href)
            results.append({"href": href, "text": text})

        return results

    except Exception as e:
        print(f"    [ERROR getting links] {e}")
        return []


async def scrape_product(page, dealer_name, product_url, product_text, price_range):
    """Visit a product page and extract price + product info."""
    min_val, max_val = price_range

    try:
        await page.goto(product_url, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Get page title for product parsing
        title = await page.title()
        h1 = ""
        try:
            h1 = await page.inner_text("h1")
        except:
            pass

        product_name = h1 or title or product_text
        parsed = parse_product(product_name, product_url)

        if not parsed:
            return None

        # Extract price
        text = await page.inner_text("body")
        price = extract_price(text, min_val, max_val)

        if not price:
            return None

        return {**parsed, "dealer": dealer_name, "buy_price": price,
                "url": product_url, "status": "OK", "in_stock": True}

    except Exception as e:
        return None


async def main():
    print("=" * 65)
    print("  GoldSilverPrices — Catalogue Scraper v3")
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

    total_saved = 0
    total_failed = 0

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

            # Collect all product links from all category pages
            all_links = []
            for cat_url in dealer["category_urls"]:
                print(f"  Scanning: {cat_url}")
                links = await get_product_links(page, dealer, cat_url)
                print(f"  Found {len(links)} products")
                all_links.extend(links)

            # Deduplicate across categories
            seen = set()
            unique_links = []
            for link in all_links:
                if link["href"] not in seen:
                    seen.add(link["href"])
                    unique_links.append(link)

            print(f"  Total unique products: {len(unique_links)}\n")

            # Scrape each product
            dealer_saved = 0
            saved_this_run = set()
            for link in unique_links:
                result = await scrape_product(
                    page, dealer["name"],
                    link["href"], link["text"],
                    dealer["price_range"]
                )

                if result:
                    saved = save_to_db(result)
                    status = "✓ db" if saved else "✗ db"
                    weight = (f"{result['weight_oz']}oz" if result.get("weight_oz")
                              else f"{result.get('weight_g')}g")
                    name = result.get("coin_type") or result.get("bar_brand") or "?"
                    print(f"  ✓ {name:20s} {weight:8s} ${result['buy_price']:>10,.2f}  [{status}]")
                    dealer_saved += 1
                    total_saved += 1
                else:
                    total_failed += 1

            print(f"\n  → {dealer_saved} products saved for {dealer['name']}")

        await browser.close()

    print(f"\n{'='*65}")
    print(f"  DONE — {total_saved} prices saved · {total_failed} skipped")
    print(f"{'='*65}")


if __name__ == "__main__":
    asyncio.run(main())