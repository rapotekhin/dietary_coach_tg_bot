import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    database_url: str
    log_level: str


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN не задан в .env")
    return Config(
        bot_token=token,
        database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./dietary_coach.db"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
