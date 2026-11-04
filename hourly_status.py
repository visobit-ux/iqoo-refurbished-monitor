import os, re, asyncio
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

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def telegram(text):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Missing Telegram secrets")
    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": True
        },
        timeout=25
    )
    r.raise_for_status()
    if not r.json().get("ok"):
        raise RuntimeError(f"Telegram API error: {r.text}")

def price_from(text):
    m = re.search(
        r"₹\s*[\d,]+|Rs\.?\s*[\d,]+|INR\s*[\d,]+",
        text,
        flags=re.I
    )
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else "Price not detected"

def status_from(text):
    t = text.lower()

    if any(x in t for x in [
        "out of stock", "sold out", "currently unavailable",
        "unavailable", "notify me", "coming soon"
    ]):
        return "OUT_OF_STOCK"

    if any(x in t for x in [
        "add to cart", "buy now", "add to bag",
        "in stock", "available now"
    ]):
        return "IN_STOCK"

    return "UNKNOWN"

async def main():
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        page = await browser.new_page(
            locale="en-IN",
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
        )

        for item in PRODUCTS:
            try:
                await page.goto(
                    item["url"],
                    wait_until="domcontentloaded",
                    timeout=60000
                )

                try:
                    await page.wait_for_load_state(
                        "networkidle",
                        timeout=12000
                    )
                except Exception:
                    pass

                await page.wait_for_timeout(2000)

                body = await page.locator("body").inner_text(timeout=15000)

                heading = ""

                for sel in [
                    "h1",
                    "[class*='product-name']",
                    "[class*='productName']"
                ]:
                    try:
                        s = (
                            await page.locator(sel).first.inner_text(timeout=1500)
                        ).strip()

                        if s and len(s) < 140 and "compare models" not in s.lower():
                            heading = s
                            break
                    except Exception:
                        pass

                results.append({
                    "name": heading or item["fallback"],
                    "price": price_from(body),
                    "status": status_from(body),
                    "url": item["url"]
                })

            except Exception:
                results.append({
                    "name": item["fallback"],
                    "price": "Price not detected",
                    "status": "UNKNOWN",
                    "url": item["url"]
                })

        await browser.close()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    in_stock = [r for r in results if r["status"] == "IN_STOCK"]
    unknown = [r for r in results if r["status"] == "UNKNOWN"]

    if not in_stock and not unknown:
        message = (
            f"⏰ iQOO Refurbished Status\n"
            f"🔴 All {len(results)} models are out of stock.\n"
            f"🕒 {now}"
        )

    elif not in_stock:
        message = (
            f"⏰ iQOO Refurbished Status\n"
            f"⚪ No confirmed stock — {len(unknown)} status unclear.\n"
            f"🕒 {now}"
        )

    else:
        lines = [
            f"🎉 iQOO REFURBISHED — STOCK UPDATE",
            f"🕒 {now}",
            ""
        ]

        for r in results:
            if r["status"] == "IN_STOCK":
                status = "🟢 In stock"
            elif r["status"] == "OUT_OF_STOCK":
                status = "🔴 Out of stock / unavailable"
            else:
                status = "⚪ Status unclear"

            lines.append(
                f"📱 {r['name']}\n"
                f"💰 {r['price']}\n"
                f"{status}\n"
                f"🔗 {r['url']}\n"
            )

        message = "\n".join(lines)

    telegram(message)
    print(message)


if __name__ == "__main__":
    asyncio.run(main())
