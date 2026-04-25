import asyncio
import json
import urllib.request
import re
from playwright.async_api import async_playwright

# ── Fetch all URLs from Supabase ───────────────────────────────────────────
SUPABASE_URL = "https://cjxkhvkvhgnlnviykoad.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNqeGtodmt2aGdubG52aXlrb2FkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY1ODIyMDYsImV4cCI6MjA5MjE1ODIwNn0.eCg-JzEshidI-l7pVsumO_SsXbDOh_s--zvH1jc78g0"
DB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

def fetch_latest_prices():
    """Get most recent price per dealer+product from Supabase."""
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/prices?select=dealer,product,buy_price,url,status&order=scraped_at.desc&limit=200",
        headers=DB_HEADERS, method="GET",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())

    # Keep only most recent per dealer+product
    seen = set()
    latest = []
    for row in data:
        key = f"{row['dealer']}||{row['product']}"
        if key not in seen and row['status'] == 'OK':
            seen.add(key)
            latest.append(row)
    return latest


def looks_like_product_page(text, expected_price, url):
    """
    Returns (is_product_page, reason)
    Checks:
    1. Page contains a price close to the expected price
    2. Page doesn't show 'not found' or category signals
    """
    text_lower = text.lower()

    # Bad signals — category or error page
    bad_signals = [
        "not found", "page not found", "404",
        "sorry, but the page",
        "results for", "showing all",
        "filter by", "sort by",
        "add to cart\nadd to cart\nadd to cart",  # multiple products
    ]
    for signal in bad_signals:
        if signal in text_lower:
            return False, f"BAD SIGNAL: '{signal}'"

    # Check price is present on page
    if expected_price:
        price_str = f"{expected_price:,.2f}"
        price_str2 = f"{expected_price:.2f}"
        price_int = str(int(expected_price))
        if price_str in text or price_str2 in text or price_int in text:
            return True, "PRICE FOUND ON PAGE"

        # Check within 2% tolerance (price may have updated)
        matches = re.findall(r'[\d]{1,3}(?:,[\d]{3})*(?:\.\d{2})?', text)
        for m in matches:
            try:
                val = float(m.replace(",", ""))
                if abs(val - expected_price) / expected_price < 0.05:
                    return True, f"PRICE APPROX MATCH: {val}"
            except:
                pass

        return False, f"PRICE ${expected_price:,.2f} NOT FOUND ON PAGE"

    return True, "NO PRICE TO CHECK"


async def verify_url(page, row):
    dealer   = row['dealer']
    product  = row['product']
    url      = row['url']
    price    = float(row['buy_price']) if row['buy_price'] else None

    try:
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        text = await page.inner_text("body")

        is_product, reason = looks_like_product_page(text, price, url)

        status = "✓ OK" if is_product else "✗ BAD"
        print(f"  {status:8s} {dealer:25s} {product:30s}")
        print(f"           {reason}")
        print(f"           {url}")
        print()

        return {
            "dealer":  dealer,
            "product": product,
            "url":     url,
            "price":   price,
            "ok":      is_product,
            "reason":  reason,
        }

    except Exception as e:
        print(f"  ✗ ERROR  {dealer:25s} {product:30s}")
        print(f"           {str(e)[:80]}")
        print(f"           {url}")
        print()
        return {
            "dealer": dealer, "product": product,
            "url": url, "price": price,
            "ok": False, "reason": f"ERROR: {str(e)[:80]}",
        }


async def main():
    print("=" * 70)
    print("  GoldSilverPrices — URL Verification")
    print("=" * 70)

    print("\n  Fetching latest prices from Supabase...")
    rows = fetch_latest_prices()
    print(f"  Found {len(rows)} dealer/product combinations\n")

    results = []

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

        for row in rows:
            result = await verify_url(page, row)
            results.append(result)

        await browser.close()

    # Summary
    ok  = [r for r in results if r['ok']]
    bad = [r for r in results if not r['ok']]

    print("=" * 70)
    print(f"  SUMMARY: {len(ok)} OK · {len(bad)} need fixing")
    print("=" * 70)

    if bad:
        print("\n  URLs TO FIX:")
        for r in bad:
            print(f"\n  ✗ {r['dealer']} — {r['product']}")
            print(f"    Reason: {r['reason']}")
            print(f"    URL:    {r['url']}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())