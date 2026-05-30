import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    database_url: str
    log_level: str
    proxy_url: str | None


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN не задан в .env")
    # Приоритет: PROXY_URL (.env) → HTTPS_PROXY → HTTP_PROXY (env). Регистр любой.
    proxy = (
        os.getenv("PROXY_URL")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("https_proxy")
        or os.getenv("HTTP_PROXY")
        or os.getenv("http_proxy")
        or ""
    ).strip() or None
    return Config(
        bot_token=token,
        database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./dietary_coach.db"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        proxy_url=proxy,
    )
