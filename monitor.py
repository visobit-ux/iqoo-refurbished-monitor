import asyncio, json, os, re
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse
from playwright.async_api import async_playwright

# Search the same iQOO store shown in the user's screenshot.
HOME = os.getenv('IQOO_HOME', 'https://mshop.iqoo.com/in/')
QUERY = os.getenv('IQOO_SEARCH', 'refurbished')
STATE_FILE = Path('state.json')

async def telegram(message):
    import urllib.request, urllib.parse
    data = urllib.parse.urlencode({'chat_id': os.environ['TELEGRAM_CHAT_ID'], 'text': message, 'disable_web_page_preview': 'true'}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage", data=data, method='POST')
    with urllib.request.urlopen(req, timeout=20) as response:
        response.read()

def clean(s):
    return re.sub(r'\s+', ' ', s or '').strip()

def is_compare_url(url):
    u = (url or '').lower()
    return 'productcompare' in u or 'compare' in urlparse(u).path

async def find_search(page):
    # Prefer actual visible search inputs; avoid broad class selectors that can open Compare Models.
    selectors = [
        'input[type="search"]',
        'input[placeholder*="search" i]',
        'input[aria-label*="search" i]',
        'input[name*="search" i]',
        'input[placeholder*="搜索"]',
    ]
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if await loc.count() and await loc.is_visible():
                return loc
        except Exception:
            pass

    # Open search only through controls explicitly labelled as search.
    for selector in [
        'button[aria-label*="search" i]', 'button[title*="search" i]',
        'a[aria-label*="search" i]', 'a[title*="search" i]',
        '[role="button"][aria-label*="search" i]'
    ]:
        try:
            loc = page.locator(selector).first
            if await loc.count() and await loc.is_visible():
                await loc.click(timeout=2500)
                await page.wait_for_timeout(500)
                break
        except Exception:
            pass

    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if await loc.count() and await loc.is_visible():
                return loc
        except Exception:
            pass

    # Last fallback: visible text input in the header/search overlay, excluding unrelated fields.
    try:
        candidates = page.locator('input:visible')
        for i in range(await candidates.count()):
            loc = candidates.nth(i)
            typ = (await loc.get_attribute('type') or 'text').lower()
            name = ' '.join([(await loc.get_attribute('placeholder') or ''), (await loc.get_attribute('aria-label') or ''), (await loc.get_attribute('name') or '')]).lower()
            if typ in ('text', 'search', '') and not any(x in name for x in ['phone', 'mobile', 'email', 'pincode', 'postal', 'coupon']):
                return loc
    except Exception:
        pass
    return None

async def extract_search_cards(page):
    """Extract only cards visible in the refurbished search results. Never use details from unrelated pages."""
    products = {}
    anchors = page.locator('a[href*="/product/"]')
    for i in range(await anchors.count()):
        a = anchors.nth(i)
        try:
            href = await a.get_attribute('href')
            if not href:
                continue
            full = urljoin(page.url, href)
            if is_compare_url(full):
                continue
            path = urlparse(full).path.lower()
            if not re.search(r'/product/\d+', path):
                continue

            # Choose the nearest ancestor whose text resembles a real search card.
            card_text = await a.evaluate('''a => {
              let e=a, best='';
              for(let i=0; e && i<8; i++, e=e.parentElement){
                const t=(e.innerText || '').trim();
                if(t.length >= 5 && t.length < 1800 && /refurbished/i.test(t) && /₹\s*[\d,]+/.test(t)) {
                  best=t; break;
                }
              }
              return best;
            }''')
            card_text = clean(card_text)
            if not card_text or not re.search(r'\brefurbished\b', card_text, re.I):
                continue
            if re.search(r'compare\s*models|product\s*compare', card_text, re.I):
                continue

            # Parse only text from the search-result card itself.
            raw_lines = await a.evaluate('''a => {
              let e=a, best='';
              for(let i=0; e && i<8; i++, e=e.parentElement){
                const t=(e.innerText || '').trim();
                if(t.length >= 5 && t.length < 1800 && /refurbished/i.test(t) && /₹\s*[\d,]+/.test(t)) { best=t; break; }
              }
              return best;
            }''')
            lines = [clean(x) for x in (raw_lines or '').splitlines() if clean(x)]
            title = next((x for x in lines if 'refurbished' in x.lower() and len(x) <= 150 and not re.search(r'₹|sold\s*out', x, re.I)), '')
            if not title:
                title = next((x for x in clean(await a.inner_text()).splitlines() if 'refurbished' in x.lower()), '')
            if not title:
                continue
            m = re.search(r'₹\s*[\d,]+(?:\.\d{1,2})?', raw_lines or '')
            price = clean(m.group(0)) if m else ''

            if re.search(r'\bsold\s*out\b|out\s*of\s*stock|currently unavailable', card_text, re.I):
                status = 'OUT_OF_STOCK'
            elif price:
                # On the search results, price without a Sold Out badge is treated as available.
                status = 'IN_STOCK'
            else:
                status = 'UNCLEAR'

            # Preserve variant query parameters (e.g. skuId) so separate variants aren't merged.
            item = {'name': title, 'price': price, 'url': full, 'status': status, 'card_text': card_text[:500]}
            if full not in products or len(card_text) > len(products[full].get('card_text', '')):
                products[full] = item
        except Exception:
            continue
    return sorted(products.values(), key=lambda x: (x['name'].lower(), x['url']))

async def search_products(page):
    await page.goto(HOME, wait_until='domcontentloaded', timeout=60000)
    await page.wait_for_timeout(2500)
    search = await find_search(page)
    if search is None:
        raise RuntimeError('Visible iQOO search box not found; refusing to report unrelated page content')
    await search.fill(QUERY)
    try:
        await search.press('Enter', timeout=4000)
    except Exception:
        pass
    await page.wait_for_timeout(1800)
    # Some versions submit search with a button rather than Enter.
    if not await extract_search_cards(page):
        try:
            # Only click a submit button associated with the search input; never generic site buttons.
            await search.evaluate('el => { const f=el.closest("form"); if (f) f.requestSubmit(); }')
        except Exception:
            pass
        await page.wait_for_timeout(3000)
    for _ in range(8):
        await page.mouse.wheel(0, 850)
        await page.wait_for_timeout(350)
    await page.wait_for_timeout(500)
    items = await extract_search_cards(page)
    if is_compare_url(page.url):
        raise RuntimeError('Search led to Compare Models, not search results; refusing to send false stock data')
    return items

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=1)
        try:
            items = await search_products(page)
        finally:
            await browser.close()

    if not items:
        await telegram('⚠️ iQOO Refurbished monitor: search did not return identifiable refurbished product cards with prices. No stock status was guessed. Please check GitHub Actions logs.')
        raise RuntimeError('No refurbished search-result cards found; previous state kept')

    old = {}
    if STATE_FILE.exists():
        try:
            old_data = json.loads(STATE_FILE.read_text())
            old = {x.get('url'): x for x in old_data.get('items', []) if x.get('url')}
        except Exception:
            old = {}

    alerts = []
    for item in items:
        previous = old.get(item['url'], {}).get('status', 'UNKNOWN')
        if item['status'] == 'IN_STOCK' and previous != 'IN_STOCK':
            alerts.append(item)

    if alerts:
        lines = ['🟢 iQOO REFURBISHED — STOCK AVAILABLE!', '📋 Details taken only from the refurbished search results', '']
        for item in alerts[:15]:
            lines += [f"📱 {item['name']}", f"💰 {item['price'] or 'Price not shown in search result'}", '🟢 In Stock', item['url'], '']
        if len(alerts) > 15:
            lines.append(f'+ {len(alerts)-15} more product(s) available.')
        await telegram('\n'.join(lines).strip())

    STATE_FILE.write_text(json.dumps({'query': QUERY, 'items': items}, indent=2, ensure_ascii=False))
    print(f'Products found in search results: {len(items)}; newly available: {len(alerts)}')
    for item in items:
        print(item['status'], item['name'], item['price'], item['url'])

if __name__ == '__main__':
    asyncio.run(main())
