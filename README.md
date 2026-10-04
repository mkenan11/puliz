# Pulİz

Telegram personal budget tracker.

## Setup

1. Create a virtual environment and install dependencies:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements-dev.txt
   ```

2. Copy `.env.example` to `.env` and add the Telegram bot token. Add
   `GEMINI_API_KEY` if AI commentary is enabled.

3. Start the bot:

   ```powershell
   python bot.py
   ```

The local database defaults to SQLite:

```env
DATABASE_URL=sqlite+aiosqlite:///puliz.db
```

Run the test suite with:

```powershell
python -m unittest discover -s tests -v
```

The bot includes onboarding, expense tracking, reminders, weekly reports,
status/history views, charts, AI commentary with fallback, CSV export, and
two-step account deletion.

## Deployment

The included `Dockerfile` runs Pulİz as a persistent worker. `render.yaml`
defines a Render background worker; add these environment variables in Render:

- `TELEGRAM_BOT_TOKEN`
- `DATABASE_URL` using a PostgreSQL `postgresql+asyncpg://...` URL
- `GEMINI_API_KEY`
- `AI_ENABLED=true`

Do not commit `.env` or any token/API key. SQLite is intended for local
development; use PostgreSQL for deployment.
