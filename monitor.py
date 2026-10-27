import os, json, re, asyncio
from pathlib import Path
from datetime import datetime, timezone
from playwright.async_api import async_playwright
import requests

PRODUCTS = [
    {"url":"https://mshop.iqoo.com/in/product/2057?skuId=8341", "fallback":"iQOO Neo 10R Refurbished"},
    {"url":"https://mshop.iqoo.com/in/product/2074?skuId=8469", "fallback":"iQOO Z10 5G Refurbished"},
    {"url":"https://mshop.iqoo.com/in/product/2070?skuId=8445", "fallback":"iQOO Neo 10 Refurbished"},
    {"url":"https://mshop.iqoo.com/in/product/2054?skuId=8325", "fallback":"iQOO Neo9 Pro Refurbished"},
    {"url":"https://mshop.iqoo.com/in/product/2066?skuId=8405", "fallback":"iQOO 13 Refurbished"},
]
STATE_FILE = Path("state.json")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def telegram(text):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID GitHub Secrets")
    r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True}, timeout=25)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")


def price_from(text):
    patterns = [r"₹\s*[\d,]+", r"Rs\.?\s*[\d,]+", r"INR\s*[\d,]+"]
    found = []
    for pat in patterns:
        found.extend(re.findall(pat, text, flags=re.I))
    if not found:
        return "Price not detected"
    # Prefer the first displayed price, usually current selling price near product header.
    return re.sub(r"\s+", " ", found[0]).strip()


def status_from(text):
    t = text.lower()
    negative = ["out of stock", "sold out", "currently unavailable", "unavailable", "notify me", "coming soon"]
    positive = ["add to cart", "buy now", "add to bag", "in stock", "available now", "buy now"]
    if any(x in t for x in negative):
        # Some pages show a generic word 'unavailable' for an unselected variant; this URL pins skuId.
        return "OUT_OF_STOCK"
    if any(x in t for x in positive):
        return "IN_STOCK"
    return "UNKNOWN"


async def inspect(page, item):
    await page.goto(item["url"], wait_until="domcontentloaded", timeout=60000)
    try:
        await page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass
    await page.wait_for_timeout(2500)
    title = await page.title()
    body = await page.locator("body").inner_text(timeout=15000)
    # Use visible product heading where available, while retaining known fallback model names.
    heading = ""
    for selector in ["h1", "[class*='product-name']", "[class*='productName']", "[class*='title']"]:
        try:
            candidate = (await page.locator(selector).first.inner_text(timeout=1500)).strip()
            if candidate and len(candidate) < 140 and "compare models" not in candidate.lower():
                heading = candidate
                break
        except Exception:
            continue
    name = heading or item["fallback"]
    if title and len(title.strip()) > 2 and "iqoo" in title.lower() and not heading:
        # Avoid using generic site titles as model names.
        cleaned = re.sub(r"\s*[|–-]\s*(iQOO|vivo).*$", "", title.strip(), flags=re.I)
        if cleaned and "official" not in cleaned.lower() and "compare" not in cleaned.lower():
            name = cleaned
    return {"name": name, "price": price_from(body), "status": status_from(body), "url": item["url"]}


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(locale="en-IN", user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36")
        results = []
        for item in PRODUCTS:
            try:
                results.append(await inspect(page, item))
            except Exception as e:
                results.append({"name":item["fallback"], "price":"Price not detected", "status":"UNKNOWN", "url":item["url"], "error":str(e)[:180]})
        await browser.close()

    old = {}
    if STATE_FILE.exists():
        try: old = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception: old = {}
    new = {}
    alerts = []
    for r in results:
        previous = old.get(r["url"], {})
        new[r["url"]] = {"status":r["status"], "price":r["price"], "name":r["name"]}
        if r["status"] == "IN_STOCK" and previous.get("status") != "IN_STOCK":
            alerts.append("🟢 STOCK AVAILABLE\n📱 " + r["name"] + "\n💰 " + r["price"] + "\n🔗 " + r["url"])
        elif r["status"] == "IN_STOCK" and previous.get("price") != r["price"]:
            alerts.append("💰 PRICE UPDATE (in stock)\n📱 " + r["name"] + "\n💵 " + r["price"] + "\n🔗 " + r["url"])
    # Persist only after all products have been checked; unknown does not overwrite a known state.
    merged = dict(old)
    for r in results:
        if r["status"] != "UNKNOWN":
            merged[r["url"]] = new[r["url"]]
    STATE_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    if alerts:
        telegram("📱 iQOO Refurbished Stock Alert\n\n" + "\n\n".join(alerts))
    elif any(r["status"] == "UNKNOWN" for r in results):
        telegram("⚠️ iQOO Refurbished monitor: some product pages did not expose a clear stock status. No stock was guessed.\n\n" + "\n".join(f"• {r['name']} — {r['price']} — {r['status']}\n{r['url']}" for r in results))
    print(json.dumps(results, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
