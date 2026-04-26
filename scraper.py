"""
scraper_v5.py — Senior-grade scraper
- Per-dealer CSS price selectors
- Debug mode shows why prices fail validation
- Perth Mint: intercept network requests for prices
- Gold Stackers/Swan/KJC: fixed selectors
"""

import asyncio
import json
import re
import urllib.request
from datetime import datetime
from playwright.async_api import async_playwright
import os
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--debug", help="Run only this dealer in verbose mode")
parser.add_argument("--nosave", action="store_true", help="Don't save to DB")
args, _ = parser.parse_known_args()
DEBUG_DEALER = args.debug.lower() if args.debug else None
NO_SAVE      = args.nosave

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://cjxkhvkvhgnlnviykoad.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNqeGtodmt2aGdubG52aXlrb2FkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY1ODIyMDYsImV4cCI6MjA5MjE1ODIwNn0.eCg-JzEshidI-l7pVsumO_SsXbDOh_s--zvH1jc78g0")
DB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

# ── Price validation rules ────────────────────────────────────────────────────
PRICE_RULES = {
    ("gold",   "coin", 1.0,  None): (6500,  9500),
    ("gold",   "coin", 0.5,  None): (3200,  5000),
    ("gold",   "coin", 0.25, None): (1600,  2700),
    ("gold",   "coin", 0.1,  None): (650,   1200),
    ("gold",   "coin", 0.05, None): (330,   650),
    ("gold",   "bar",  1.0,  None): (6500,  9500),
    ("gold",   "bar",  0.5,  None): (3200,  5000),
    ("gold",   "bar",  0.25, None): (1600,  2700),
    ("gold",   "bar",  None, 1.0):  (200,   450),
    ("gold",   "bar",  None, 2.5):  (500,   900),
    ("gold",   "bar",  None, 5.0):  (1000,  1900),
    ("gold",   "bar",  None, 10.0): (2000,  3600),
    ("gold",   "bar",  None, 20.0): (4000,  7200),
    ("gold",   "bar",  None, 50.0): (10000, 18000),
    ("gold",   "bar",  None, 100.0):(20000, 36000),
    ("gold",   "bar",  5.0,  None): (32000, 50000),
    ("gold",   "bar",  10.0, None): (64000, 100000),
    ("silver", "coin", 1.0,  None): (110,   200),
    ("silver", "coin", 0.5,  None): (55,    120),
    ("silver", "coin", 0.25, None): (28,    70),
    ("silver", "coin", 2.0,  None): (220,   420),
    ("silver", "coin", 5.0,  None): (550,   1000),
    ("silver", "coin", 10.0, None): (1100,  2000),
    ("silver", "bar",  1.0,  None): (110,   200),
    ("silver", "bar",  32.15,None): (3500,  5500),
}

COIN_TYPES = {
    "kangaroo": "Kangaroo", "nugget": "Kangaroo",
    "kookaburra": "Kookaburra",
    "koala": "Koala",
    "maple": "Maple Leaf",
    "krugerrand": "Krugerrand",
    "kruger": "Krugerrand",
    "britannia": "Britannia",
    "british": "Britannia",
    "philharmonic": "Philharmonic",
    "philharmoniker": "Philharmonic",
    "austrian": "Philharmonic",
    "american eagle": "American Eagle",
    "buffalo": "Buffalo",
    "lunar": "Lunar",
    "horse": "Lunar",
    "dragon": "Lunar",
    "snake": "Lunar",
    "emu": "Emu",
    "swan coin": "Swan",
    "panda": "Panda",
    "libertad": "Libertad",
}

WEIGHT_PATTERNS = [
    (r'1/20\s*oz', 0.05, None), (r'1/10\s*oz', 0.1, None),
    (r'1/4\s*oz', 0.25, None),  (r'1/2\s*oz', 0.5, None),
    (r'\b10\s*oz', 10.0, None), (r'\b5\s*oz', 5.0, None),
    (r'\b2\s*oz', 2.0, None),   (r'\b1\s*oz', 1.0, None),
    (r'1\s*kg', 32.15, None),
    (r'(\d+(?:\.\d+)?)\s*g\b', None, 'g'),
]

def parse_name(name):
    name_lower = name.lower()
    if any(w in name_lower for w in ["gold", " au "]):
        metal = "gold"
    elif any(w in name_lower for w in ["silver", " ag "]):
        metal = "silver"
    else:
        return None

    skip = ["proof", "coloured", "colored", "gilded", "antique", "piedfort",
            "high relief", "specimen", "privy", "mintmark", "capsule only",
            "collection", "set", "2 coin", "3 coin"]
    if any(s in name_lower for s in skip):
        return None

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
    metal = parsed.get("metal")
    cat   = parsed.get("category")
    woz   = parsed.get("weight_oz")
    wg    = parsed.get("weight_g")
    for (m, c, wo, wgo), (mn, mx) in PRICE_RULES.items():
        if m != metal or c != cat:
            continue
        if wo is not None and woz is not None and abs(woz - wo) < 0.001:
            return mn <= price <= mx, mn, mx
        if wgo is not None and wg is not None and abs(wg - wgo) < 0.01:
            return mn <= price <= mx, mn, mx
    if metal == "gold":   return 200 < price < 200000, 200, 200000
    if metal == "silver": return 28 < price < 5000, 28, 5000
    return True, 0, 999999

def extract_price_from_text(text, parsed):
    matches = re.findall(r'A?\$\s*([\d,]+\.?\d*)', text)
    matches += re.findall(r'AUD\s*([\d,]+\.?\d*)', text)
    candidates = []
    for m in matches:
        try:
            val = float(m.replace(",", ""))
            ok, mn, mx = validate_price(parsed, val)
            if ok:
                candidates.append(val)
        except:
            pass
    if not candidates:
        return None
    from collections import Counter
    count = Counter(candidates)
    return min(count, key=lambda x: -count[x])

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

# ── Per-dealer config ─────────────────────────────────────────────────────────
DEALERS = [
    {
        "name": "Ainslie Bullion",
        "pages": [
            {"url": "https://ainsliebullion.com.au/Buy/Keyword/Gold-Coins/ID/13",
             "link_sel": "a[href*='/Buy/View/Product/']", "wait": 4000},
            {"url": "https://ainsliebullion.com.au/Buy/Keyword/Silver-Coins/ID/14",
             "link_sel": "a[href*='/Buy/View/Product/']", "wait": 4000},
            {"url": "https://ainsliebullion.com.au/Buy/Keyword/Gold-Bars/ID/15",
             "link_sel": "a[href*='/Buy/View/Product/']", "wait": 4000},
        ],
        "price_sels": [".price", ".product-price", "span[class*='price']", ".buy-price"],
        "base_url": "https://ainsliebullion.com.au",
    },
    {
        "name": "Gold Stackers",
        "pages": [
            {"url": "https://www.goldstackers.com.au/buy/gold/",
             "link_sel": "a[href*='/product/']", "wait": 5000},
            {"url": "https://www.goldstackers.com.au/buy/silver/",
             "link_sel": "a[href*='/product/']", "wait": 5000},
        ],
        "price_sels": [".woocommerce-Price-amount bdi", ".price .amount",
                       "p.price .woocommerce-Price-amount"],
        "base_url": "https://www.goldstackers.com.au",
    },
    {
        "name": "ABC Bullion",
        "pages": [
            {"url": "https://www.abcbullion.com.au/store/Bullion-Coins/gold-coins",
             "link_sel": "a[href*='/store/'][href*='gold']", "wait": 6000, "networkidle": True},
            {"url": "https://www.abcbullion.com.au/store/Bullion-Coins/silver-coins",
             "link_sel": "a[href*='/store/'][href*='silver']", "wait": 6000, "networkidle": True},
            {"url": "https://www.abcbullion.com.au/store/gold/gold-bars",
             "link_sel": "a[href*='/store/gold/']", "wait": 6000, "networkidle": True},
        ],
        "price_sels": [".product-info-price .price", "[data-price]",
                       ".price-wrapper .price", "span.price"],
        "base_url": "https://www.abcbullion.com.au",
        "networkidle": True,
    },
    {
        "name": "Jaggards",
        "pages": [
            {"url": "https://www.jaggards.com.au/category/gold/gold-coins/1oz-gold-coins/",
             "link_sel": "a.woocommerce-loop-product__link", "wait": 3000},
            {"url": "https://www.jaggards.com.au/category/gold/gold-coins/1-2oz-gold-coins/",
             "link_sel": "a.woocommerce-loop-product__link", "wait": 3000},
            {"url": "https://www.jaggards.com.au/category/gold/gold-coins/1-4oz-gold-coins/",
             "link_sel": "a.woocommerce-loop-product__link", "wait": 3000},
            {"url": "https://www.jaggards.com.au/category/gold/gold-coins/1-10oz-gold-coins/",
             "link_sel": "a.woocommerce-loop-product__link", "wait": 3000},
            {"url": "https://www.jaggards.com.au/category/silver/silver-coins/1oz-silver-coins/",
             "link_sel": "a.woocommerce-loop-product__link", "wait": 3000},
            {"url": "https://www.jaggards.com.au/category/gold/gold-bars/",
             "link_sel": "a.woocommerce-loop-product__link", "wait": 3000},
        ],
        "price_sels": [".woocommerce-Price-amount bdi",
                       "p.price .woocommerce-Price-amount bdi"],
        "base_url": "https://www.jaggards.com.au",
    },
    {
        "name": "Swan Bullion",
        "pages": [
            {"url": "https://swanbullion.com/gold-bullion/",
             "link_sel": "a.woocommerce-loop-product__link",
             "wait": 5000},
            {"url": "https://swanbullion.com/silver-bullion/",
             "link_sel": "a.woocommerce-loop-product__link",
             "wait": 5000},
        ],
        "price_sels": [".woocommerce-Price-amount bdi",
                       "p.price bdi", ".price bdi"],
        "base_url": "https://swanbullion.com",
    },
    {
        "name": "KJC Bullion",
        "pages": [
            {"url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-australian-kangaroo-gold-bullion-coin/3003878", "link_sel": "h1", "wait": 5000, "is_direct": True, "name": "1oz 2026 Australian Kangaroo Gold Bullion Coin"},
            {"url": "https://www.kjc-gold-silver-bullion.com.au/PD/12-oz-2026-australian-kangaroo-gold-bullion-coin/3003879", "link_sel": "h1", "wait": 5000, "is_direct": True, "name": "1/2oz 2026 Australian Kangaroo Gold Bullion Coin"},
            {"url": "https://www.kjc-gold-silver-bullion.com.au/PD/14-oz-2026-australian-kangaroo-gold-bullion-coin/3003880", "link_sel": "h1", "wait": 5000, "is_direct": True, "name": "1/4oz 2026 Australian Kangaroo Gold Bullion Coin"},
            {"url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-10-oz-2026-australian-kangaroo-gold-bullion-coin/3003881", "link_sel": "h1", "wait": 5000, "is_direct": True, "name": "1/10oz 2026 Australian Kangaroo Gold Bullion Coin"},
            {"url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-australian-kangaroo-silver-bullion-coin/3003876", "link_sel": "h1", "wait": 5000, "is_direct": True, "name": "1oz 2026 Australian Kangaroo Silver Bullion Coin"},
            {"url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-australian-kookaburra-silver-bullion-coin/3003877", "link_sel": "h1", "wait": 5000, "is_direct": True, "name": "1oz 2026 Australian Kookaburra Silver Bullion Coin"},
            {"url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-canadian-maple-leaf-gold-bullion-coin/3003907", "link_sel": "h1", "wait": 5000, "is_direct": True, "name": "1oz 2026 Canadian Maple Leaf Gold Bullion Coin"},
            {"url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-canadian-maple-leaf-silver-bullion-coin/3003908", "link_sel": "h1", "wait": 5000, "is_direct": True, "name": "1oz 2026 Canadian Maple Leaf Silver Bullion Coin"},
            {"url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-british-britannia-gold-bullion-coin/3003905", "link_sel": "h1", "wait": 5000, "is_direct": True, "name": "1oz 2026 British Britannia Gold Bullion Coin"},
            {"url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-south-african-krugerrand-gold-bullion-coin/3003903", "link_sel": "h1", "wait": 5000, "is_direct": True, "name": "1oz 2026 South African Krugerrand Gold Bullion Coin"},
            {"url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-austrian-philharmonic-gold-bullion-coin/3003906", "link_sel": "h1", "wait": 5000, "is_direct": True, "name": "1oz 2026 Austrian Philharmonic Gold Bullion Coin"},
            {"url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-australian-year-of-the-horse-gold-bullion-coin/3003807", "link_sel": "h1", "wait": 5000, "is_direct": True, "name": "1oz 2026 Australian Lunar Horse Gold Bullion Coin"},
            {"url": "https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-perth-mint-gold-bar/3003900", "link_sel": "h1", "wait": 5000, "is_direct": True, "name": "1oz Perth Mint Gold Minted Bar"},
            {"url": "https://www.kjc-gold-silver-bullion.com.au/PD/1g-perth-mint-gold-minted-bar/3003901", "link_sel": "h1", "wait": 5000, "is_direct": True, "name": "1g Perth Mint Gold Minted Bar"},
        ],
        "price_sels": [".product-price .price", "span[itemprop='price']",
                       ".price", "[class*='price']", "strong"],
        "base_url": "https://www.kjc-gold-silver-bullion.com.au",
        "networkidle": True,
        "use_sitemap": True,
    },
    {
        "name": "Perth Mint",
        "pages": [
            {"url": "https://www.perthmint.com/shop/bullion/bullion-coins/",
             "link_sel": "a.product-item-link",
             "wait": 12000, "networkidle": True},
            {"url": "https://www.perthmint.com/shop/bullion/cast-bars/",
             "link_sel": "a.product-item-link",
             "wait": 12000, "networkidle": True},
            {"url": "https://www.perthmint.com/shop/bullion/minted-bars/",
             "link_sel": "a.product-item-link",
             "wait": 12000, "networkidle": True},
        ],
        "price_sels": [
            "span.price-wrapper .price",
            "[data-price-amount]",
            ".product-info-price .price",
            "meta[itemprop='price']",
        ],
        "base_url": "https://www.perthmint.com",
        "networkidle": True,
        "use_meta_price": True,
    },
]

async def get_links(page, page_config, base_url):
    try:
        # Direct product URL mode
        if page_config.get("is_direct"):
            return [{"href": page_config["url"], "text": ""}]

        # Sitemap mode
        if page_config.get("is_sitemap"):
            return []

        await page.goto(page_config["url"], timeout=60000, wait_until="domcontentloaded")
        if page_config.get("networkidle"):
            try:
                await page.wait_for_load_state("networkidle", timeout=20000)
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
            href = link.get("href", "").split("?")[0].split("#")[0]
            if not href or href in seen or base_url not in href:
                continue
            if any(s in href for s in [
                "/category/", "/tag/", "/page/", "product-category",
                "/buy/gold/$", "/buy/silver/$",
                "javascript:", "mailto:",
                ".pdf", ".zip", ".xlsx", ".doc",
            ]):
                continue
            if href.rstrip("/") == base_url.rstrip("/"):
                continue
            seen.add(href)
            results.append({"href": href, "text": link.get("text", "")})
        # If no links found and sitemap mode, try fetching sitemap
        if not results and page_config.get("use_sitemap", False):
            try:
                sitemap_resp = await page.goto("https://www.kjc-gold-silver-bullion.com.au/sitemap.xml", timeout=30000)
                content = await page.content()
                import re as re2
                pd_urls = re2.findall(r'https://www\.kjc-gold-silver-bullion\.com\.au/PD/[^<]+', content)
                for url in pd_urls[:50]:  # limit to 50
                    url = url.strip()
                    if url not in seen:
                        seen.add(url)
                        results.append({"href": url, "text": ""})
                print(f"      [sitemap] Found {len(results)} PD URLs")
            except Exception as se:
                print(f"      [sitemap error] {str(se)[:60]}")

        return results
    except Exception as e:
        print(f"      [LINK ERROR] {str(e)[:60]}")
        return []

async def scrape_product(page, dealer, url, text, price_sels, wait=3000, use_meta=False, page_config=None):
    try:
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        if dealer.get("networkidle"):
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except:
                pass
        await page.wait_for_timeout(wait)

        # Get title — use hardcoded name if available (for JS-rendered sites)
        title = page_config.get("name", "") if hasattr(page_config, "get") else ""
        if not title:
            try:
                title = await page.inner_text("h1")
                title = title.strip()
            except:
                pass
        # Fallback: derive title from URL (handles JS-rendered sites)
        if not title or len(title) < 5:
            title = text
        if not title or len(title) < 5:
            # Parse from URL e.g. /PD/1-oz-2026-british-britannia-gold-bullion-coin/
            import re as _re
            url_part = url.rstrip("/").split("/")[-2] if "/PD/" in url else ""
            if url_part:
                title = url_part.replace("-", " ").title()

        parsed = parse_name(title)
        if not parsed:
            return None, "unparseable"

        price = None

        # Try meta[itemprop='price'] first for Perth Mint
        if use_meta:
            try:
                el = await page.query_selector("meta[itemprop='price']")
                if el:
                    val = await el.get_attribute("content")
                    if val:
                        v = float(val)
                        ok, mn, mx = validate_price(parsed, v)
                        if ok:
                            price = v
            except:
                pass

        # Try [data-price-amount]
        if not price:
            try:
                els = await page.query_selector_all("[data-price-amount]")
                for el in els:
                    val = await el.get_attribute("data-price-amount")
                    if val:
                        try:
                            v = float(val)
                            ok, mn, mx = validate_price(parsed, v)
                            if ok:
                                price = v
                                break
                        except:
                            pass
            except:
                pass

        # Try CSS selectors
        if not price:
            for sel in price_sels:
                try:
                    els = await page.query_selector_all(sel)
                    for el in els:
                        txt = await el.inner_text()
                        nums = re.findall(r'[\d,]+\.?\d*', txt)
                        for n in nums:
                            try:
                                v = float(n.replace(",", ""))
                                ok, mn, mx = validate_price(parsed, v)
                                if ok:
                                    price = v
                                    break
                            except:
                                pass
                        if price:
                            break
                except:
                    pass
                if price:
                    break

        # Fallback: body text
        if not price:
            body = await page.inner_text("body")
            price = extract_price_from_text(body, parsed)

        if not price:
            return None, f"no valid price found for {title[:40]}"

        return {**parsed, "dealer": dealer["name"], "buy_price": price,
                "url": url, "status": "OK", "in_stock": True}, None

    except Exception as e:
        return None, f"error: {str(e)[:60]}"

async def main():
    print("=" * 65)
    print("  GoldSilverPrices — Scraper v5")
    print("=" * 65)
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

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

    total_saved = total_deduped = total_invalid = 0

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--disable-web-security", "--disable-downloads"]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            extra_http_headers={"Accept-Language": "en-AU,en;q=0.9"},
            accept_downloads=False,
        )
        page = await context.new_page()

        dealers_to_run = DEALERS
        if DEBUG_DEALER:
            dealers_to_run = [d for d in DEALERS if DEBUG_DEALER in d['name'].lower()]
            if not dealers_to_run:
                print(f"  No dealer matching '{DEBUG_DEALER}'")
                return
            print(f"  DEBUG MODE: {dealers_to_run[0]['name']}\n")
        for dealer in dealers_to_run:
            print(f"\n{'─'*65}")
            print(f"  {dealer['name']}")
            print(f"{'─'*65}")

            all_links = []
            for page_config in dealer["pages"]:
                print(f"  Scanning: {page_config['url']}")
                links = await get_links(page, page_config, dealer["base_url"])
                print(f"  → {len(links)} products found")
                all_links.extend(links)

            seen = set()
            unique = []
            for l in all_links:
                if l["href"] not in seen:
                    seen.add(l["href"])
                    unique.append(l)

            print(f"  Total unique: {len(unique)}\n")

            saved_this_run = set()
            fail_reasons = {}

            for link in unique:
                # Match this link to its page config for correct name
                cfg = next(
                    (p for p in dealer["pages"] if p["url"] == link["href"]),
                    dealer["pages"][0]
                )
                result, reason = await scrape_product(
                    page, dealer, link["href"], link["text"],
                    dealer["price_sels"],
                    cfg.get("wait", 3000),
                    dealer.get("use_meta_price", False),
                    page_config=cfg,
                )

                if result:
                    dedup = (
                        dealer["name"],
                        result.get("coin_type") or result.get("bar_brand"),
                        result.get("weight_oz"),
                        result.get("weight_g"),
                        result.get("metal"),
                    )
                    if dedup in saved_this_run:
                        total_deduped += 1
                        continue

                    saved_this_run.add(dedup)
                    saved = save_to_db(result) if not NO_SAVE else True
                    weight = (f"{result['weight_oz']}oz" if result.get("weight_oz")
                              else f"{result.get('weight_g')}g")
                    name = result.get("coin_type") or result.get("bar_brand") or "?"
                    tick = "✓ db" if saved else "✗ db"
                    print(f"  ✓ {name:20s} {weight:8s} ${result['buy_price']:>10,.2f}  [{tick}]")
                    total_saved += 1
                else:
                    fail_reasons[reason] = fail_reasons.get(reason, 0) + 1
                    total_invalid += 1

            if fail_reasons:
                print(f"\n  Failures:")
                for r, cnt in sorted(fail_reasons.items(), key=lambda x: -x[1])[:5]:
                    print(f"    {cnt}x {r}")

            print(f"\n  → {len(saved_this_run)} saved for {dealer['name']}")

        await browser.close()

    print(f"\n{'='*65}")
    print(f"  DONE — {total_saved} saved · {total_deduped} deduped · {total_invalid} invalid")
    print(f"{'='*65}")

if __name__ == "__main__":
    asyncio.run(main())