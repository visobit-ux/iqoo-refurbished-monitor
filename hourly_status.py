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
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID GitHub Secrets")
    r=requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id":CHAT_ID,"text":text,"disable_web_page_preview":True}, timeout=25)
    r.raise_for_status()
    if not r.json().get("ok"): raise RuntimeError(f"Telegram API error: {r.text}")

def price_from(text):
    m=re.search(r"₹\s*[\d,]+|Rs\.?\s*[\d,]+|INR\s*[\d,]+", text, flags=re.I)
    return re.sub(r"\s+"," ",m.group(0)).strip() if m else "Price not detected"

def status_from(text):
    t=text.lower()
    if any(x in t for x in ["out of stock","sold out","currently unavailable","unavailable","notify me","coming soon"]): return "🔴 Out of stock / unavailable"
    if any(x in t for x in ["add to cart","buy now","add to bag","in stock","available now"]): return "🟢 In stock"
    return "⚪ Status unclear"

async def main():
    results=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        page=await browser.new_page(locale="en-IN", user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36")
        for item in PRODUCTS:
            try:
                await page.goto(item["url"],wait_until="domcontentloaded",timeout=60000)
                try: await page.wait_for_load_state("networkidle",timeout=12000)
                except Exception: pass
                await page.wait_for_timeout(2000)
                body=await page.locator("body").inner_text(timeout=15000)
                heading=""
                for sel in ["h1","[class*='product-name']","[class*='productName']"]:
                    try:
                        s=(await page.locator(sel).first.inner_text(timeout=1500)).strip()
                        if s and len(s)<140 and "compare models" not in s.lower(): heading=s; break
                    except Exception: pass
                results.append((heading or item["fallback"],price_from(body),status_from(body),item["url"]))
            except Exception:
                results.append((item["fallback"],"Price not detected","⚪ Status unclear",item["url"]))
        await browser.close()
    now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines=[f"🕐 iQOO Refurbished — Hourly Status\n🕒 {now}",""]
    for name,price,status,url in results:
        lines.append(f"📱 {name}\n💰 {price}\n{status}\n🔗 {url}\n")
    telegram("\n".join(lines))
    print("\n".join(lines))

if __name__=="__main__": asyncio.run(main())
