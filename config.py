import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    database_url: str
    ai_enabled: bool
    gemini_api_key: str


def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    database_url = os.getenv(
        "DATABASE_URL", "sqlite+aiosqlite:///puliz.db"
    ).strip()
    ai_enabled = os.getenv("AI_ENABLED", "true").strip().lower() == "true"
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN is not configured. Copy .env.example to .env "
            "and add the token from BotFather."
        )

    return Settings(
        telegram_bot_token=token,
        database_url=database_url,
        ai_enabled=ai_enabled,
        gemini_api_key=gemini_api_key,
    )