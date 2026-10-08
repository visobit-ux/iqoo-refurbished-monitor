
# iQOO Refurbished Search Monitor

This monitor opens the iQOO India store, uses its search box to search for
`refurbished`, collects refurbished/product links, and sends a Telegram alert
when the observed results change.

## Setup

1. Create a GitHub repository and upload these files.
2. Create a Telegram bot with @BotFather and obtain the bot token.
3. Send any message to the bot, then obtain your chat ID.
4. In GitHub: Settings -> Secrets and variables -> Actions -> New repository secret.
5. Add:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
6. Run the workflow once from Actions -> iQOO refurbished search monitor -> Run workflow.

The workflow is scheduled approximately every 5 minutes. GitHub Actions cron
jobs can be delayed, so this is not an exact 5-minute guarantee.

## What it alerts on

- A newly discovered refurbished/product listing.
- A changed product result/link label.

It does not claim exact real-time stock unless the search-result page itself
exposes stock information. The monitor is intentionally based on the same
search-bar query `refurbished`.

If iQOO changes its search UI, the selectors in `monitor.py` may need updating.
