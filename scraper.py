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
import urllib.parse
from datetime import datetime, timezone
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
    ("gold",   "bar",  None, 5.0):  (900,   2000),
    ("gold",   "bar",  None, 10.0): (2000,  3600),
    ("gold",   "bar",  None, 20.0): (3500,  8000),
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

def delete_existing(row):
    """Delete existing price for same dealer+product+weight before inserting."""
    try:
        metal    = row.get("metal", "")
        category = row.get("category", "")
        dealer   = row.get("dealer", "")
        coin     = row.get("coin_type")
        brand    = row.get("bar_brand")
        bar_type = row.get("bar_type")
        woz      = row.get("weight_oz")
        wg       = row.get("weight_g")

        # Build filter query
        filters = [
            f"dealer=eq.{urllib.parse.quote(dealer)}",
            f"metal=eq.{metal}",
            f"category=eq.{category}",
        ]
        if coin:    filters.append(f"coin_type=eq.{urllib.parse.quote(coin)}")
        else:       filters.append("coin_type=is.null")
        if brand:   filters.append(f"bar_brand=eq.{urllib.parse.quote(brand)}")
        else:       filters.append("bar_brand=is.null")
        if bar_type: filters.append(f"bar_type=eq.{bar_type}")
        if woz is not None: filters.append(f"weight_oz=eq.{woz}")
        else:               filters.append("weight_oz=is.null")
        if wg is not None:  filters.append(f"weight_g=eq.{wg}")
        else:               filters.append("weight_g=is.null")

        url = f"{SUPABASE_URL}/rest/v1/prices_v2?{'&'.join(filters)}"
        req = urllib.request.Request(url, headers=DB_HEADERS, method="DELETE")
        with urllib.request.urlopen(req, timeout=10) as resp:
            pass
    except Exception as e:
        pass  # Non-critical — insert will still work

SPOT_EST = {"gold": 6500, "silver": 100, "platinum": 2500}
MAX_PREMIUM = 4.0   # reject if price/oz > spot * 4x
MIN_PREMIUM = 0.75  # reject if price/oz < spot * 0.75x

def is_price_sane(row):
    """Return False if buy_price or sell_price is wildly out of range vs spot estimate."""
    metal = row.get("metal", "")
    spot = SPOT_EST.get(metal)
    if not spot:
        return True  # unknown metal, let it through
    weight_oz = row.get("weight_oz")
    if not weight_oz or weight_oz <= 0:
        return True  # no weight to validate against
    for price_field in ("buy_price", "sell_price"):
        price = row.get(price_field)
        if price is None:
            continue
        ratio = price / (spot * weight_oz)
        if ratio > MAX_PREMIUM or ratio < MIN_PREMIUM:
            print(f"  ✗ REJECTED insane price: {row.get('dealer')} {metal} {weight_oz}oz "
                  f"{price_field}=${price:,.0f} ({ratio:.1f}x spot)")
            return False
    return True

def save_to_db(row):
    if not is_price_sane(row):
        return False
    try:
        # Delete old price first — prevents duplicates
        delete_existing(row)
        # Insert fresh price
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
            {"url": "https://ainsliebullion.com.au/Buy/Keyword/Silver-Coins/ID/3", "link_sel": "a[href*='/Buy/View/Product/']", "wait": 6000},
            {"url": "https://ainsliebullion.com.au/Buy/Keyword/Silver-Bars/ID/16", "link_sel": "a[href*='/Buy/View/Product/']", "wait": 6000},
            {"url": "https://ainsliebullion.com.au/Buy/Keyword/Gold-Bars/ID/15",
             "link_sel": "a[href*='/Buy/View/Product/']", "wait": 4000},
        ],
        "price_sels": ["span.price-number", ".price-number", ".price", ".product-price"],
        "base_url": "https://ainsliebullion.com.au",
    },
    {
        "name": "Guardian Gold",
        "pages": [
            {"url": "https://guardian-gold.com.au/product-category/gold/buy-gold-cast-bars/", "link_sel": "a[href*='/product/']", "wait": 4000},
            {"url": "https://guardian-gold.com.au/product-category/gold/buy-gold-minted-bars/", "link_sel": "a[href*='/product/']", "wait": 4000},
            {"url": "https://guardian-gold.com.au/product-category/gold/gold-coins/", "link_sel": "a[href*='/product/']", "wait": 4000},
            {"url": "https://guardian-gold.com.au/product-category/silver/silver-buy-silver-bars/", "link_sel": "a[href*='/product/']", "wait": 4000},
            {"url": "https://guardian-gold.com.au/product-category/silver/buy-silver-coins/", "link_sel": "a[href*='/product/']", "wait": 4000},
            {"url": "https://guardian-gold.com.au/product-category/platinum/", "link_sel": "a[href*='/product/']", "wait": 4000},
        ],
        "price_sels": ["span.price", ".price bdi", ".woocommerce-Price-amount bdi"],
        "base_url": "https://guardian-gold.com.au",
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
            {"url": "https://www.perthmint.com/shop/bullion/bullion-coins/australian-kangaroo-2026-1oz-gold-bullion-coin/", "link_sel": "h1", "wait": 8000, "networkidle": True, "is_direct": True, "name": "2026 1oz Australian Kangaroo Gold Bullion Coin"},
            {"url": "https://www.perthmint.com/shop/bullion/bullion-coins/australian-kangaroo-2026-1-2oz-gold-bullion-coin/", "link_sel": "h1", "wait": 8000, "networkidle": True, "is_direct": True, "name": "2026 1/2oz Australian Kangaroo Gold Bullion Coin"},
            {"url": "https://www.perthmint.com/shop/bullion/bullion-coins/australian-kangaroo-2026-1-4oz-gold-bullion-coin/", "link_sel": "h1", "wait": 8000, "networkidle": True, "is_direct": True, "name": "2026 1/4oz Australian Kangaroo Gold Bullion Coin"},
            {"url": "https://www.perthmint.com/shop/bullion/bullion-coins/australian-kangaroo-2026-1-10oz-gold-bullion-coin/", "link_sel": "h1", "wait": 8000, "networkidle": True, "is_direct": True, "name": "2026 1/10oz Australian Kangaroo Gold Bullion Coin"},
            {"url": "https://www.perthmint.com/shop/bullion/bullion-coins/australian-kangaroo-2026-1oz-silver-bullion-coin-in-pouch/", "link_sel": "h1", "wait": 8000, "networkidle": True, "is_direct": True, "name": "2026 1oz Australian Kangaroo Silver Bullion Coin"},
            {"url": "https://www.perthmint.com/shop/bullion/bullion-coins/australian-kookaburra-2026-1oz-silver-bullion-coin/", "link_sel": "h1", "wait": 8000, "networkidle": True, "is_direct": True, "name": "2026 1oz Australian Kookaburra Silver Bullion Coin"},
            {"url": "https://www.perthmint.com/shop/bullion/minted-bars/kangaroo-1oz-minted-gold-bar/", "link_sel": "h1", "wait": 8000, "networkidle": True, "is_direct": True, "name": "1oz Perth Mint Kangaroo Minted Gold Bar"},
            {"url": "https://www.perthmint.com/shop/bullion/minted-bars/kangaroo-10g-minted-gold-bar/", "link_sel": "h1", "wait": 8000, "networkidle": True, "is_direct": True, "name": "10g Perth Mint Kangaroo Minted Gold Bar"},
            {"url": "https://www.perthmint.com/shop/bullion/minted-bars/kangaroo-5g-minted-gold-bar/", "link_sel": "h1", "wait": 8000, "networkidle": True, "is_direct": True, "name": "5g Perth Mint Kangaroo Minted Gold Bar"},
            {"url": "https://www.perthmint.com/shop/bullion/minted-bars/kangaroo-1g-minted-gold-bar/", "link_sel": "h1", "wait": 8000, "networkidle": True, "is_direct": True, "name": "1g Perth Mint Kangaroo Minted Gold Bar"},
            {"url": "https://www.perthmint.com/shop/bullion/cast-bars/perth-mint-1oz-gold-cast-bar/", "link_sel": "h1", "wait": 12000, "networkidle": True, "is_direct": True, "name": "1oz Perth Mint Kangaroo Cast Gold Bar"},
            {"url": "https://www.perthmint.com/shop/bullion/cast-bars/perth-mint-100g-gold-cast-bar/", "link_sel": "h1", "wait": 12000, "networkidle": True, "is_direct": True, "name": "100g Perth Mint Kangaroo Cast Gold Bar"},
            {"url": "https://www.perthmint.com/shop/bullion/minted-bars/kangaroo-5g-minted-gold-bar/", "link_sel": "h1", "wait": 12000, "networkidle": True, "is_direct": True, "name": "5g Perth Mint Kangaroo Minted Gold Bar"},
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
            try:
                from xml.etree import ElementTree as ET
                req = urllib.request.Request(page_config["url"], headers={"User-Agent":"Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    xml = r.read()
                root = ET.fromstring(xml)
                ns = {"sm":"http://www.sitemaps.org/schemas/sitemap/0.9"}
                urls = [loc.text for loc in root.findall(".//sm:loc", ns) if loc.text]
                # Filter to product pages only, exclude category/tag pages
                BULLION_KEYWORDS = ["gold","silver","platinum","bar","coin","bullion","oz","gram","kilo","pamp","heraeus","abc","baird","valcambi","krugerrand","kangaroo","kookaburra","lunar","britannia","maple","philharmonic","emu"]
                product_urls = [
                    u for u in urls
                    if "/product/" in u
                    and "/product-category/" not in u
                    and any(k in u.lower() for k in BULLION_KEYWORDS)
                ]
                print(f"    Sitemap: {len(product_urls)} product URLs found")
                return [{"href": u, "text": ""} for u in product_urls]
            except Exception as e:
                print(f"    Sitemap error: {e}")
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
        # Check for unavailable products
        page_text = await page.inner_text("body")
        if "Unavailable" in page_text and "Add to Cart" not in page_text:
            return None, "product unavailable"
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
                "url": url, "status": "OK", "available": True, "last_seen": datetime.now(timezone.utc).isoformat(), "in_stock": True}, None

    except Exception as e:
        return None, f"error: {str(e)[:60]}"



async def scrape_jaggards_sell(page):
    """Scrape Jaggards live buyback prices"""
    results = []
    try:
        await page.goto("https://www.jaggards.com.au/sell-to-us/",
                       wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        rows = await page.query_selector_all("table tr")
        current_metal = "gold"
        for row in rows:
            cells = await row.query_selector_all("td")
            if len(cells) < 2:
                # Check for section header
                header = await row.query_selector("th, td")
                if header:
                    txt = (await header.inner_text()).lower()
                    if "silver" in txt:
                        current_metal = "silver"
                    elif "gold" in txt:
                        current_metal = "gold"
                continue

            name = (await cells[0].inner_text()).strip()
            price_str = (await cells[-1].inner_text()).strip().replace("$","").replace(",","")

            try:
                price = float(price_str)
            except:
                continue

            if price <= 0:
                continue

            # Parse weight from name e.g. "1oz Gold .9999", "5g Gold .9999"
            wm = re.search(r"(1/20|1/10|1/4|1/2|\d+(?:\.\d+)?)(oz|g|kg)", name.lower())
            if not wm:
                continue

            wstr  = wm.group(1)
            wunit = wm.group(2)

            frac_map = {"1/20":0.05,"1/10":0.1,"1/4":0.25,"1/2":0.5}
            if wstr in frac_map:
                wval = frac_map[wstr]
            else:
                wval = float(wstr)

            if wunit == "oz":
                weight_oz = wval
            elif wunit == "kg":
                weight_oz = wval * 32.1507
            else:
                weight_oz = wval / 31.1035

            results.append({
                "dealer":    "Jaggards",
                "metal":     current_metal,
                "sell_price": price,
                "weight_oz": round(weight_oz, 4),
                "category":  "bar",
                "status":    "OK",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            })
            print(f"  ✓ Jaggards buyback {current_metal} {weight_oz:.4f}oz @ A${price:.2f}")

    except Exception as e:
        print(f"  ✗ Jaggards sell error: {e}")
    return results


async def scrape_bullion_now_sell(page):
    """Bullion Now — prices in nfusionsolutions iframe"""
    results = []
    try:
        await page.goto("https://bullionnow.com.au/sell-my-bullion/",
                       wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(8000)
        frame = next((f for f in page.frames if "nfusionsolutions" in f.url and "table" in f.url), None)
        if not frame:
            print("  ⚠️  Bullion Now iframe not found")
            return results
        data = await frame.evaluate("""() => {
            const rows = document.querySelectorAll('tr.symbol-block');
            return Array.from(rows).map(r => ({
                metal: r.querySelector('th.symbol') ? r.querySelector('th.symbol').innerText : '',
                price: r.querySelector('.value') ? r.querySelector('.value').innerText : ''
            }));
        }""")
        for item in data:
            metal_txt = item.get("metal","").strip().lower()
            price_str = item.get("price","").replace("A","").replace("$","").replace(",","").strip()
            if metal_txt not in ["gold","silver","platinum"]: continue
            try:
                price = float(price_str)
                if price > 0:
                    results.append({"dealer":"Bullion Now","metal":metal_txt,
                        "sell_price":price,"weight_oz":1.0,"category":"bar",
                        "status":"OK","scraped_at":datetime.now(timezone.utc).isoformat()})
                    print(f"  ✓ Bullion Now buyback {metal_txt} 1oz @ A${price:.2f}")
            except: pass
    except Exception as e:
        print(f"  ✗ Bullion Now sell error: {e}")
    return results


async def scrape_melbourne_gold_sell(page):
    """Melbourne Gold Company — bullion rates from li elements"""
    results = []
    try:
        await page.goto("https://www.melbournegoldcompany.com.au/gold-buyers-melbourne.html",
                       wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)
        items = await page.query_selector_all("li")
        for item in items:
            txt = (await item.inner_text()).strip()
            lines = [l.strip() for l in txt.split("\n") if l.strip()]
            if len(lines) < 2:
                continue
            name = lines[0]
            # Only bullion bars/coins — skip purity/jewellery rows
            if not re.search(r"(oz|kg|gram).*(gold|silver)", name.lower()) and                not re.search(r"(gold|silver).*(oz|g|kg)", name.lower()):
                continue
            if any(x in name.lower() for x in ["purity","per gram","round coin","granule"]):
                continue
            price_str = lines[1].replace("$","").replace(",","").strip()
            try:
                price = float(price_str)
            except:
                continue
            if price <= 0:
                continue
            metal = "silver" if "silver" in name.lower() else "gold"
            weight_oz = None
            # Handle "1oz", "10oz", "1kg" style
            wm = re.search(r"(\d+(?:\.\d+)?)\s*(oz|g\b|kg)", name.lower())
            if wm:
                wval  = float(wm.group(1))
                wunit = wm.group(2).strip()
                if wunit == "oz":   weight_oz = wval
                elif wunit == "g":  weight_oz = wval / 31.1035
                elif wunit == "kg": weight_oz = wval * 32.1507
            if not weight_oz:
                continue
            results.append({
                "dealer":"Melbourne Gold Company","metal":metal,
                "sell_price":price,"weight_oz":round(weight_oz,4),"category":"bar",
                "status":"OK","scraped_at":datetime.now(timezone.utc).isoformat(),
            })
            print(f"  ✓ Melbourne Gold buyback {metal} {weight_oz:.4f}oz @ A${price:.2f}")
    except Exception as e:
        print(f"  ✗ Melbourne Gold sell error: {e}")
    return results


async def scrape_imperial_sell(page):
    """Imperial Bullion Brisbane — bullion bars and coins, gold + silver"""
    results = []
    FRAC = {"1/20oz":0.05,"1/10oz":0.1,"1/4oz":0.25,"1/2oz":0.5}
    try:
        await page.goto("https://imperialbullion.com.au/sell-prices/",
                       wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(6000)

        # Track current metal via section headings
        current_metal = "gold"
        elements = await page.query_selector_all("h3, li")
        for el in elements:
            tag = await el.evaluate("e => e.tagName.toLowerCase()")

            if tag == "h3":
                heading = (await el.inner_text()).strip().lower()
                if "silver" in heading:
                    current_metal = "silver"
                elif "gold" in heading:
                    current_metal = "gold"
                continue

            # li element
            title_el = await el.query_selector("span.title")
            meta_el  = await el.query_selector("span.meta")
            if not title_el or not meta_el:
                continue

            name = (await title_el.inner_text()).strip()
            if any(x in name.lower() for x in ["ct gold","sovereign","$200","half sov"]):
                continue

            img = await meta_el.query_selector("img")
            if img:
                continue

            price_str = (await meta_el.inner_text()).strip().replace("$","").replace(",","")
            try:
                price = float(price_str)
            except:
                continue
            if price <= 0:
                continue

            name_l = name.lower().strip()
            weight_oz = None
            for frac, oz in FRAC.items():
                if frac in name_l.replace(" ",""):
                    weight_oz = oz
                    break
            if not weight_oz:
                wm = re.search(r"(\d+(?:\.\d+)?)\s*(oz|g\b|kg|kilo)", name_l)
                if wm:
                    wval  = float(wm.group(1))
                    wunit = wm.group(2)
                    if wunit == "oz":            weight_oz = wval
                    elif wunit == "g":           weight_oz = wval / 31.1035
                    elif wunit in ["kg","kilo"]: weight_oz = wval * 32.1507
            if not weight_oz:
                continue

            # Sanity check vs spot
            spot_est = 6500 if current_metal == "gold" else 100
            if price > spot_est * weight_oz * 1.5 or price < spot_est * weight_oz * 0.5:
                continue

            cat = "coin" if "coin" in name_l or "lunar" in name_l else "bar"
            results.append({
                "dealer":"Imperial Bullion","metal":current_metal,
                "sell_price":price,"weight_oz":round(weight_oz,4),
                "category":cat,"status":"OK",
                "scraped_at":datetime.now(timezone.utc).isoformat(),
            })
            print(f"  ✓ Imperial buyback {current_metal} {weight_oz:.4f}oz [{name[:25]}] @ A${price:.2f}")

    except Exception as e:
        print(f"  ✗ Imperial sell error: {e}")
    return results


async def scrape_perth_mint_sell(page):
    """Scrape Perth Mint buyback prices - clicks accordions to reveal tables"""
    results = []
    WEIGHT_MAP = {
        "1/20 ounce":0.05,"1/10 ounce":0.1,"1/4 ounce":0.25,"1/2 ounce":0.5,
        "1 ounce":1.0,"2 ounce":2.0,"10 ounce":10.0,"1 kilo":32.1507,
        "1 gram":0.0322,"5 gram":0.1608,"10 gram":0.3215,"20 gram":0.6430,
        "50 gram":1.6076,"100 gram":3.2151,"1 kilogram":32.1507,
    }
    METAL_SECTIONS = [
        ("gold coins",   "gold"),
        ("gold cast",    "gold"),
        ("gold minted",  "gold"),
        ("silver coins", "silver"),
        ("silver cast",  "silver"),
        ("silver minted","silver"),
    ]
    try:
        await page.goto("https://www.perthmint.com/invest/information-for-investors/metal-prices/",
                       wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)

        # Click all accordion sections open — scroll into view first
        accordions = await page.query_selector_all("a.accordion-title")
        for acc in accordions:
            label = (await acc.inner_text()).strip().lower()
            if "jewellery" in label or "hallmark" in label or "other" in label:
                continue
            try:
                await acc.scroll_into_view_if_needed()
                await page.wait_for_timeout(300)
                expanded = await acc.get_attribute("aria-expanded")
                if expanded != "true":
                    await acc.click()
                    await page.wait_for_timeout(1000)
            except:
                pass

        await page.wait_for_timeout(2000)

        # Now scrape all open accordion tables
        sections = await page.query_selector_all("a.accordion-title")
        for acc in sections:
            label = (await acc.inner_text()).strip().lower()
            if "jewellery" in label or "hallmark" in label or "other" in label:
                continue

            # Determine metal
            metal = "gold" if "gold" in label else "silver" if "silver" in label else None
            if not metal:
                continue

            # Get the associated accordion content
            ctrl_id = await acc.get_attribute("aria-controls")
            if not ctrl_id:
                continue
            content = await page.query_selector(f"[id='{ctrl_id}']")
            if not content:
                continue

            rows = await content.query_selector_all("div[role='row']")
            for row in rows:
                cells = await row.query_selector_all("span[role='cell']")
                if len(cells) < 3:
                    continue
                weight_str = (await cells[0].inner_text()).strip().lower()
                buy_str    = (await cells[2].inner_text()).strip().replace("$","").replace(",","").strip()

                weight_oz = WEIGHT_MAP.get(weight_str)
                if not weight_oz:
                    # try gram patterns
                    wm = re.search(r"(\d+)\s*gram", weight_str)
                    if wm:
                        weight_oz = int(wm.group(1)) / 31.1035

                if not weight_oz:
                    continue
                try:
                    price = float(buy_str)
                    if price > 0:
                        results.append({
                            "dealer":"Perth Mint","metal":metal,
                            "sell_price":price,"weight_oz":round(weight_oz,4),
                            "category":"coin" if "coin" in label else "bar",
                        })
                        print(f"  ✓ Perth Mint buys {metal} {weight_oz:.4f}oz @ A${price:.2f}")
                except:
                    pass
    except Exception as e:
        print(f"  ✗ Perth Mint sell error: {e}")
    return results

async def scrape_abc_sell(page):
    """Scrape ABC Bullion buyback prices — 3-column table: name, sell, buyback"""
    results = []
    FRAC = {"1/20":0.05,"1/10":0.1,"1/4":0.25,"1/2":0.5}
    try:
        for metal, url in [
            ("gold",   "https://www.abcbullion.com.au/products-pricing/gold"),
            ("silver", "https://www.abcbullion.com.au/products-pricing/silver"),
        ]:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(6000)
            rows = await page.query_selector_all("table tr")
            for row in rows:
                cells = await row.query_selector_all("td")
                if len(cells) < 3:
                    continue
                name        = (await cells[0].inner_text()).strip()
                buyback_str = (await cells[2].inner_text()).strip().replace("$","").replace(",","")
                try:
                    sell_price = float(buyback_str)
                except:
                    continue
                if sell_price < 50:
                    continue
                name_l = name.lower()
                if any(x in name_l for x in ["pool","tael","luong","good delivery","400oz","kilo bar","5kg","10kg"]):
                    continue
                weight_oz = None
                for frac, oz in FRAC.items():
                    if frac+"oz" in name_l or frac+" oz" in name_l:
                        weight_oz = oz
                        break
                if not weight_oz:
                    wm = re.search(r"(\d+(?:\.\d+)?)\s*(oz|g|kg)\b", name_l)
                    if wm:
                        wval  = float(wm.group(1))
                        wunit = wm.group(2)
                        if wunit == "oz":   weight_oz = wval
                        elif wunit == "g":  weight_oz = wval / 31.1035
                        elif wunit == "kg": weight_oz = wval * 32.1507
                if not weight_oz:
                    continue
                spot_est = 6500 if metal == "gold" else 100
                expected = spot_est * weight_oz
                if sell_price > expected * 1.5 or sell_price < expected * 0.5:
                    continue
                results.append({
                    "dealer":"ABC Bullion","metal":metal,
                    "sell_price":sell_price,"weight_oz":round(weight_oz,4),
                    "category":"coin" if "coin" in name_l else "bar",
                })
                print(f"  ✓ ABC buyback {metal} {weight_oz:.4f}oz [{name[:30]}] @ A${sell_price:.2f}")
    except Exception as e:
        print(f"  ✗ ABC sell error: {e}")
    return results


async def scrape_guardian_sell(page):
    """Scrape Guardian Gold live buyback rates"""
    results = []
    try:
        await page.goto("https://guardian-gold.com.au/sell-bullion/",
                       wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)
        
        rows = await page.query_selector_all("table tr")
        current_metal = None
        for row in rows:
            cells = await row.query_selector_all("td")
            if not cells:
                continue
            texts = [(await c.inner_text()).strip() for c in cells]
            
            if len(texts) >= 1 and texts[0] in ["Gold", "Silver", "Platinum"]:
                current_metal = texts[0].lower()
                continue
            
            if current_metal and len(texts) >= 2:
                weight_str = texts[0].strip()
                price_str  = texts[-1].replace("$","").replace(",","").strip()
                
                # Parse weight
                import re as re2
                wm = re2.search(r"(\d+(?:\.\d+)?)(g|oz|KG|kg)", weight_str)
                if not wm:
                    continue
                wval = float(wm.group(1))
                wunit = wm.group(2).lower()
                if wunit == "oz":
                    weight_oz = wval
                elif wunit == "kg":
                    weight_oz = wval * 32.1507
                else:
                    weight_oz = wval / 31.1035
                
                try:
                    sell_price = float(price_str)
                    if sell_price > 0:
                        results.append({
                            "dealer": "Guardian Gold",
                            "metal": current_metal,
                            "sell_price": sell_price,
                            "weight_oz": round(weight_oz, 4),
                            "category": "bar",
                        })
                        print(f"  ✓ Guardian buyback {current_metal} {weight_oz:.2f}oz @ A${sell_price:.2f}")
                except:
                    pass
    except Exception as e:
        print(f"  ✗ Guardian sell error: {e}")
    return results

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

            # Parallel scraping — 5 tabs at once
            # Reduce batch for slow dealers
            BATCH = 3 if "perth" not in dealer["name"].lower() else 1
            extra_pages = [await context.new_page() for _ in range(BATCH - 1)]
            pool = [page] + extra_pages

            async def scrape_one(pg, link):
                cfg = next(
                    (p for p in dealer["pages"] if p["url"] == link["href"]),
                    dealer["pages"][0]
                )
                return await scrape_product(
                    pg, dealer, link["href"], link["text"],
                    dealer["price_sels"],
                    cfg.get("wait", 3000),
                    dealer.get("use_meta_price", False),
                    page_config=cfg,
                )

            all_batch = []
            for i in range(0, len(unique), BATCH):
                batch = unique[i:i+BATCH]
                tasks = [scrape_one(pool[j], lnk) for j, lnk in enumerate(batch)]
                out = await asyncio.gather(*tasks, return_exceptions=True)
                all_batch.extend(out)

            for _res in all_batch:
                if isinstance(_res, Exception):
                    continue
                if isinstance(_res, tuple):
                    result, reason = _res
                else:
                    result = _res
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
                    if reason == "product unavailable":
                        try:
                            patch_data = json.dumps({"available": False}).encode()
                            req2 = urllib.request.Request(
                                f"{SUPABASE_URL}/rest/v1/prices_v2?dealer=eq.{urllib.parse.quote(dealer['name'])}&status=eq.OK",
                                data=patch_data,
                                headers={**DB_HEADERS, "Content-Type": "application/json"},
                                method="PATCH"
                            )
                            urllib.request.urlopen(req2, timeout=5)
                        except:
                            pass

            if fail_reasons:
                print(f"\n  Failures:")
                for r, cnt in sorted(fail_reasons.items(), key=lambda x: -x[1])[:5]:
                    print(f"    {cnt}x {r}")

            print(f"\n  → {len(saved_this_run)} saved for {dealer['name']}")

        # ── Sell price scraping ──────────────────────────────────────────────────
        print(f"\n{'='*65}")
        print("  SELL PRICES")
        print(f"{'='*65}")
        sell_results = []
        for fn, name in [
            (scrape_perth_mint_sell, "Perth Mint"),
            (scrape_abc_sell, "ABC Bullion"),
            (scrape_guardian_sell, "Guardian Gold"),
            (scrape_jaggards_sell, "Jaggards"),
            (scrape_bullion_now_sell, "Bullion Now"),
            (scrape_melbourne_gold_sell, "Melbourne Gold Company"),
            (scrape_imperial_sell, "Imperial Bullion"),
        ]:
            print(f"\n  {name}")
            try:
                res = await fn(page)
                sell_results.extend(res)
            except Exception as e:
                print(f"  ✗ {name} sell failed: {e}")

        if sell_results:
            print(f"\n  Saving {len(sell_results)} sell prices...")
            saved_sell = 0
            for row in sell_results:
                try:
                    # Match existing row and update sell_price only
                    dealer   = row["dealer"]
                    metal    = row["metal"]
                    weight   = row.get("weight_oz")
                    sell_p   = row["sell_price"]
                    import json as json2
                    # Update existing rows matching dealer+metal+weight
                    url = (f"{SUPABASE_URL}/rest/v1/prices_v2"
                           f"?dealer=eq.{urllib.parse.quote(dealer)}"
                           f"&metal=eq.{metal}"
                           + (f"&weight_oz=eq.{weight}" if weight else ""))
                    patch_data = json2.dumps({"sell_price": sell_p}).encode()
                    req = urllib.request.Request(url, data=patch_data,
                        headers={**DB_HEADERS,"Content-Type":"application/json"},
                        method="PATCH")
                    urllib.request.urlopen(req, timeout=10)
                    saved_sell += 1
                except Exception as e:
                    pass
            print(f"  ✓ {saved_sell} sell prices updated")

        await browser.close()

    print(f"\n{'='*65}")
    print(f"  DONE — {total_saved} saved · {total_deduped} deduped · {total_invalid} invalid")
    print(f"{'='*65}")

if __name__ == "__main__":
    asyncio.run(main())