# iQOO hourly status add-on

Upload `hourly_status.py` to the repository root and
`.github/workflows/iqoo-hourly-status.yml` to `.github/workflows/`.

It reuses the existing `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` secrets
and sends a Telegram status every hour.

Your existing ~5-minute monitor should remain enabled for immediate change alerts.
GitHub scheduled jobs can be delayed by a few minutes.
