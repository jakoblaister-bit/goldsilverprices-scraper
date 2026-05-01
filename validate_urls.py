"""
validate_urls.py — check every catalogue URL resolves to the right product page.

For each dealer entry it checks:
  1. Final URL stayed on the same domain (no redirect to homepage / 404 page)
  2. Page title contains at least one expected keyword derived from the product

Run:  python validate_urls.py
      python validate_urls.py --fix   (prints corrected entries you can paste back)

Exit code 0 = all OK, 1 = at least one failure.
"""

import asyncio
import argparse
import sys
from playwright.async_api import async_playwright

# ── Pull CATALOGUE directly from the scraper ─────────────────────────────────
sys.path.insert(0, ".")
from scraper_v3 import CATALOGUE


def _expected_keywords(product_name, product_def):
    """Return a set of lowercase strings that SHOULD appear somewhere on the page."""
    kws = set()
    metal = product_def.get("metal", "")
    kws.add(metal)

    coin_type = product_def.get("coin_type")
    bar_brand = product_def.get("bar_brand")
    bar_type  = product_def.get("bar_type")

    if coin_type:
        # e.g. "Maple Leaf" → {"maple", "leaf"}
        for w in coin_type.lower().split():
            if len(w) > 3:
                kws.add(w)
    if bar_brand and bar_brand.lower() not in ("generic",):
        for w in bar_brand.lower().split():
            if len(w) > 2:
                kws.add(w)
    if bar_type:
        kws.add(bar_type.lower())

    # weight hint
    woz = product_def.get("weight_oz")
    wg  = product_def.get("weight_g")
    if wg:
        kws.add(f"{int(wg)}g")
    elif woz:
        if woz >= 30:
            kws.add("kilo")
            kws.add("1kg")
        elif woz == int(woz):
            kws.add(f"{int(woz)}oz")

    return kws


def _domain(url):
    from urllib.parse import urlparse
    return urlparse(url).netloc.lower().lstrip("www.")


async def validate(args):
    ok = fail = skip = 0
    failures = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx     = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
        page = await ctx.new_page()

        for product_name, product_def in CATALOGUE.items():
            kws = _expected_keywords(product_name, product_def)

            for dealer_entry in product_def.get("dealers", []):
                dealer = dealer_entry["dealer"]
                url    = dealer_entry["url"]
                expected_domain = _domain(url)

                try:
                    resp = await page.goto(url, timeout=40000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)

                    final_url   = page.url
                    final_dom   = _domain(final_url)
                    title       = (await page.title()).lower()
                    body_sample = (await page.inner_text("body"))[:2000].lower()
                    combined    = title + " " + body_sample

                    # Check 1: domain unchanged (redirect to homepage = product gone)
                    domain_ok = final_dom == expected_domain

                    # Check 2: at least 2 keywords present on page
                    matched = [k for k in kws if k in combined]
                    kw_ok   = len(matched) >= min(2, len(kws))

                    status = resp.status if resp else 0

                    if domain_ok and kw_ok and status < 400:
                        print(f"  ✓ {dealer:25s} {product_name}")
                        ok += 1
                    else:
                        reasons = []
                        if not domain_ok:
                            reasons.append(f"redirected → {final_url[:70]}")
                        if not kw_ok:
                            reasons.append(f"missing keywords {kws - set(matched)}")
                        if status >= 400:
                            reasons.append(f"HTTP {status}")
                        msg = f"  ✗ {dealer:25s} {product_name}  — {'; '.join(reasons)}"
                        print(msg)
                        failures.append({"dealer": dealer, "product": product_name,
                                         "url": url, "final_url": final_url,
                                         "title": title[:80], "reasons": reasons})
                        fail += 1

                except Exception as e:
                    print(f"  ? {dealer:25s} {product_name}  — ERROR: {str(e)[:80]}")
                    failures.append({"dealer": dealer, "product": product_name,
                                     "url": url, "error": str(e)})
                    fail += 1

        await browser.close()

    print(f"\n{'─'*60}")
    print(f"  OK: {ok}   FAIL: {fail}   SKIP: {skip}")
    print(f"{'─'*60}")

    if failures:
        print("\nFailed entries (update these URLs in scraper_v3.py CATALOGUE):\n")
        for f in failures:
            print(f"  Dealer:  {f['dealer']}")
            print(f"  Product: {f['product']}")
            print(f"  URL:     {f['url']}")
            if "final_url" in f and f["final_url"] != f["url"]:
                print(f"  Landed:  {f['final_url']}")
            if "title" in f:
                print(f"  Title:   {f['title']}")
            print(f"  Reason:  {', '.join(f.get('reasons', [f.get('error','')]))}")
            print()

    return 0 if fail == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true", help="print correctable entries")
    args = parser.parse_args()
    sys.exit(asyncio.run(validate(args)))