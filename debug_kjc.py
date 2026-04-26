import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.goto("https://www.kjc-gold-silver-bullion.com.au/gold/coins/", timeout=60000)
        await page.wait_for_timeout(8000)
        
        title = await page.title()
        url = page.url
        print(f"Title: {title}")
        print(f"Final URL: {url}")
        
        # Get all links on page
        all_links = await page.eval_on_selector_all("a", "els => els.map(e => e.href).filter(h => h.includes('kjc'))")
        product_links = [l for l in all_links if any(x in l for x in ['/product', '/PD/', 'coin', 'bar', 'bullion'])]
        print(f"\nProduct-like links: {len(product_links)}")
        for l in product_links[:10]:
            print(f"  {l}")
            
        await browser.close()

asyncio.run(main())