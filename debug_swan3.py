import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://swanbullion.com/gold-bullion/")
        await page.wait_for_timeout(5000)
        
        for sel in [
            "a.woocommerce-loop-product__link",
            "h2 a", ".product a",
            "a[href*='swanbullion.com/20']",
            "a[href*='swanbullion.com/perth']",
            "a[href*='swanbullion.com/'][href*='gold']",
            "ul.products li a",
        ]:
            try:
                els = await page.query_selector_all(sel)
                hrefs = []
                for el in els[:3]:
                    hrefs.append(await el.get_attribute('href'))
                print(f"{sel}: {len(els)} — {hrefs}")
            except Exception as e:
                print(f"{sel}: ERROR {e}")

        await browser.close()

asyncio.run(main())