# test_bn.py
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://bullionnow.com.au/sell-my-bullion/", wait_until="domcontentloaded")
        await page.wait_for_timeout(8000)
        
        # Find the nfusions iframe
        frame = next((f for f in page.frames if "nfusionsolutions" in f.url and "table" in f.url), None)
        if frame:
            print("Found frame:", frame.url)
            data = await frame.evaluate("""() => {
                const rows = document.querySelectorAll('tr.symbol-block');
                return Array.from(rows).map(r => ({
                    metal: r.querySelector('th.symbol') ? r.querySelector('th.symbol').innerText : '',
                    price: r.querySelector('.value') ? r.querySelector('.value').innerText : ''
                }));
            }""")
            print("Data:", data)
        else:
            print("Frame not found")
        await browser.close()

asyncio.run(test())