from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.models import MealType
from app.utils.labels import MEAL_TYPE_LABELS


def meal_kb(meal_id: int, meal_type: str | None, hunger: int | None, satiety: int | None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    # Ряд 1: тип приёма
    for mt in MealType:
        mark = "✅ " if meal_type == mt.value else ""
        kb.button(text=f"{mark}{MEAL_TYPE_LABELS[mt.value]}", callback_data=f"meal:type:{meal_id}:{mt.value}")
    # Ряд 2: голод 1-5
    for n in range(1, 6):
        mark = "🟧" if hunger == n else ""
        kb.button(text=f"{mark}{n}", callback_data=f"meal:hunger:{meal_id}:{n}")
    # Ряд 3: насыщение 1-5
    for n in range(1, 6):
        mark = "🟦" if satiety == n else ""
        kb.button(text=f"{mark}{n}", callback_data=f"meal:satiety:{meal_id}:{n}")
    kb.adjust(5, 5, 5)
    # Ряд 4: изменить время
    kb.row(
        InlineKeyboardButton(text="🕒 Изменить время", callback_data=f"meal:edit_time:{meal_id}")
    )
    return kb.as_markup()


def meal_header(occurred_at_str: str) -> str:
    return (
        f"<b>Приём пищи зафиксирован.</b>\n"
        f"Время: <code>{occurred_at_str}</code>\n"
        f"Выберите тип, степень голода и насыщения ниже. Кнопки можно нажать повторно — выбор изменится."
    )
