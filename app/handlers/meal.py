from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message

from app.db.models import MealType
from app.db.session import get_sessionmaker
from app.keyboards.meal import meal_header, meal_kb
from app.services import meal_service, user_service
from app.utils.labels import MEAL_TYPE_LABELS
from app.utils.time_utils import fmt_dt, parse_caption_time, to_local

logger = logging.getLogger(__name__)
router = Router(name="meal")

# Сериализация обработки одного media_group, чтобы первое фото создавало запись,
# а остальные просто докидывали фото к существующей.
_media_group_locks: dict[str, asyncio.Lock] = {}


def _lock_for(group_id: str) -> asyncio.Lock:
    lock = _media_group_locks.get(group_id)
    if lock is None:
        lock = asyncio.Lock()
        _media_group_locks[group_id] = lock
    return lock


async def _ensure_user(session, user_id: int):
    user = await user_service.get_user(session, user_id)
    return user


def _occurred_at(message: Message, tz_name: str) -> datetime:
    cap = message.caption or message.text
    parsed = parse_caption_time(cap, tz_name)
    if parsed is not None:
        return parsed
    return to_local(message.date, tz_name)


async def _send_meal_card(message: Message, meal_id: int, occurred_at: datetime, meal_type: str | None, hunger: int | None, satiety: int | None) -> None:
    await message.reply(
        meal_header(fmt_dt(occurred_at)),
        parse_mode="HTML",
        reply_markup=meal_kb(meal_id, meal_type, hunger, satiety),
    )


@router.message(StateFilter(None), F.photo)
async def on_photo_meal(message: Message) -> None:
    assert message.from_user is not None and message.photo is not None

    sm = get_sessionmaker()
    async with sm() as session:
        user = await _ensure_user(session, message.from_user.id)
        if user is None:
            await message.answer("Сначала настрой профиль: /start")
            return
        tz = user.timezone
        photo = message.photo[-1]  # самое большое разрешение

        if message.media_group_id:
            async with _lock_for(message.media_group_id):
                existing = await meal_service.get_meal_by_media_group(
                    session, user.user_id, message.media_group_id
                )
                if existing is not None:
                    await meal_service.add_photo_to_meal(
                        session, existing.id, photo.file_id, photo.file_unique_id
                    )
                    return  # карточку не дублируем
                meal = await meal_service.create_meal(
                    session,
                    user_id=user.user_id,
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    occurred_at=_occurred_at(message, tz),
                    text=message.caption,
                    media_group_id=message.media_group_id,
                    photos=[(photo.file_id, photo.file_unique_id)],
                )
                await _send_meal_card(message, meal.id, meal.occurred_at, None, None, None)
                return

        # одиночное фото
        meal = await meal_service.create_meal(
            session,
            user_id=user.user_id,
            chat_id=message.chat.id,
            message_id=message.message_id,
            occurred_at=_occurred_at(message, tz),
            text=message.caption,
            media_group_id=None,
            photos=[(photo.file_id, photo.file_unique_id)],
        )
        await _send_meal_card(message, meal.id, meal.occurred_at, None, None, None)


@router.message(StateFilter(None), F.text & ~F.text.startswith("/"))
async def on_text_meal(message: Message) -> None:
    assert message.from_user is not None
    sm = get_sessionmaker()
    async with sm() as session:
        user = await _ensure_user(session, message.from_user.id)
        if user is None:
            await message.answer("Сначала настрой профиль: /start")
            return
        meal = await meal_service.create_meal(
            session,
            user_id=user.user_id,
            chat_id=message.chat.id,
            message_id=message.message_id,
            occurred_at=_occurred_at(message, user.timezone),
            text=message.text,
            media_group_id=None,
            photos=[],
        )
        await _send_meal_card(message, meal.id, meal.occurred_at, None, None, None)


# ===== Кнопки на карточке =====

async def _update_card(callback: CallbackQuery, meal) -> None:
    assert callback.message is not None
    try:
        await callback.message.edit_text(
            meal_header(fmt_dt(meal.occurred_at)),
            parse_mode="HTML",
            reply_markup=meal_kb(meal.id, meal.meal_type, meal.hunger, meal.satiety),
        )
    except Exception as e:  # noqa: BLE001 — Telegram кидает "message is not modified"
        logger.debug("edit_text failed: %s", e)


@router.callback_query(F.data.startswith("meal:type:"))
async def on_meal_type(callback: CallbackQuery) -> None:
    assert callback.data is not None and callback.from_user is not None
    _, _, meal_id_s, value = callback.data.split(":", 3)
    if value not in {m.value for m in MealType}:
        await callback.answer("Неизвестный тип", show_alert=True)
        return
    sm = get_sessionmaker()
    async with sm() as session:
        meal = await meal_service.update_meal_field(
            session, int(meal_id_s), callback.from_user.id, meal_type=value
        )
    if meal is None:
        await callback.answer("Приём не найден", show_alert=True)
        return
    await _update_card(callback, meal)
    await callback.answer(f"Тип: {MEAL_TYPE_LABELS[value]}")


@router.callback_query(F.data.startswith("meal:hunger:"))
async def on_meal_hunger(callback: CallbackQuery) -> None:
    assert callback.data is not None and callback.from_user is not None
    _, _, meal_id_s, n_s = callback.data.split(":", 3)
    n = int(n_s)
    sm = get_sessionmaker()
    async with sm() as session:
        meal = await meal_service.update_meal_field(
            session, int(meal_id_s), callback.from_user.id, hunger=n
        )
    if meal is None:
        await callback.answer("Приём не найден", show_alert=True)
        return
    await _update_card(callback, meal)
    await callback.answer(f"Голод: {n}")


@router.callback_query(F.data.startswith("meal:satiety:"))
async def on_meal_satiety(callback: CallbackQuery) -> None:
    assert callback.data is not None and callback.from_user is not None
    _, _, meal_id_s, n_s = callback.data.split(":", 3)
    n = int(n_s)
    sm = get_sessionmaker()
    async with sm() as session:
        meal = await meal_service.update_meal_field(
            session, int(meal_id_s), callback.from_user.id, satiety=n
        )
    if meal is None:
        await callback.answer("Приём не найден", show_alert=True)
        return
    await _update_card(callback, meal)
    await callback.answer(f"Насыщение: {n}")
