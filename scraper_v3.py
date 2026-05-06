#!/usr/bin/env python3
"""
GoldSilverPrices.com.au — Scraper v3
Architecture: direct-URL catalogue, per-product availability tracking
- Each product/dealer combo has a known URL
- Availability detected per page (out of stock / sold out / unavailable)
- available=false hides from FE; auto-recovers to true on next successful scrape
- All 7 sell scrapers ported and working
"""

import asyncio
import json
import re
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone
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

# ── Constants ─────────────────────────────────────────────────────────────────
G_PER_OZ    = 31.1035
SPOT_EST    = {"gold": 6500, "silver": 100, "platinum": 2500}
MAX_PREMIUM = 4.0
MIN_PREMIUM = 0.75

UNAVAILABLE_PHRASES = [
    "out of stock",
    "sold out",
    "currently unavailable",
    "this product is unavailable",
    "notify me when available",
    "add to waitlist",
    "join waitlist",
]

# Dealers whose pages show multiple prices (e.g. spot + retail) — target the product price element directly
DEALER_PRICE_SELECTORS = {
    # WooCommerce dealers: p.price scopes to the product price, avoiding spot-price widgets
    "Guardian Gold":  "p.price",
    "Gold Stackers":  "p.price",
    "Swan Bullion":   "p.price",
    "Jaggards":       "p.price",
    # Magento (KJC): finalPrice data attribute holds the true product price
    "KJC Bullion":    "[data-price-type='finalPrice'] .price",
}

DEBUG_DEALER = None  # set via --debug "Dealer Name"
NO_SELL      = False # set via --no-sell
NO_SAVE      = False # set via --no-save (dry run)


# ── Utility ───────────────────────────────────────────────────────────────────

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
    return min(retail) if retail else min(candidates)


def detect_availability(text):
    """Return False if page clearly says product is not purchasable."""
    t = text.lower()
    return not any(phrase in t for phrase in UNAVAILABLE_PHRASES)


def is_price_sane(metal, price, weight_oz):
    spot = SPOT_EST.get(metal)
    if not spot or not weight_oz or weight_oz <= 0:
        return True
    ratio = price / (spot * weight_oz)
    if ratio > MAX_PREMIUM or ratio < MIN_PREMIUM:
        print(f"    ✗ REJECTED insane price: {metal} {weight_oz}oz ${price:,.0f} ({ratio:.1f}x spot)")
        return False
    return True


def delete_existing(row):
    try:
        filters = [
            f"dealer=eq.{urllib.parse.quote(row['dealer'])}",
            f"metal=eq.{row['metal']}",
            f"category=eq.{row['category']}",
        ]
        if row.get("coin_type"):
            filters.append(f"coin_type=eq.{urllib.parse.quote(row['coin_type'])}")
        else:
            filters.append("coin_type=is.null")
        if row.get("bar_brand"):
            filters.append(f"bar_brand=eq.{urllib.parse.quote(row['bar_brand'])}")
        else:
            filters.append("bar_brand=is.null")
        if row.get("bar_type"):
            filters.append(f"bar_type=eq.{row['bar_type']}")
        if row.get("weight_oz") is not None:
            filters.append(f"weight_oz=eq.{row['weight_oz']}")
        url = f"{SUPABASE_URL}/rest/v1/prices_v2?{'&'.join(filters)}"
        req = urllib.request.Request(url, headers=DB_HEADERS, method="DELETE")
        urllib.request.urlopen(req, timeout=10)
        # Also remove stale rows with weight_oz=null for same product (left by old scraper)
        if row.get("weight_g") and row.get("weight_oz") is not None:
            null_filters = [f for f in filters if "weight_oz" not in f]
            null_filters.append("weight_oz=is.null")
            null_url = f"{SUPABASE_URL}/rest/v1/prices_v2?{'&'.join(null_filters)}"
            urllib.request.urlopen(
                urllib.request.Request(null_url, headers=DB_HEADERS, method="DELETE"),
                timeout=10
            )
    except:
        pass


def patch_available(row, available):
    """PATCH only the available flag — used when product is unavailable and no price shown."""
    try:
        filters = [
            f"dealer=eq.{urllib.parse.quote(row['dealer'])}",
            f"metal=eq.{row['metal']}",
            f"category=eq.{row['category']}",
        ]
        if row.get("coin_type"):
            filters.append(f"coin_type=eq.{urllib.parse.quote(row['coin_type'])}")
        else:
            filters.append("coin_type=is.null")
        if row.get("bar_brand"):
            filters.append(f"bar_brand=eq.{urllib.parse.quote(row['bar_brand'])}")
        else:
            filters.append("bar_brand=is.null")
        if row.get("weight_oz") is not None:
            filters.append(f"weight_oz=eq.{row['weight_oz']}")
        url = f"{SUPABASE_URL}/rest/v1/prices_v2?{'&'.join(filters)}"
        patch_data = json.dumps({
            "available":  available,
            "last_seen":  datetime.now(timezone.utc).isoformat(),
        }).encode()
        req = urllib.request.Request(
            url, data=patch_data,
            headers={**DB_HEADERS, "Content-Type": "application/json"},
            method="PATCH"
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"    [PATCH ERROR] {e}")


TIER1_DEALERS = {"Ainslie Bullion", "Gold Stackers", "Gold Bullion Australia"}

def save_to_db(row):
    if NO_SAVE:
        return True
    if row.get("dealer") in TIER1_DEALERS:
        # Tier 1 dealers are managed exclusively by their dedicated push_*.py scripts.
        # Skipping here prevents this scraper from corrupting their data.
        return True
    try:
        delete_existing(row)
        payload = json.dumps(row).encode("utf-8")
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/prices_v2",
            data=payload, headers=DB_HEADERS, method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 201)
    except Exception as e:
        body = e.read().decode() if hasattr(e, "read") else ""
        if row.get("buy_url") and "buy_url" in body:
            # buy_url column not yet added — retry without it
            row_copy = {k: v for k, v in row.items() if k != "buy_url"}
            try:
                payload = json.dumps(row_copy).encode("utf-8")
                req = urllib.request.Request(
                    f"{SUPABASE_URL}/rest/v1/prices_v2",
                    data=payload, headers=DB_HEADERS, method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return resp.status in (200, 201)
            except Exception as e2:
                body2 = e2.read().decode() if hasattr(e2, "read") else ""
                print(f"    [DB ERROR] {e2} — {body2}")
                return False
        print(f"    [DB ERROR] {e} — {body}")
        return False


def save_sell_prices(sell_results):
    if NO_SAVE:
        return
    print(f"\n  Saving {len(sell_results)} sell prices...")
    saved = 0
    for row in sell_results:
        try:
            filters = [
                f"dealer=eq.{urllib.parse.quote(row['dealer'])}",
                f"metal=eq.{row['metal']}",
                f"weight_oz=eq.{row['weight_oz']}",
            ]
            url = f"{SUPABASE_URL}/rest/v1/prices_v2?{'&'.join(filters)}"
            patch = json.dumps({
                "sell_price": row["sell_price"],
                "last_seen":  datetime.now(timezone.utc).isoformat(),
            }).encode()
            req = urllib.request.Request(
                url, data=patch,
                headers={**DB_HEADERS, "Content-Type": "application/json"},
                method="PATCH"
            )
            urllib.request.urlopen(req, timeout=10)
            saved += 1
        except Exception as e:
            print(f"    [SELL PATCH ERROR] {e}")
    print(f"  ✓ {saved} sell prices updated")


# ── Buy scraper ───────────────────────────────────────────────────────────────

async def scrape_product(page, product_name, product_def, dealer_entry):
    """
    Scrape one product at one dealer.
    Returns: "ok" | "unavailable" | "no_price" | "error"
    """
    url       = dealer_entry["url"]
    dealer    = dealer_entry["dealer"]
    metal     = product_def["metal"]
    min_val   = dealer_entry.get("min_val", product_def["min_aud"])
    max_val   = dealer_entry.get("max_val", product_def["max_aud"])
    weight_oz = product_def.get("weight_oz")
    weight_g  = product_def.get("weight_g")

    if weight_g and not weight_oz:
        weight_oz = round(weight_g / G_PER_OZ, 4)

    try:
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        if dealer_entry.get("networkidle"):
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except:
                pass
        await page.wait_for_timeout(dealer_entry.get("wait", 4000))

        # URL drift: product removed → page redirects to home/category. Bail out early.
        final_url = page.url
        if not final_url.startswith(url[:40]):
            print(f"  ! {dealer:25s} URL redirected → {final_url[:70]}")
            return "error"

        text      = await page.inner_text("body")
        available = detect_availability(text)
        sel = DEALER_PRICE_SELECTORS.get(dealer)
        if sel:
            el = await page.query_selector(sel)
            if el:
                price_text = await el.inner_text()
                price = extract_price(price_text, min_val, max_val)
            else:
                price = extract_price(text, min_val, max_val)  # element not found — fall back
        else:
            price = extract_price(text, min_val, max_val)

        row = {
            "dealer":     dealer,
            "metal":      metal,
            "category":   product_def["category"],
            "coin_type":  product_def.get("coin_type"),
            "bar_brand":  product_def.get("bar_brand"),
            "bar_type":   product_def.get("bar_type"),
            "weight_oz":  weight_oz,
            "weight_g":   weight_g,
            "available":  available,
            "status":     "OK",
            "buy_url":    url,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

        weight_str = f"{weight_oz}oz" if weight_oz else f"{weight_g}g"
        avail_icon = "✓" if available else "✗"

        if price and is_price_sane(metal, price, weight_oz):
            row["buy_price"] = price
            saved = save_to_db(row)
            tick  = "db✓" if saved else "db✗"
            suffix = "  UNAVAIL" if not available else ""
            print(f"  {avail_icon} {dealer:25s} {weight_str:8s} ${price:>10,.2f}  [{tick}{suffix}]")
            return "unavailable" if not available else "ok"

        elif not available:
            # Unavailable and no price — just flip the flag, preserve last known price
            patch_available(row, False)
            print(f"  ✗ {dealer:25s} {weight_str:8s} no price — marked unavailable")
            return "unavailable"

        else:
            print(f"  ? {dealer:25s} {weight_str:8s} no price found")
            return "no_price"

    except Exception as e:
        print(f"  ✗ {dealer:25s} ERROR: {str(e)[:80]}")
        return "error"


# ── Sell scrapers ─────────────────────────────────────────────────────────────

async def scrape_perth_mint_sell(page):
    results = []
    WEIGHT_MAP = {
        "1/20 ounce":0.05,"1/10 ounce":0.1,"1/4 ounce":0.25,"1/2 ounce":0.5,
        "1 ounce":1.0,"2 ounce":2.0,"10 ounce":10.0,"1 kilo":32.1507,
        "1 gram":0.0322,"5 gram":0.1608,"10 gram":0.3215,"20 gram":0.6430,
        "50 gram":1.6076,"100 gram":3.2151,"1 kilogram":32.1507,
    }
    try:
        await page.goto("https://www.perthmint.com/invest/information-for-investors/metal-prices/",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)
        accordions = await page.query_selector_all("a.accordion-title")
        for acc in accordions:
            label = (await acc.inner_text()).strip().lower()
            if any(x in label for x in ["jewellery","hallmark","other"]):
                continue
            try:
                await acc.scroll_into_view_if_needed()
                await page.wait_for_timeout(300)
                if await acc.get_attribute("aria-expanded") != "true":
                    await acc.click()
                    await page.wait_for_timeout(1000)
            except:
                pass
        await page.wait_for_timeout(2000)
        sections = await page.query_selector_all("a.accordion-title")
        for acc in sections:
            label = (await acc.inner_text()).strip().lower()
            if any(x in label for x in ["jewellery","hallmark","other"]):
                continue
            metal = "gold" if "gold" in label else "silver" if "silver" in label else None
            if not metal:
                continue
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
                weight_oz  = WEIGHT_MAP.get(weight_str)
                if not weight_oz:
                    wm = re.search(r"(\d+)\s*gram", weight_str)
                    if wm:
                        weight_oz = int(wm.group(1)) / G_PER_OZ
                if not weight_oz:
                    continue
                try:
                    price = float(buy_str)
                    if price > 0:
                        results.append({"dealer":"Perth Mint","metal":metal,
                            "sell_price":price,"weight_oz":round(weight_oz,4),
                            "category":"coin" if "coin" in label else "bar"})
                        print(f"  ✓ Perth Mint buys {metal} {weight_oz:.4f}oz @ A${price:.2f}")
                except:
                    pass
    except Exception as e:
        print(f"  ✗ Perth Mint sell error: {e}")
    return results


async def scrape_abc_sell(page):
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
                        wval, wunit = float(wm.group(1)), wm.group(2)
                        if wunit == "oz":   weight_oz = wval
                        elif wunit == "g":  weight_oz = wval / G_PER_OZ
                        elif wunit == "kg": weight_oz = wval * 32.1507
                if not weight_oz:
                    continue
                spot_est = SPOT_EST.get(metal, 100)
                if sell_price > spot_est * weight_oz * 1.5 or sell_price < spot_est * weight_oz * 0.5:
                    continue
                results.append({"dealer":"ABC Bullion","metal":metal,
                    "sell_price":sell_price,"weight_oz":round(weight_oz,4),
                    "category":"coin" if "coin" in name_l else "bar"})
                print(f"  ✓ ABC buyback {metal} {weight_oz:.4f}oz [{name[:30]}] @ A${sell_price:.2f}")
    except Exception as e:
        print(f"  ✗ ABC sell error: {e}")
    return results


async def scrape_guardian_sell(page):
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
            if len(texts) >= 1 and texts[0] in ["Gold","Silver","Platinum"]:
                current_metal = texts[0].lower()
                continue
            if current_metal and len(texts) >= 2:
                weight_str = texts[0].strip()
                price_str  = texts[-1].replace("$","").replace(",","").strip()
                wm = re.search(r"(\d+(?:\.\d+)?)(g|oz|KG|kg)", weight_str)
                if not wm:
                    continue
                wval, wunit = float(wm.group(1)), wm.group(2).lower()
                if wunit == "oz":   weight_oz = wval
                elif wunit == "kg": weight_oz = wval * 32.1507
                else:               weight_oz = wval / G_PER_OZ
                try:
                    sell_price = float(price_str)
                    if sell_price > 0:
                        results.append({"dealer":"Guardian Gold","metal":current_metal,
                            "sell_price":sell_price,"weight_oz":round(weight_oz,4),"category":"bar"})
                        print(f"  ✓ Guardian buyback {current_metal} {weight_oz:.2f}oz @ A${sell_price:.2f}")
                except:
                    pass
    except Exception as e:
        print(f"  ✗ Guardian sell error: {e}")
    return results


async def scrape_jaggards_sell(page):
    results = []
    FRAC_MAP = {"1/20":0.05,"1/10":0.1,"1/4":0.25,"1/2":0.5}
    try:
        await page.goto("https://www.jaggards.com.au/sell-to-us/",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)
        rows = await page.query_selector_all("table tr")
        current_metal = "gold"
        for row in rows:
            cells = await row.query_selector_all("td")
            if len(cells) < 2:
                header = await row.query_selector("th, td")
                if header:
                    txt = (await header.inner_text()).lower()
                    if "silver" in txt:   current_metal = "silver"
                    elif "gold" in txt:   current_metal = "gold"
                continue
            name      = (await cells[0].inner_text()).strip()
            price_str = (await cells[-1].inner_text()).strip().replace("$","").replace(",","")
            try:
                price = float(price_str)
            except:
                continue
            if price <= 0:
                continue
            wm = re.search(r"(1/20|1/10|1/4|1/2|\d+(?:\.\d+)?)(oz|g|kg)", name.lower())
            if not wm:
                continue
            wstr, wunit = wm.group(1), wm.group(2)
            wval = FRAC_MAP.get(wstr, float(wstr) if wstr not in FRAC_MAP else 0)
            if wunit == "oz":   weight_oz = wval
            elif wunit == "kg": weight_oz = wval * 32.1507
            else:               weight_oz = wval / G_PER_OZ
            results.append({"dealer":"Jaggards","metal":current_metal,
                "sell_price":price,"weight_oz":round(weight_oz,4),"category":"bar",
                "status":"OK","scraped_at":datetime.now(timezone.utc).isoformat()})
            print(f"  ✓ Jaggards buyback {current_metal} {weight_oz:.4f}oz @ A${price:.2f}")
    except Exception as e:
        print(f"  ✗ Jaggards sell error: {e}")
    return results


async def scrape_bullion_now_sell(page):
    results = []
    try:
        await page.goto("https://bullionnow.com.au/sell-my-bullion/",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(8000)
        frame = next((f for f in page.frames if "nfusionsolutions" in f.url and "table" in f.url), None)
        if not frame:
            print("  ⚠  Bullion Now iframe not found")
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
            if metal_txt not in ["gold","silver","platinum"]:
                continue
            try:
                price = float(price_str)
                if price > 0:
                    results.append({"dealer":"Bullion Now","metal":metal_txt,
                        "sell_price":price,"weight_oz":1.0,"category":"bar",
                        "status":"OK","scraped_at":datetime.now(timezone.utc).isoformat()})
                    print(f"  ✓ Bullion Now buyback {metal_txt} 1oz @ A${price:.2f}")
            except:
                pass
    except Exception as e:
        print(f"  ✗ Bullion Now sell error: {e}")
    return results


async def scrape_melbourne_gold_sell(page):
    results = []
    try:
        await page.goto("https://www.melbournegoldcompany.com.au/gold-buyers-melbourne.html",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)
        items = await page.query_selector_all("li")
        for item in items:
            txt   = (await item.inner_text()).strip()
            lines = [l.strip() for l in txt.split("\n") if l.strip()]
            if len(lines) < 2:
                continue
            name = lines[0]
            if not re.search(r"(oz|kg|gram).*(gold|silver)", name.lower()) and \
               not re.search(r"(gold|silver).*(oz|g|kg)", name.lower()):
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
            wm = re.search(r"(\d+(?:\.\d+)?)\s*(oz|g\b|kg)", name.lower())
            if wm:
                wval, wunit = float(wm.group(1)), wm.group(2).strip()
                if wunit == "oz":   weight_oz = wval
                elif wunit == "g":  weight_oz = wval / G_PER_OZ
                elif wunit == "kg": weight_oz = wval * 32.1507
            if not weight_oz:
                continue
            results.append({"dealer":"Melbourne Gold Company","metal":metal,
                "sell_price":price,"weight_oz":round(weight_oz,4),"category":"bar",
                "status":"OK","scraped_at":datetime.now(timezone.utc).isoformat()})
            print(f"  ✓ Melbourne Gold buyback {metal} {weight_oz:.4f}oz @ A${price:.2f}")
    except Exception as e:
        print(f"  ✗ Melbourne Gold sell error: {e}")
    return results


async def scrape_imperial_sell(page):
    results = []
    FRAC = {"1/20oz":0.05,"1/10oz":0.1,"1/4oz":0.25,"1/2oz":0.5}
    try:
        await page.goto("https://imperialbullion.com.au/sell-prices/",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(6000)
        current_metal = "gold"
        elements = await page.query_selector_all("h3, li")
        for el in elements:
            tag = await el.evaluate("e => e.tagName.toLowerCase()")
            if tag == "h3":
                heading = (await el.inner_text()).strip().lower()
                if "silver" in heading:   current_metal = "silver"
                elif "gold" in heading:   current_metal = "gold"
                continue
            title_el = await el.query_selector("span.title")
            meta_el  = await el.query_selector("span.meta")
            if not title_el or not meta_el:
                continue
            name = (await title_el.inner_text()).strip()
            if any(x in name.lower() for x in ["ct gold","sovereign","$200","half sov"]):
                continue
            if await meta_el.query_selector("img"):
                continue
            price_str = (await meta_el.inner_text()).strip().replace("$","").replace(",","")
            try:
                price = float(price_str)
            except:
                continue
            if price <= 0:
                continue
            name_l    = name.lower().strip()
            weight_oz = None
            for frac, oz in FRAC.items():
                if frac in name_l.replace(" ",""):
                    weight_oz = oz
                    break
            if not weight_oz:
                wm = re.search(r"(\d+(?:\.\d+)?)\s*(oz|g\b|kg|kilo)", name_l)
                if wm:
                    wval, wunit = float(wm.group(1)), wm.group(2)
                    if wunit == "oz":            weight_oz = wval
                    elif wunit == "g":           weight_oz = wval / G_PER_OZ
                    elif wunit in ["kg","kilo"]: weight_oz = wval * 32.1507
            if not weight_oz:
                continue
            spot_est = SPOT_EST.get(current_metal, 100)
            if price > spot_est * weight_oz * 1.5 or price < spot_est * weight_oz * 0.5:
                continue
            results.append({"dealer":"Imperial Bullion","metal":current_metal,
                "sell_price":price,"weight_oz":round(weight_oz,4),
                "category":"coin" if "coin" in name_l or "lunar" in name_l else "bar",
                "status":"OK","scraped_at":datetime.now(timezone.utc).isoformat()})
            print(f"  ✓ Imperial buyback {current_metal} {weight_oz:.4f}oz [{name[:25]}] @ A${price:.2f}")
    except Exception as e:
        print(f"  ✗ Imperial sell error: {e}")
    return results


# ── CATALOGUE ─────────────────────────────────────────────────────────────────
# Structure per product:
#   "Product Name": {
#     metal, category, coin_type|bar_brand, bar_type, weight_oz|weight_g,
#     min_aud, max_aud,
#     dealers: [{dealer, url, wait?, networkidle?, min_val?, max_val?}]
#   }
# Note: URLs marked # TODO need to be verified/found before use

CATALOGUE = {

    # ══════════════════════════════════════════════════════════════════════════
    # GOLD COINS — Kangaroo (all sizes)
    # ══════════════════════════════════════════════════════════════════════════

    "Gold Kangaroo 1oz": {
        "metal":"gold","category":"coin","coin_type":"Kangaroo",
        "weight_oz":1.0,"min_aud":5500,"max_aud":10000,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-australian-kangaroo-gold-bullion-coin/3003878"},
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/bullion-coins/australian-kangaroo-2026-1oz-gold-bullion-coin/", "wait":8000},
            {"dealer":"ABC Bullion",     "url":"https://www.abcbullion.com.au/store/Bullion-Coins/gn011oz-perth-mint-kangaroo-gold-coin-9999", "networkidle":True, "min_val":5500},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Gold-Coin-2026-Kangaroo-Perth-Mint/ID/673"},
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/australian-kangaroo-2026-1-oz-gold-bullion-coin/"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/2026-1oz-perth-mint-gold-kangaroo-coin/"},
            {"dealer":"Swan Bullion",    "url":"https://swanbullion.com/2026-australian-kangaroo-1oz-gold-coin/"},
            {"dealer":"Guardian Gold",   "url":"https://guardian-gold.com.au/product/1oz-gold-kang-coin-2026/", "wait":8000},
        ],
    },

    "Gold Kangaroo 0.5oz": {
        "metal":"gold","category":"coin","coin_type":"Kangaroo",
        "weight_oz":0.5,"min_aud":2800,"max_aud":5500,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/1-2-oz-2026-australian-kangaroo-gold-bullion-coin/3003875", "wait":7000},
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/bullion-coins/australian-kangaroo-2026-1-2oz-gold-bullion-coin/", "wait":8000},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1-2oz-Gold-Coin-2026-Kangaroo-Perth-Mint/ID/674"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/2026-1-2oz-perth-mint-gold-kangaroo-coin/"},
            {"dealer":"Swan Bullion",    "url":"https://swanbullion.com/2026-australian-kangaroo-half-oz-gold-coin/"},
        ],
    },

    "Gold Kangaroo 0.25oz": {
        "metal":"gold","category":"coin","coin_type":"Kangaroo",
        "weight_oz":0.25,"min_aud":1400,"max_aud":3000,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/1-4-oz-2026-australian-kangaroo-gold-bullion-coin/3003874"},
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/bullion-coins/australian-kangaroo-2026-1-4oz-gold-bullion-coin/", "wait":8000},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1-4oz-Gold-Coin-2026-Kangaroo-Perth-Mint/ID/675"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/2026-1-4oz-perth-mint-gold-kangaroo-coin/"},
        ],
    },

    "Gold Kangaroo 0.1oz": {
        "metal":"gold","category":"coin","coin_type":"Kangaroo",
        "weight_oz":0.1,"min_aud":550,"max_aud":1400,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/1-10-oz-2026-australian-kangaroo-gold-bullion-coin/3003873"},
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/bullion-coins/australian-kangaroo-2026-1-10oz-gold-bullion-coin/", "wait":8000},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1-10oz-Gold-Coin-2026-Kangaroo-Perth-Mint/ID/676"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/2026-1-10oz-perth-mint-gold-kangaroo-coin/"},
            {"dealer":"Swan Bullion",    "url":"https://swanbullion.com/2026-australian-kangaroo-1-10oz-gold-coin/"},
        ],
    },

    "Gold Kangaroo 0.05oz": {
        "metal":"gold","category":"coin","coin_type":"Kangaroo",
        "weight_oz":0.05,"min_aud":270,"max_aud":700,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/1-20-oz-2026-australian-kangaroo-gold-bullion-coin/3003872"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/2026-1-20oz-perth-mint-gold-kangaroo-coin/"},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # GOLD COINS — International 1oz
    # ══════════════════════════════════════════════════════════════════════════

    "Gold Maple Leaf 1oz": {
        "metal":"gold","category":"coin","coin_type":"Maple Leaf",
        "weight_oz":1.0,"min_aud":5500,"max_aud":10000,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-canadian-maple-leaf-gold-bullion-coin/3003907"},
            {"dealer":"ABC Bullion",     "url":"https://www.abcbullion.com.au/store/Bullion-Coins/gml011oz-maple-leaf-gold-coin-9999", "networkidle":True, "min_val":5500},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Maple-Leaf-Gold-Coin/ID/37"},
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/buy/gold/all-1oz/", "min_val":6500},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/1oz-canadian-gold-maple-leaf-coin/"},
            {"dealer":"Guardian Gold",   "url":"https://guardian-gold.com.au/product/1oz-gold-maple-leaf-coin-2023/"},
        ],
    },

    "Gold Krugerrand 1oz": {
        "metal":"gold","category":"coin","coin_type":"Krugerrand",
        "weight_oz":1.0,"min_aud":5500,"max_aud":10000,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-south-africa-krugerrand-gold-bullion-coin--mixed-dates/2207805"},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/buy/view/product/name/krugerand-gold-coin-incl-gst-/id/51"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/1oz-south-african-gold-krugerrand/"},
            {"dealer":"Swan Bullion",    "url":"https://swanbullion.com/product/south-african-krugerrand-1oz-gold-coin-random-year"},
        ],
    },

    "Gold Britannia 1oz": {
        "metal":"gold","category":"coin","coin_type":"Britannia",
        "weight_oz":1.0,"min_aud":5500,"max_aud":10000,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2024-britannia-gold-bullion-coin/3003321"},
            {"dealer":"ABC Bullion",     "url":"https://www.abcbullion.com.au/store/Bullion-Coins/royal-mint/gbritc01cor1oz-the-royal-mint-coronation-britannia-coin-9999", "networkidle":True, "min_val":6700},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/2023-1oz-great-britain-britannia-gold-coin-king-charles"},
        ],
    },

    "Gold Philharmonic 1oz": {
        "metal":"gold","category":"coin","coin_type":"Philharmonic",
        "weight_oz":1.0,"min_aud":5500,"max_aud":10000,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-austrian-philharmonic-gold-bullion-coin/3003909"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/1oz-gold-austrian-philharmonic-coin/"},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # SILVER COINS — 1oz
    # ══════════════════════════════════════════════════════════════════════════

    "Silver Kangaroo 1oz": {
        "metal":"silver","category":"coin","coin_type":"Kangaroo",
        "weight_oz":1.0,"min_aud":95,"max_aud":250,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-australian-kangaroo-silver-bullion-coin/3003876"},
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/bullion-coins/australian-kangaroo-2026-1oz-silver-bullion-coin-in-pouch/", "wait":8000},
            {"dealer":"ABC Bullion",     "url":"https://www.abcbullion.com.au/store/skangc011oz-silver-kangaroo-coin", "networkidle":True},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Silver-Coin-2026-Kangaroo-Perth-Mint/ID/677"},
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/perth-mint-2026-kangaroo-silver-coin-1-oz/"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/2026-1oz-perth-mint-silver-kangaroo-coin/"},
            {"dealer":"Swan Bullion",    "url":"https://swanbullion.com/2026-australian-kangaroo-1oz-silver-coin/"},
            {"dealer":"Guardian Gold",   "url":"https://guardian-gold.com.au/product/1oz-silver-kangaroo-coin-2026/"},
        ],
    },

    "Silver Kookaburra 1oz": {
        "metal":"silver","category":"coin","coin_type":"Kookaburra",
        "weight_oz":1.0,"min_aud":95,"max_aud":250,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-australian-kookaburra-silver-bullion-coin/3003879"},
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/bullion-coins/australian-kookaburra-2026-1oz-silver-bullion-coin/", "wait":8000},
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/australian-kookaburra-2026-1oz-silver-bullion-coin/"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/2026-kookaburra-1oz-silver-coin/"},
            {"dealer":"Swan Bullion",    "url":"https://swanbullion.com/2026-kookaburra-1oz-silver-coin/"},
            {"dealer":"Guardian Gold",   "url":"https://guardian-gold.com.au/product/1oz-silver-kookaburra-coin-2026/", "wait":8000},
        ],
    },

    "Silver Maple Leaf 1oz": {
        "metal":"silver","category":"coin","coin_type":"Maple Leaf",
        "weight_oz":1.0,"min_aud":95,"max_aud":250,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-canadian-maple-leaf-silver-bullion-coin/3003908"},
            {"dealer":"ABC Bullion",     "url":"https://www.abcbullion.com.au/store/Bullion-Coins/Royal-Canadian-Mint/sml011oz-silver-maple-coin-9999", "networkidle":True},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Silver-Maple-Leaf-2026/ID/679"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/2026-maple-leaf-1oz-silver-coin/"},
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/rcm-silver-maple-leaf-coin-1oz/"},
            {"dealer":"Swan Bullion",    "url":"https://swanbullion.com/2026-canadian-maple-leaf-1oz-silver-coin/"},
        ],
    },

    "Silver Britannia 1oz": {
        "metal":"silver","category":"coin","coin_type":"Britannia",
        "weight_oz":1.0,"min_aud":95,"max_aud":250,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-silver-britannia-coin/3003910"},
            {"dealer":"ABC Bullion",     "url":"https://www.abcbullion.com.au/store/Bullion-Coins/royal-mint", "networkidle":True, "min_val":95},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Silver-Britannia-2026/ID/680"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/2026-1oz-britannia-silver-coin/"},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # GOLD BARS — Perth Mint Minted (gram weights)
    # ══════════════════════════════════════════════════════════════════════════

    "Gold Bar Perth Mint 1g": {
        "metal":"gold","category":"bar","bar_brand":"Perth Mint","bar_type":"minted",
        "weight_g":1.0,"weight_oz":0.0322,"min_aud":180,"max_aud":500,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/1-g-perth-mint-gold-bullion-minted-bar/2417"},
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/minted-bars/kangaroo-1g-minted-gold-bar/", "wait":8000},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1g-Minted-Gold-Bar-Perth-Mint/ID/25"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/1g-perth-mint-gold-minted-bar/"},
            {"dealer":"Swan Bullion",    "url":"https://swanbullion.com/perth-mint-1g-gold-minted-bar/"},
            {"dealer":"Guardian Gold",   "url":"https://guardian-gold.com.au/product/1g-perth-mint-gold-minted-bar/"},
        ],
    },

    "Gold Bar Perth Mint 5g": {
        "metal":"gold","category":"bar","bar_brand":"Perth Mint","bar_type":"minted",
        "weight_g":5.0,"weight_oz":0.1608,"min_aud":900,"max_aud":2500,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/5-g-perth-mint-gold-bullion-minted-bar/2418", "wait":7000},
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/minted-bars/kangaroo-5g-minted-gold-bar/", "wait":8000},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/5g-Minted-Gold-Bar-Perth-Mint/ID/26"},
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/perth-mint-kangaroo-gold-bar-5g/"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/5g-perth-mint-gold-minted-bar/"},
            {"dealer":"Swan Bullion",    "url":"https://swanbullion.com/perth-mint-5g-gold-minted-bar/"},
        ],
    },

    "Gold Bar Perth Mint 10g": {
        "metal":"gold","category":"bar","bar_brand":"Perth Mint","bar_type":"minted",
        "weight_g":10.0,"weight_oz":0.3215,"min_aud":1800,"max_aud":4500,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/10-g-perth-mint-gold-bullion-minted-bar/2419", "wait":7000},
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/minted-bars/kangaroo-10g-minted-gold-bar/", "wait":8000},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/10g-Minted-Gold-Bar-Perth-Mint/ID/27"},
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/perth-mint-kangaroo-gold-bar-10g/"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/10g-perth-mint-gold-minted-bar/"},
            {"dealer":"Swan Bullion",    "url":"https://swanbullion.com/perth-mint-10g-gold-minted-bar/"},
        ],
    },

    "Gold Bar Perth Mint 20g": {
        "metal":"gold","category":"bar","bar_brand":"Perth Mint","bar_type":"minted",
        "weight_g":20.0,"weight_oz":0.6430,"min_aud":3500,"max_aud":8000,
        "dealers":[
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/perth-mint-kangaroo-gold-bar-20g/"},
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/minted-bars/kangaroo-20g-minted-gold-bar/", "wait":8000},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/20g-Minted-Gold-Bar-Perth-Mint/ID/28"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/20g-perth-mint-gold-minted-bar/"},
            {"dealer":"Swan Bullion",    "url":"https://swanbullion.com/perth-mint-20g-gold-minted-bar/"},
        ],
    },

    "Gold Bar Perth Mint 50g": {
        "metal":"gold","category":"bar","bar_brand":"Perth Mint","bar_type":"minted",
        "weight_g":50.0,"weight_oz":1.6075,"min_aud":9000,"max_aud":18000,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/50-g-perth-mint-gold-bullion-minted-bar/2421"},
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/minted-bars/kangaroo-50g-minted-gold-bar/", "wait":8000},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/50g-Minted-Gold-Bar-Perth-Mint/ID/242"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/50g-perth-mint-gold-minted-bar/"},
            {"dealer":"Swan Bullion",    "url":"https://swanbullion.com/perth-mint-50g-gold-minted-bar/"},
        ],
    },

    "Gold Bar Perth Mint 100g": {
        "metal":"gold","category":"bar","bar_brand":"Perth Mint","bar_type":"minted",
        "weight_g":100.0,"weight_oz":3.2151,"min_aud":18000,"max_aud":36000,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/100-g-perth-mint-gold-bullion-minted-bar/2422"},
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/minted-bars/kangaroo-100g-minted-gold-bar/", "wait":8000},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/100g-Minted-Gold-Bar-Perth-Mint/ID/30"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/100g-perth-mint-gold-minted-bar/"},
            {"dealer":"Swan Bullion",    "url":"https://swanbullion.com/perth-mint-100g-gold-minted-bar/"},
            {"dealer":"Guardian Gold",   "url":"https://guardian-gold.com.au/product/100g-perth-mint-gold-minted-bar/"},
        ],
    },

    "Gold Bar Perth Mint 1oz Minted": {
        "metal":"gold","category":"bar","bar_brand":"Perth Mint","bar_type":"minted",
        "weight_oz":1.0,"min_aud":5500,"max_aud":9500,
        "dealers":[
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/perth-mint-kangaroo-gold-bar-1-oz/"},
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/minted-bars/kangaroo-1oz-minted-gold-bar/", "wait":8000},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Minted-Gold-Bar-Perth-Mint/ID/31"},
            {"dealer":"Swan Bullion",    "url":"https://swanbullion.com/perth-mint-1oz-gold-minted-bar/"},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # GOLD BARS — Perth Mint Cast (oz weights)
    # ══════════════════════════════════════════════════════════════════════════

    "Gold Bar Perth Mint 0.5oz Cast": {
        "metal":"gold","category":"bar","bar_brand":"Perth Mint","bar_type":"cast",
        "weight_oz":0.5,"min_aud":2800,"max_aud":5500,
        "dealers":[
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/half-oz-perth-mint-gold-cast-bar/"},
            {"dealer":"Guardian Gold",   "url":"https://guardian-gold.com.au/product/1-2-oz-gold-cast/"},
        ],
    },

    "Gold Bar Perth Mint 1oz Cast": {
        "metal":"gold","category":"bar","bar_brand":"Perth Mint","bar_type":"cast",
        "weight_oz":1.0,"min_aud":5500,"max_aud":9500,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/CT/perth-mint-gold-bars-1oz-gold/220241/1"},
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/cast-bars/perth-mint-1oz-gold-cast-bar/", "wait":8000},
            {"dealer":"ABC Bullion",     "url":"https://www.abcbullion.com.au/store/gold/gabg011oz-abc-gold-cast-bar-9999", "networkidle":True, "min_val":5500},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Perth-Mint-Gold-Cast-Bar/ID/32"},
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/the-perth-mint-1oz-gold-cast-bar/"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/1oz-perth-mint-gold-minted-bar/"},
            {"dealer":"Swan Bullion",    "url":"https://swanbullion.com/perth-mint-1oz-gold-minted-bar/"},
            {"dealer":"Guardian Gold",   "url":"https://guardian-gold.com.au/product/1oz-perth-mint-gold-cast-bar/", "wait":8000},
        ],
    },

    "Gold Bar Perth Mint 5oz Cast": {
        "metal":"gold","category":"bar","bar_brand":"Perth Mint","bar_type":"cast",
        "weight_oz":5.0,"min_aud":27000,"max_aud":45000,
        "dealers":[
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/cast-bars/perth-mint-5-oz-gold-cast-bar/", "wait":8000},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/5oz-Perth-Mint-Gold-Cast-Bar/ID/35"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/5oz-perth-mint-gold-cast-bar/"},
        ],
    },

    "Gold Bar Perth Mint 10oz Cast": {
        "metal":"gold","category":"bar","bar_brand":"Perth Mint","bar_type":"cast",
        "weight_oz":10.0,"min_aud":55000,"max_aud":90000,
        "dealers":[
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/cast-bars/perth-mint-10oz-gold-cast-bar/", "wait":8000},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/10oz-Perth-Mint-Gold-Cast-Bar/ID/36"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/10oz-perth-mint-gold-cast-bar/"},
        ],
    },

    "Gold Bar Perth Mint 1kg Cast": {
        "metal":"gold","category":"bar","bar_brand":"Perth Mint","bar_type":"cast",
        "weight_oz":32.1507,"min_aud":185000,"max_aud":280000,
        "dealers":[

        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # GOLD BARS — ABC Bullion Cast
    # ══════════════════════════════════════════════════════════════════════════

    "Gold Bar ABC 1oz Cast": {
        "metal":"gold","category":"bar","bar_brand":"ABC Bullion","bar_type":"cast",
        "weight_oz":1.0,"min_aud":5500,"max_aud":9500,
        "dealers":[
            {"dealer":"ABC Bullion",     "url":"https://www.abcbullion.com.au/store/gold/gabg011oz-abc-gold-cast-bar-9999", "networkidle":True, "min_val":5500},
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-abc-bullion-gold-cast-bar/3001001"},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-ABC-Bullion-Gold-Cast-Bar/ID/39"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/1oz-abc-bullion-gold-cast-bar/"},
        ],
    },

    "Gold Bar ABC 5oz Cast": {
        "metal":"gold","category":"bar","bar_brand":"ABC Bullion","bar_type":"cast",
        "weight_oz":5.0,"min_aud":27000,"max_aud":45000,
        "dealers":[
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/5oz-ABC-Gold-Cast-Bar/ID/40"},
        ],
    },

    "Gold Bar ABC 10oz Cast": {
        "metal":"gold","category":"bar","bar_brand":"ABC Bullion","bar_type":"cast",
        "weight_oz":10.0,"min_aud":55000,"max_aud":90000,
        "dealers":[
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/10oz-ABC-Gold-Cast-Bar/ID/41"},
        ],
    },

    "Gold Bar ABC 1kg Cast": {
        "metal":"gold","category":"bar","bar_brand":"ABC Bullion","bar_type":"cast",
        "weight_oz":32.1507,"min_aud":185000,"max_aud":280000,
        "dealers":[
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1kg-ABC-Gold-Cast-Bar/ID/42"},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # GOLD BARS — Generic Minted (unbranded / GBA / assorted mint)
    # ══════════════════════════════════════════════════════════════════════════

    "Gold Bar Generic 0.5oz Minted": {
        "metal":"gold","category":"bar","bar_brand":"Generic","bar_type":"minted",
        "weight_oz":0.5,"min_aud":2800,"max_aud":5500,
        "dealers":[
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/gba-gold-1-2-oz/"},
        ],
    },

    "Gold Bar Generic 1oz Minted": {
        "metal":"gold","category":"bar","bar_brand":"Generic","bar_type":"minted",
        "weight_oz":1.0,"min_aud":5500,"max_aud":9500,
        "dealers":[
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/generic-gold-1oz/"},
        ],
    },

    "Gold Bar Generic 5oz Minted": {
        "metal":"gold","category":"bar","bar_brand":"Generic","bar_type":"minted",
        "weight_oz":5.0,"min_aud":27000,"max_aud":45000,
        "dealers":[
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/gba-gold-5-oz/"},
        ],
    },

    "Gold Bar Generic 0.1oz Minted": {
        "metal":"gold","category":"bar","bar_brand":"Generic","bar_type":"minted",
        "weight_oz":0.1,"min_aud":550,"max_aud":1400,
        "dealers":[],
    },

    "Gold Bar Generic 0.25oz Minted": {
        "metal":"gold","category":"bar","bar_brand":"Generic","bar_type":"minted",
        "weight_oz":0.25,"min_aud":1400,"max_aud":3000,
        "dealers":[],
    },

    "Gold Bar Generic 2oz Minted": {
        "metal":"gold","category":"bar","bar_brand":"Generic","bar_type":"minted",
        "weight_oz":2.0,"min_aud":11000,"max_aud":19000,
        "dealers":[
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/generic-gold-2oz/"},
        ],
    },

    "Gold Bar Generic 10oz Minted": {
        "metal":"gold","category":"bar","bar_brand":"Generic","bar_type":"minted",
        "weight_oz":10.0,"min_aud":55000,"max_aud":90000,
        "dealers":[],
    },

    "Gold Bar Generic 1kg Minted": {
        "metal":"gold","category":"bar","bar_brand":"Generic","bar_type":"minted",
        "weight_oz":32.1507,"min_aud":185000,"max_aud":280000,
        "dealers":[
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/generic-gold-1kg/"},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # SILVER BARS — Perth Mint Cast
    # ══════════════════════════════════════════════════════════════════════════

    "Silver Bar Perth Mint 1oz Cast": {
        "metal":"silver","category":"bar","bar_brand":"Perth Mint","bar_type":"cast",
        "weight_oz":1.0,"min_aud":90,"max_aud":200,
        "dealers":[
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Perth-Mint-Silver-Cast-Bar/ID/60"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/1oz-perth-mint-silver-cast-bar/"},
        ],
    },

    "Silver Bar Perth Mint 10oz Cast": {
        "metal":"silver","category":"bar","bar_brand":"Perth Mint","bar_type":"cast",
        "weight_oz":10.0,"min_aud":850,"max_aud":1600,
        "dealers":[
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/10oz-Perth-Mint-Silver-Cast-Bar/ID/61"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/10oz-perth-mint-silver-cast-bar/"},
        ],
    },

    "Silver Bar Perth Mint 1kg Cast": {
        "metal":"silver","category":"bar","bar_brand":"Perth Mint","bar_type":"cast",
        "weight_oz":32.1507,"min_aud":2800,"max_aud":5000,
        "dealers":[
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/cast-bars/perth-mint-1-kilo-silver-cast-bar/", "wait":8000},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1kg-Perth-Mint-Silver-Cast-Bar/ID/62"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/1kg-perth-mint-silver-cast-bar/"},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # SILVER BARS — ABC Bullion Cast
    # ══════════════════════════════════════════════════════════════════════════

    "Silver Bar ABC 1oz Cast": {
        "metal":"silver","category":"bar","bar_brand":"ABC Bullion","bar_type":"cast",
        "weight_oz":1.0,"min_aud":90,"max_aud":200,
        "dealers":[
            {"dealer":"ABC Bullion",     "url":"https://www.abcbullion.com.au/store/silver/sabg011oz-abc-silver-cast-bar-9995", "networkidle":True},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-ABC-Silver-Cast-Bar/ID/65"},
        ],
    },

    "Silver Bar ABC 10oz Cast": {
        "metal":"silver","category":"bar","bar_brand":"ABC Bullion","bar_type":"cast",
        "weight_oz":10.0,"min_aud":850,"max_aud":1600,
        "dealers":[
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/10oz-ABC-Silver-Cast-Bar/ID/66"},
        ],
    },

    "Silver Bar ABC 1kg Cast": {
        "metal":"silver","category":"bar","bar_brand":"ABC Bullion","bar_type":"cast",
        "weight_oz":32.1507,"min_aud":2800,"max_aud":5000,
        "dealers":[
            {"dealer":"ABC Bullion",     "url":"https://www.abcbullion.com.au/store/silver/sabg011kg-abc-silver-cast-bar-9995", "networkidle":True, "wait":8000},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1kg-ABC-Silver-Cast-Bar/ID/67"},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # SILVER BARS — Generic
    # ══════════════════════════════════════════════════════════════════════════

    "Silver Bar Generic 1oz": {
        "metal":"silver","category":"bar","bar_brand":"Generic","bar_type":"cast",
        "weight_oz":1.0,"min_aud":90,"max_aud":200,
        "dealers":[],
    },

    "Silver Bar Generic 5oz": {
        "metal":"silver","category":"bar","bar_brand":"Generic","bar_type":"cast",
        "weight_oz":5.0,"min_aud":450,"max_aud":900,
        "dealers":[
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/gba-silver-5oz/"},
        ],
    },

    "Silver Bar Generic 10oz": {
        "metal":"silver","category":"bar","bar_brand":"Generic","bar_type":"cast",
        "weight_oz":10.0,"min_aud":850,"max_aud":1600,
        "dealers":[
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/generic-silver-10oz/"},
        ],
    },

    "Silver Bar Generic 1kg": {
        "metal":"silver","category":"bar","bar_brand":"Generic","bar_type":"cast",
        "weight_oz":32.1507,"min_aud":2800,"max_aud":5000,
        "dealers":[
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/generic-silver-1kg/"},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # BUYBACK — pre-owned, secondary market (lower price tier)
    # ══════════════════════════════════════════════════════════════════════════

    "Gold Buyback 1oz Minted": {
        "metal":"gold","category":"bar","bar_brand":"Generic","bar_type":"buyback",
        "weight_oz":1.0,"min_aud":5000,"max_aud":9000,
        "dealers":[
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/buyback-gold-minted-bars-1-oz/"},
        ],
    },

    "Silver Buyback 1oz Bar": {
        "metal":"silver","category":"bar","bar_brand":"Generic","bar_type":"buyback",
        "weight_oz":1.0,"min_aud":80,"max_aud":180,
        "dealers":[
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/buyback-silver-bar-1-oz/"},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # LUNAR — Silver + Gold (Perth Mint annual series, 2026 Year of the Horse)
    # ══════════════════════════════════════════════════════════════════════════

    "Silver Lunar 1oz": {
        "metal":"silver","category":"coin","coin_type":"Lunar",
        "weight_oz":1.0,"min_aud":95,"max_aud":250,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-australian-year-of-the-horse-silver-bullion-coin/3003811"},
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/bullion-coins/australian-lunar-series-iii-2026-year-of-the-horse-1oz-silver-bullion-coin/", "wait":8000},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Silver-Coin-2026-Year-of-the-Horse-Perth-Mint/ID/637"},
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/perth-mint-2026-lunar-horse-silver-coin-1-oz/"},
        ],
    },

    "Gold Lunar 1oz": {
        "metal":"gold","category":"coin","coin_type":"Lunar",
        "weight_oz":1.0,"min_aud":5500,"max_aud":10000,
        "dealers":[
            {"dealer":"KJC Bullion",     "url":"https://www.kjc-gold-silver-bullion.com.au/PD/1-oz-2026-australian-year-of-the-horse-gold-bullion-coin/3003807"},
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/bullion-coins/Australian-Lunar-Series-III-2026-Year-of-the-Horse-1oz-Gold-Bullion-Coin/", "wait":8000},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/1oz-Gold-Coin-2026-Year-of-the-Horse-Perth-Mint/ID/644"},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # KOALA — Silver (Perth Mint, releasing 6 May 2026 — verify URLs before first scrape)
    # ══════════════════════════════════════════════════════════════════════════

    "Silver Koala 1oz": {
        "metal":"silver","category":"coin","coin_type":"Koala",
        "weight_oz":1.0,"min_aud":95,"max_aud":250,
        "dealers":[
            {"dealer":"Perth Mint",      "url":"https://www.perthmint.com/shop/bullion/bullion-coins/australian-koala-2026-1oz-silver-bullion-coin/", "wait":8000},
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/perth-mint-2026-koala-silver-coin-1-oz/"},
            {"dealer":"Jaggards",        "url":"https://www.jaggards.com.au/product/2026-1oz-perth-mint-silver-koala-coin/"},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # SILVER BARS — 100oz
    # ══════════════════════════════════════════════════════════════════════════

    "Silver Bar Generic 100oz": {
        "metal":"silver","category":"bar","bar_brand":"Generic","bar_type":"cast",
        "weight_oz":100.0,"min_aud":8500,"max_aud":16000,
        "dealers":[
            {"dealer":"Gold Stackers",   "url":"https://www.goldstackers.com.au/product/generic-silver-100oz/"},
            {"dealer":"Ainslie Bullion", "url":"https://ainsliebullion.com.au/Buy/View/Product/Name/100oz-Ainslie-Silver-Bullion/ID/95"},
        ],
    },

}

SELL_SCRAPERS = [
    (scrape_perth_mint_sell,     "Perth Mint"),
    (scrape_abc_sell,            "ABC Bullion"),
    (scrape_guardian_sell,       "Guardian Gold"),
    (scrape_jaggards_sell,       "Jaggards"),
    (scrape_bullion_now_sell,    "Bullion Now"),
    (scrape_melbourne_gold_sell, "Melbourne Gold Company"),
    (scrape_imperial_sell,       "Imperial Bullion"),
]


# ── Jaggards buy scraper (category-page architecture) ─────────────────────────

JAGGARDS_CATEGORIES = [
    ("gold",   "coin", "https://www.jaggards.com.au/category/gold/gold-coins/"),
    ("gold",   "bar",  "https://www.jaggards.com.au/category/gold/gold-bars/"),
    ("silver", "coin", "https://www.jaggards.com.au/category/silver-coins/"),
    ("silver", "bar",  "https://www.jaggards.com.au/category/silver-bars/"),
]

SWAN_CATEGORIES = [
    ("gold",   "https://swanbullion.com/gold-bullion/"),
    ("silver", "https://swanbullion.com/silver-bullion/"),
]

_COIN_KW = {
    "Kangaroo":     ["kangaroo"],
    "Maple Leaf":   ["maple"],
    "Krugerrand":   ["krugerrand"],
    "Britannia":    ["britannia"],
    "Philharmonic": ["philharmonic"],
    "Kookaburra":   ["kookaburra"],
    "Lunar":        ["lunar"],
}

def _jag_parse_weight(title):
    t = title.lower()
    if re.search(r'\bhalf[\s-]*oz\b', t):
        return 0.5, None
    m = re.search(r'(\d+)/(\d+)\s*oz', t)
    if m:
        return round(int(m.group(1)) / int(m.group(2)), 6), None
    m = re.search(r'(\d+(?:\.\d+)?)\s*kg\b', t)
    if m:
        return round(float(m.group(1)) * 32.1507, 4), None
    m = re.search(r'(\d+(?:\.\d+)?)\s*g\b', t)
    if m:
        g = float(m.group(1))
        return round(g / 31.1035, 4), g
    m = re.search(r'(\d+(?:\.\d+)?)\s*oz\b', t)
    if m:
        return float(m.group(1)), None
    return None, None


def _jag_match(title, metal, category, catalogue, dealer="Jaggards"):
    t = title.lower()
    weight_oz, weight_g = _jag_parse_weight(title)
    for product_name, product_def in catalogue.items():
        if product_def.get("metal") != metal:
            continue
        if product_def.get("category") != category:
            continue
        if not any(d["dealer"] == dealer for d in product_def.get("dealers", [])):
            continue
        cat_woz = product_def.get("weight_oz")
        cat_wg  = product_def.get("weight_g")
        if weight_g is not None and cat_wg is not None:
            if abs(weight_g - cat_wg) > 0.1:
                continue
        elif weight_oz is not None and cat_woz is not None:
            if abs(weight_oz - cat_woz) > 0.01:
                continue
        else:
            continue
        if category == "coin":
            coin_type = product_def.get("coin_type", "")
            kws = _COIN_KW.get(coin_type, [coin_type.lower()])
            if not any(kw in t for kw in kws):
                continue
        else:
            bar_brand = (product_def.get("bar_brand") or "").lower()
            bar_type  = (product_def.get("bar_type")  or "").lower()
            if bar_brand and bar_brand != "generic":
                if not any(kw in t for kw in bar_brand.split()):
                    continue
            if bar_type in ("cast", "minted") and bar_type not in t:
                continue
        return product_name, product_def
    return None, None


async def scrape_jaggards_buy(page, catalogue):
    stats = {}
    for metal, category, base_url in JAGGARDS_CATEGORIES:
        page_num = 1
        while True:
            url = base_url if page_num == 1 else f"{base_url}page/{page_num}/"
            try:
                await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"  ✗ Jaggards {url}: {str(e)[:60]}")
                break
            items = await page.query_selector_all("li.product")
            if not items:
                break
            for item in items:
                try:
                    title_el = await item.query_selector("h2.woocommerce-loop-product__title")
                    price_el = await item.query_selector("span.price span.woocommerce-Price-amount bdi")
                    stock_el = await item.query_selector("span.badge-instock, span.badge-backorder, span.badge-instock-backorder")
                    if not title_el:
                        continue
                    title     = (await title_el.inner_text()).strip()
                    available = stock_el is not None
                    price     = None
                    if price_el:
                        raw = (await price_el.inner_text()).replace(",", "").replace("$", "").strip()
                        try:
                            price = float(re.sub(r'[^\d.]', '', raw))
                        except:
                            pass
                    product_name, product_def = _jag_match(title, metal, category, catalogue)
                    if not product_name:
                        continue
                    woz = product_def.get("weight_oz")
                    wg  = product_def.get("weight_g")
                    weight_str = f"{wg}g" if wg else f"{woz}oz"
                    link_el = await item.query_selector("a.woocommerce-loop-product__link")
                    jag_url = await link_el.get_attribute("href") if link_el else next((d["url"] for d in product_def.get("dealers", []) if d["dealer"] == "Jaggards"), None)
                    row = {
                        "dealer":     "Jaggards",
                        "metal":      metal,
                        "category":   category,
                        "coin_type":  product_def.get("coin_type"),
                        "bar_brand":  product_def.get("bar_brand"),
                        "bar_type":   product_def.get("bar_type"),
                        "weight_oz":  woz,
                        "weight_g":   wg,
                        "available":  available,
                        "status":     "OK",
                        "buy_url":    jag_url,
                        "scraped_at": datetime.now(timezone.utc).isoformat(),
                    }
                    avail_icon = "✓" if available else "✗"
                    if price and is_price_sane(metal, price, woz):
                        row["buy_price"] = price
                        db_ok = save_to_db(row)
                        tick   = "db✓" if db_ok else "db✗"
                        suffix = "  UNAVAIL" if not available else ""
                        key    = "unavailable" if not available else "ok"
                        print(f"  {avail_icon} Jaggards             {weight_str:8s} ${price:>10,.2f}  [{tick}{suffix}]")
                    elif not available:
                        patch_available(row, False)
                        key = "unavailable"
                        print(f"  ✗ Jaggards             {weight_str:8s} no price — marked unavailable")
                    else:
                        key = "no_price"
                        print(f"  ? Jaggards             {weight_str:8s} no price found")
                    stats[key] = stats.get(key, 0) + 1
                except Exception as e:
                    stats["error"] = stats.get("error", 0) + 1
            next_el = await page.query_selector("a.next.page-numbers")
            if not next_el:
                break
            page_num += 1
    return stats



async def scrape_swan_buy(page, catalogue):
    stats = {}
    for metal, base_url in SWAN_CATEGORIES:
        page_num = 1
        while True:
            url = base_url if page_num == 1 else f"{base_url}page/{page_num}/"
            try:
                await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"  ✗ Swan {url}: {str(e)[:60]}")
                break
            items = await page.query_selector_all("div.product")
            if not items:
                break
            for item in items:
                try:
                    title_el = await item.query_selector(".woocommerce-loop-product__title")
                    price_el = await item.query_selector("bdi")
                    if not title_el:
                        continue
                    title     = (await title_el.inner_text()).strip()
                    cls       = await item.get_attribute("class") or ""
                    available = "outofstock" not in cls
                    price     = None
                    if price_el:
                        raw = (await price_el.inner_text()).replace(",", "").replace("$", "").strip()
                        try:
                            price = float(re.sub(r'[^\d.]', '', raw))
                        except:
                            pass
                    product_name, product_def = _jag_match(title, metal, "coin", catalogue, "Swan Bullion")
                    if not product_name:
                        product_name, product_def = _jag_match(title, metal, "bar", catalogue, "Swan Bullion")
                    if not product_name:
                        continue
                    woz = product_def.get("weight_oz")
                    wg  = product_def.get("weight_g")
                    weight_str = f"{wg}g" if wg else f"{woz}oz"
                    swan_link_el = await item.query_selector("a.woocommerce-loop-product__link")
                    swan_url = await swan_link_el.get_attribute("href") if swan_link_el else next((d["url"] for d in product_def.get("dealers", []) if d["dealer"] == "Swan Bullion"), None)
                    row = {
                        "dealer":     "Swan Bullion",
                        "metal":      metal,
                        "category":   product_def["category"],
                        "coin_type":  product_def.get("coin_type"),
                        "bar_brand":  product_def.get("bar_brand"),
                        "bar_type":   product_def.get("bar_type"),
                        "weight_oz":  woz,
                        "weight_g":   wg,
                        "available":  available,
                        "status":     "OK",
                        "buy_url":    swan_url,
                        "scraped_at": datetime.now(timezone.utc).isoformat(),
                    }
                    avail_icon = "✓" if available else "✗"
                    if price and is_price_sane(metal, price, woz or (wg / 31.1035 if wg else None)):
                        row["buy_price"] = price
                        db_ok = save_to_db(row)
                        tick   = "db✓" if db_ok else "db✗"
                        suffix = "  UNAVAIL" if not available else ""
                        key    = "unavailable" if not available else "ok"
                        print(f"  {avail_icon} Swan Bullion           {weight_str:8s} ${price:>10,.2f}  [{tick}{suffix}]")
                    elif not available:
                        patch_available(row, False)
                        key = "unavailable"
                        print(f"  ✗ Swan Bullion           {weight_str:8s} no price — marked unavailable")
                    else:
                        key = "no_price"
                        print(f"  ? Swan Bullion           {weight_str:8s} no price found")
                    stats[key] = stats.get(key, 0) + 1
                except Exception as e:
                    stats["error"] = stats.get("error", 0) + 1
            next_el = await page.query_selector("a.next.page-numbers")
            if not next_el:
                break
            page_num += 1
    return stats

async def main():
    global DEBUG_DEALER, NO_SELL, NO_SAVE

    args = sys.argv[1:]
    if "--debug" in args:
        idx = args.index("--debug")
        DEBUG_DEALER = args[idx + 1] if idx + 1 < len(args) else None
    NO_SELL = "--no-sell" in args
    NO_SAVE = "--no-save" in args

    total_scrapes = sum(len(p["dealers"]) for p in CATALOGUE.values())

    print("=" * 65)
    print("  GoldSilverPrices.com.au — Scraper v3")
    print("=" * 65)
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if DEBUG_DEALER:
        print(f"  DEBUG: {DEBUG_DEALER}")
    else:
        print(f"  {len(CATALOGUE)} products · {total_scrapes} total scrapes")
    if NO_SAVE:
        print("  DRY RUN — no DB writes")
    print()

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

    stats = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-blink-features=AutomationControlled",
                  "--disable-web-security","--disable-downloads"]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            extra_http_headers={"Accept-Language": "en-AU,en;q=0.9"},
        )
        page = await context.new_page()

        # ── Buy prices ────────────────────────────────────────────────────────
        for product_name, product_def in CATALOGUE.items():
            dealers = product_def["dealers"]
            if DEBUG_DEALER:
                dealers = [d for d in dealers if d["dealer"] == DEBUG_DEALER]
                if not dealers:
                    continue

            weight_str = (f"{product_def['weight_oz']}oz" if product_def.get("weight_oz")
                          else f"{product_def['weight_g']}g")
            label = product_def.get("coin_type") or product_def.get("bar_brand") or "?"
            print(f"\n{'─'*65}")
            print(f"  {product_def['metal'].upper()} {product_def['category'].upper()}"
                  f" — {label} {weight_str}")
            print(f"{'─'*65}")

            for dealer_entry in dealers:
                if dealer_entry["dealer"] in ("Jaggards", "Swan Bullion"):
                    continue  # handled by category scrapers below
                result = await scrape_product(page, product_name, product_def, dealer_entry)
                stats[result] = stats.get(result, 0) + 1

        # ── Jaggards buy (category scrape) ────────────────────────────────────
        if not DEBUG_DEALER or DEBUG_DEALER == "Jaggards":
            print(f"\n{'─'*65}")
            print("  JAGGARDS — category scrape")
            print(f"{'─'*65}")
            jag_stats = await scrape_jaggards_buy(page, CATALOGUE)
            for k, v in jag_stats.items():
                stats[k] = stats.get(k, 0) + v

        # ── Swan Bullion buy (category scrape) ───────────────────────────────
        if not DEBUG_DEALER or DEBUG_DEALER == "Swan Bullion":
            print(f"\n{'─'*65}")
            print("  SWAN BULLION — category scrape")
            print(f"{'─'*65}")
            swan_stats = await scrape_swan_buy(page, CATALOGUE)
            for k, v in swan_stats.items():
                stats[k] = stats.get(k, 0) + v

        # ── Sell prices ───────────────────────────────────────────────────────
        if not NO_SELL:
            print(f"\n{'='*65}")
            print("  SELL PRICES")
            print(f"{'='*65}")
            sell_results = []
            for fn, name in SELL_SCRAPERS:
                if DEBUG_DEALER and name != DEBUG_DEALER:
                    continue
                print(f"\n  {name}")
                try:
                    res = await fn(page)
                    sell_results.extend(res)
                except Exception as e:
                    print(f"  ✗ {name}: {e}")
            if sell_results:
                save_sell_prices(sell_results)

        await browser.close()

    print(f"\n{'='*65}")
    print("  DONE")
    print(f"{'='*65}")
    print(f"  ✓ {stats.get('ok', 0)} prices saved")
    print(f"  ✗ {stats.get('unavailable', 0)} unavailable  (available=false in DB, auto-recovers)")
    print(f"  ? {stats.get('no_price', 0)} no price found")
    print(f"  ! {stats.get('error', 0)} errors")
    print(f"{'='*65}")


if __name__ == "__main__":
    asyncio.run(main())