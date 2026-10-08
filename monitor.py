
import asyncio, json, os, re, hashlib
from pathlib import Path
from playwright.async_api import async_playwright

HOME = os.getenv("IQOO_HOME", "https://shop.iqoo.com/in/")
QUERY = os.getenv("IQOO_SEARCH", "refurbished")
STATE_FILE = Path("state.json")

async def telegram(text):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    import urllib.request, urllib.parse
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data, method="POST"
    )
    urllib.request.urlopen(req, timeout=20).read()

def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})

        await page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2500)

        # Try common search inputs used by iQOO/vivo storefronts.
        selectors = [
            'input[type="search"]',
            'input[placeholder*="Search" i]',
            'input[placeholder*="search" i]',
            'input[aria-label*="search" i]',
            'input[name*="search" i]'
        ]
        search = None
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() and await loc.is_visible():
                    search = loc
                    break
            except Exception:
                pass

        # Some storefronts hide the input until the search icon is clicked.
        if search is None:
            for sel in ['button[aria-label*="search" i]', '[class*="search" i] button', 'a[href*="search" i]']:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() and await loc.is_visible():
                        await loc.click()
                        await page.wait_for_timeout(500)
                        break
                except Exception:
                    pass
            for sel in selectors:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() and await loc.is_visible():
                        search = loc
                        break
                except Exception:
                    pass

        if search is None:
            raise RuntimeError("Could not find the iQOO search box. Inspect selectors in monitor.py.")

        await search.fill(QUERY)
        await search.press("Enter")
        await page.wait_for_timeout(4000)

        # Scroll so lazy-loaded product cards can appear.
        for _ in range(5):
            await page.mouse.wheel(0, 1200)
            await page.wait_for_timeout(600)

        items = []
        links = await page.locator("a[href]").all()
        seen = set()
        for a in links:
            try:
                href = await a.get_attribute("href")
                txt = clean(await a.inner_text())
                if not href or not txt:
                    continue
                full = href if href.startswith("http") else "https://shop.iqoo.com" + href
                hay = (txt + " " + full).lower()
                if "product/" not in hay and "refurb" not in hay:
                    continue
                if "product/" not in full.lower():
                    continue
                key = (full.split("?")[0], txt)
                if key in seen:
                    continue
                seen.add(key)
                items.append({"name": txt, "url": full})
            except Exception:
                pass

        # Keep only meaningful product-looking entries.
        items = [x for x in items if len(x["name"]) >= 4]
        items.sort(key=lambda x: (x["url"], x["name"]))

        digest = hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()
        old = {}
        if STATE_FILE.exists():
            try:
                old = json.loads(STATE_FILE.read_text())
            except Exception:
                old = {}

        old_items = {x["url"]: x for x in old.get("items", [])}
        new_items = {x["url"]: x for x in items}

        new_urls = [u for u in new_items if u not in old_items]
        changed = [u for u in new_items if u in old_items and new_items[u]["name"] != old_items[u]["name"]]

        if old and (new_urls or changed):
            lines = ["🔔 iQOO refurbished search update", ""]
            for u in new_urls[:15]:
                lines.append("🆕 " + new_items[u]["name"])
                lines.append(u)
            for u in changed[:15]:
                lines.append("🔄 " + new_items[u]["name"])
                lines.append(u)
            await telegram("\n".join(lines))

        STATE_FILE.write_text(json.dumps({
            "query": QUERY,
            "items": items,
            "digest": digest
        }, indent=2))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
