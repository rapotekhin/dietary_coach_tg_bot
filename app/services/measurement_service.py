from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Measurement


async def add_measurement(
    session: AsyncSession,
    *,
    user_id: int,
    shoulders_cm: float,
    waist_cm: float,
    hips_cm: float,
    weight_kg: float,
    measured_at: datetime,
) -> Measurement:
    m = Measurement(
        user_id=user_id,
        shoulders_cm=shoulders_cm,
        waist_cm=waist_cm,
        hips_cm=hips_cm,
        weight_kg=weight_kg,
        measured_at=measured_at,
    )
    session.add(m)
    await session.commit()
    return m


async def list_measurements_in_period(
    session: AsyncSession, user_id: int, start: datetime, end: datetime
) -> list[Measurement]:
    stmt = (
        select(Measurement)
        .where(
            Measurement.user_id == user_id,
            Measurement.measured_at >= start,
            Measurement.measured_at <= end,
        )
        .order_by(Measurement.measured_at)
    )
    return list((await session.execute(stmt)).scalars().all())


async def last_measurement_before(
    session: AsyncSession, user_id: int, before: datetime
) -> Measurement | None:
    stmt = (
        select(Measurement)
        .where(Measurement.user_id == user_id, Measurement.measured_at < before)
        .order_by(Measurement.measured_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()
