import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://swanbullion.com/buy-gold/")
        await page.wait_for_timeout(5000)
        
        # Try different selectors
        for sel in [
            "a[href*='swanbullion.com'][href$='/']",
            "a.woocommerce-loop-product__link",
            "h2.woocommerce-loop-product__title a",
            "a[href*='swanbullion']",
            ".products a",
        ]:
            try:
                els = await page.query_selector_all(sel)
                hrefs = []
                for el in els[:3]:
                    hrefs.append(await el.get_attribute('href'))
                print(f"{sel}: {len(els)} found — {hrefs}")
            except Exception as e:
                print(f"{sel}: ERROR {e}")
        
        await browser.close()

asyncio.run(main())