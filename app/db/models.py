from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"


class MealType(str, Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"
    SPORTS_NUTRITION = "sports_nutrition"


class GoalCode(str, Enum):
    WEIGHT_LOSS = "weight_loss"
    WEIGHT_GAIN = "weight_gain"
    WEIGHT_MAINTAIN = "weight_maintain"
    WAIST_REDUCE = "waist_reduce"
    SHOULDERS_INCREASE = "shoulders_increase"
    HIPS_INCREASE = "hips_increase"
    REGULAR_TIMING = "regular_timing"
    FEWER_SNACKS = "fewer_snacks"
    NO_SKIP_MAIN = "no_skip_main"
    NO_OVEREAT = "no_overeat"
    NO_HUNGER = "no_hunger"
    REGULAR_SPORTS_NUTRITION = "regular_sports_nutrition"


WEIGHT_GOALS = {GoalCode.WEIGHT_LOSS, GoalCode.WEIGHT_GAIN, GoalCode.WEIGHT_MAINTAIN}


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram ID
    height_cm: Mapped[float] = mapped_column(Float)
    age: Mapped[int] = mapped_column(Integer)
    gender: Mapped[str] = mapped_column(String(16))
    timezone: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    goals: Mapped[list["UserGoal"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    meals: Mapped[list["Meal"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    measurements: Mapped[list["Measurement"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserGoal(Base):
    __tablename__ = "user_goals"
    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_user_goal"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="goals")


class Measurement(Base):
    """Snapshot замеров тела и веса в момент времени."""

    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    shoulders_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    waist_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    hips_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    user: Mapped[User] = relationship(back_populates="measurements")


class Meal(Base):
    """Запись приёма пищи. Создаётся сразу при отправке сообщения, поля добиваются кнопками."""

    __tablename__ = "meals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    media_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    meal_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hunger: Mapped[int | None] = mapped_column(Integer, nullable=True)
    satiety: Mapped[int | None] = mapped_column(Integer, nullable=True)

    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    photos: Mapped[list["MealPhoto"]] = relationship(back_populates="meal", cascade="all, delete-orphan")
    user: Mapped[User] = relationship(back_populates="meals")


class MealPhoto(Base):
    __tablename__ = "meal_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meal_id: Mapped[int] = mapped_column(Integer, ForeignKey("meals.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[str] = mapped_column(String(256))
    file_unique_id: Mapped[str] = mapped_column(String(128))

    meal: Mapped[Meal] = relationship(back_populates="photos")
