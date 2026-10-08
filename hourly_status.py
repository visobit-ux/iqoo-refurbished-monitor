import asyncio, os, re
from playwright.async_api import async_playwright

HOME = os.getenv("IQOO_HOME", "https://shop.iqoo.com/in/")
QUERY = os.getenv("IQOO_SEARCH", "refurbished")

def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()

async def telegram(text):
    import urllib.request, urllib.parse
    data = urllib.parse.urlencode({
        "chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
        data=data, method="POST"
    )
    urllib.request.urlopen(req, timeout=20).read()

async def find_search(page):
    sels = [
        'input[type="search"]',
        'input[placeholder*="Search" i]',
        'input[placeholder*="search" i]',
        'input[aria-label*="search" i]',
        'input[name*="search" i]'
    ]
    for sel in sels:
        try:
            x = page.locator(sel).first
            if await x.count() and await x.is_visible():
                return x
        except Exception:
            pass
    for sel in ['button[aria-label*="search" i]', '[class*="search" i] button',
                'a[href*="search" i]']:
        try:
            x = page.locator(sel).first
            if await x.count() and await x.is_visible():
                await x.click()
                await page.wait_for_timeout(700)
                break
        except Exception:
            pass
    for sel in sels:
        try:
            x = page.locator(sel).first
            if await x.count() and await x.is_visible():
                return x
        except Exception:
            pass
    return None

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            await page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2500)
            search = await find_search(page)
            if search is None:
                raise RuntimeError("iQOO search box not found")
            await search.fill(QUERY)
            await search.press("Enter")
            await page.wait_for_timeout(4000)

            for _ in range(5):
                await page.mouse.wheel(0, 1200)
                await page.wait_for_timeout(500)

            links = await page.locator("a[href]").all()
            products, seen = [], set()
            for a in links:
                try:
                    href = await a.get_attribute("href")
                    name = clean(await a.inner_text())
                    if not href or not name:
                        continue
                    full = href if href.startswith("http") else "https://shop.iqoo.com" + href
                    if "/product/" not in full.lower():
                        continue
                    key = full.split("?")[0]
                    if key in seen or len(name) < 4:
                        continue
                    seen.add(key)
                    products.append({"name": name, "url": full})
                except Exception:
                    pass

            results = []
            for product in products[:30]:
                status = "⚪ status not clear"
                try:
                    d = await browser.new_page(viewport={"width": 1200, "height": 900})
                    await d.goto(product["url"], wait_until="domcontentloaded", timeout=45000)
                    await d.wait_for_timeout(1800)
                    low = clean(await d.locator("body").inner_text()).lower()
                    pos = any(x in low for x in ["add to cart", "buy now", "in stock",
                                                 "available now", "available"])
                    neg = any(x in low for x in ["out of stock", "sold out",
                                                 "currently unavailable", "unavailable"])
                    if neg:
                        status = "🔴 OUT OF STOCK"
                    elif pos:
                        status = "🟢 IN/AVAILABLE"
                    await d.close()
                except Exception:
                    status = "⚪ check failed"
                results.append((product["name"], status, product["url"]))

            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

            if not results:
                msg = ("🕐 iQOO Refurbished — Hourly Status\n\n"
                       "⚠️ कोई product link नहीं मिला।\n"
                       "यह जरूरी नहीं कि stock नहीं है; site check स्पष्ट नहीं हुआ।")
            else:
                available = sum("🟢" in s for _, s, _ in results)
                out = sum("🔴" in s for _, s, _ in results)
                unclear = len(results) - available - out
                lines = [
                    "🕐 iQOO Refurbished — Hourly Status",
                    f"🕒 {now}", "",
                    f"📱 Products checked: {len(results)}",
                    f"🟢 Available: {available}",
                    f"🔴 Out of stock: {out}",
                    f"⚪ Unclear: {unclear}", ""
                ]
                for name, status, url in results[:20]:
                    lines += [f"{status} {name[:70]}", url]
                if len(results) > 20:
                    lines.append(f"+ {len(results)-20} more product(s) checked.")
                msg = "\n".join(lines)
            await telegram(msg)
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
