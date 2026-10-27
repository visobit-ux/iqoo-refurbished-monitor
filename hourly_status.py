import asyncio
from datetime import datetime, timezone
from playwright.async_api import async_playwright
from monitor import search_products, telegram

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=1)
        try:
            products = await search_products(page)
        finally:
            await browser.close()

    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    if not products:
        await telegram(f'🕐 iQOO Refurbished — Hourly Status\n🕒 {now}\n\n⚠️ Search results were not detected. No product/status was guessed; check GitHub Actions logs.')
        raise RuntimeError('No refurbished search-result cards found')

    available = [x for x in products if x['status'] == 'IN_STOCK']
    sold_out = [x for x in products if x['status'] == 'OUT_OF_STOCK']
    unclear = [x for x in products if x['status'] == 'UNCLEAR']
    lines = [
        '🕐 iQOO Refurbished — Hourly Status', f'🕒 {now}',
        '🔎 Search: refurbished', '📋 Details are from the search-result cards only', '',
        f'📱 Products found: {len(products)}', f'🟢 In stock: {len(available)}',
        f'🔴 Sold out: {len(sold_out)}', f'⚪ Status unclear: {len(unclear)}', ''
    ]
    for item in products[:25]:
        emoji = {'IN_STOCK':'🟢 IN STOCK', 'OUT_OF_STOCK':'🔴 SOLD OUT', 'UNCLEAR':'⚪ STATUS UNCLEAR'}[item['status']]
        lines += [f"{emoji} — {item['name']}", f"💰 {item['price'] or 'Price not shown in search result'}", item['url'], '']
    if len(products) > 25:
        lines.append(f'+ {len(products)-25} more product(s).')
    await telegram('\n'.join(lines).strip())
    print(f'Products found: {len(products)}; in stock: {len(available)}; sold out: {len(sold_out)}; unclear: {len(unclear)}')

if __name__ == '__main__':
    asyncio.run(main())
