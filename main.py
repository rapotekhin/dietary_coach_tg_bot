from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from alembic import command
from alembic.config import Config as AlembicConfig

from app.config import load_config
from app.db.session import init_engine
from app.handlers import common, measurements, meal, meal_time, report, start


ROOT = Path(__file__).resolve().parent


def _run_migrations(database_url: str) -> None:
    """Прогоняет alembic upgrade head программно при старте.
    Идемпотентно: если схема уже на head, alembic ничего не делает."""
    cfg = AlembicConfig(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    # alembic env.py использует синхронный URL; конвертируем aiosqlite → sqlite
    sync_url = database_url.replace("+aiosqlite", "")
    cfg.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(cfg, "head")


async def _set_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands([
        BotCommand(command="start", description="Настройка / профиль"),
        BotCommand(command="add_measurements", description="Добавить замеры тела"),
        BotCommand(command="get_report", description="PDF-отчёт за период"),
        BotCommand(command="cancel", description="Отменить текущее действие"),
        BotCommand(command="help", description="Помощь"),
    ])


async def main() -> None:
    cfg = load_config()
    logging.basicConfig(
        level=cfg.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    _run_migrations(cfg.database_url)
    logging.info("Миграции применены, схема БД актуальна.")

    init_engine(cfg.database_url)

    session = AiohttpSession(proxy=cfg.proxy_url) if cfg.proxy_url else AiohttpSession()
    if cfg.proxy_url:
        logging.info("Используется прокси: %s", cfg.proxy_url)
    bot = Bot(
        token=cfg.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    dp = Dispatcher(storage=MemoryStorage())

    # порядок важен: FSM-хендлеры старта/замеров/отчёта/времени должны идти до meal-роутера
    dp.include_router(common.router)
    dp.include_router(start.router)
    dp.include_router(measurements.router)
    dp.include_router(report.router)
    dp.include_router(meal_time.router)
    dp.include_router(meal.router)

    await _set_bot_commands(bot)
    logging.info("Бот запущен.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
