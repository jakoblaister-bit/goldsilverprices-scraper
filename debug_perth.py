import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.goto("https://www.perthmint.com/shop/bullion/cast-bars/kangaroo-1oz-cast-gold-bar/", timeout=60000)
        await page.wait_for_load_state("networkidle", timeout=20000)
        await page.wait_for_timeout(12000)
        
        # Check all price-related elements
        for sel in ["[data-price-amount]", ".price", ".price-wrapper", 
                    "meta[itemprop='price']", "[class*='price']",
                    "span[data-price]", ".product-info-price"]:
            els = await page.query_selector_all(sel)
            for el in els[:2]:
                txt = await el.inner_text() if sel != "meta[itemprop='price']" else await el.get_attribute("content")
                print(f"{sel}: {txt[:50] if txt else 'empty'}")
        
        await browser.close()

asyncio.run(main())