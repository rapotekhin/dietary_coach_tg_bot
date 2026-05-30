from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import GoalCode, Measurement, User, UserGoal


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    stmt = select(User).where(User.user_id == user_id).options(selectinload(User.goals))
    return (await session.execute(stmt)).scalar_one_or_none()


async def user_exists(session: AsyncSession, user_id: int) -> bool:
    stmt = select(User.user_id).where(User.user_id == user_id)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def create_user(
    session: AsyncSession,
    *,
    user_id: int,
    height_cm: float,
    age: int,
    gender: str,
    timezone: str,
    goal_codes: list[str],
    weight_kg: float,
    measured_at,
) -> User:
    user = User(
        user_id=user_id,
        height_cm=height_cm,
        age=age,
        gender=gender,
        timezone=timezone,
    )
    session.add(user)
    await session.flush()

    for code in goal_codes:
        session.add(UserGoal(user_id=user_id, code=code))

    # Стартовый замер только с весом — обхваты юзер добавит через /add_measurements
    session.add(
        Measurement(
            user_id=user_id,
            shoulders_cm=None,
            waist_cm=None,
            hips_cm=None,
            weight_kg=weight_kg,
            measured_at=measured_at,
        )
    )
    await session.commit()
    return user


async def get_goal_codes(session: AsyncSession, user_id: int) -> set[str]:
    stmt = select(UserGoal.code).where(UserGoal.user_id == user_id)
    return {row[0] for row in (await session.execute(stmt)).all()}
