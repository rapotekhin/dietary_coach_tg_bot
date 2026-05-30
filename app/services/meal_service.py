from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Meal, MealPhoto


async def create_meal(
    session: AsyncSession,
    *,
    user_id: int,
    chat_id: int,
    message_id: int,
    occurred_at: datetime,
    text: str | None,
    media_group_id: str | None,
    photos: list[tuple[str, str]],
) -> Meal:
    meal = Meal(
        user_id=user_id,
        chat_id=chat_id,
        message_id=message_id,
        media_group_id=media_group_id,
        text=text,
        occurred_at=occurred_at,
    )
    session.add(meal)
    await session.flush()
    for file_id, file_unique_id in photos:
        session.add(MealPhoto(meal_id=meal.id, file_id=file_id, file_unique_id=file_unique_id))
    await session.commit()
    return meal


async def get_meal_for_user(session: AsyncSession, meal_id: int, user_id: int) -> Meal | None:
    stmt = (
        select(Meal)
        .where(Meal.id == meal_id, Meal.user_id == user_id)
        .options(selectinload(Meal.photos))
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def add_photo_to_meal(
    session: AsyncSession, meal_id: int, file_id: str, file_unique_id: str
) -> None:
    session.add(MealPhoto(meal_id=meal_id, file_id=file_id, file_unique_id=file_unique_id))
    await session.commit()


async def get_meal_by_media_group(
    session: AsyncSession, user_id: int, media_group_id: str
) -> Meal | None:
    stmt = (
        select(Meal)
        .where(Meal.user_id == user_id, Meal.media_group_id == media_group_id)
        .options(selectinload(Meal.photos))
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def update_meal_field(
    session: AsyncSession, meal_id: int, user_id: int, **fields
) -> Meal | None:
    meal = await get_meal_for_user(session, meal_id, user_id)
    if meal is None:
        return None
    for k, v in fields.items():
        setattr(meal, k, v)
    await session.commit()
    return meal


async def list_meals_in_period(
    session: AsyncSession, user_id: int, start: datetime, end: datetime
) -> list[Meal]:
    stmt = (
        select(Meal)
        .where(Meal.user_id == user_id, Meal.occurred_at >= start, Meal.occurred_at <= end)
        .order_by(Meal.occurred_at)
    )
    return list((await session.execute(stmt)).scalars().all())
