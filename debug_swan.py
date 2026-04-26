import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://swanbullion.com/2026-australian-kangaroo-1oz-gold-coin/")
        await page.wait_for_timeout(4000)
        h1 = await page.inner_text("h1")
        print("H1:", h1)
        title = await page.title()
        print("Title:", title)
        await browser.close()

asyncio.run(main())