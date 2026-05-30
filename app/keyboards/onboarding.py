from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.models import WEIGHT_GOALS, GoalCode
from app.utils.labels import GOAL_LABELS


def gender_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Мужской", callback_data="gender:male")
    kb.button(text="Женский", callback_data="gender:female")
    return kb.as_markup()


def goals_kb(selected: set[str]) -> InlineKeyboardMarkup:
    """Inline keyboard для выбора целей. Чекбоксы по выбранным.

    На мобильных экранах длинные подписи целей режутся даже в 2 колонки, поэтому
    некрасивые цели идут по 1 в ряд. Короткие — попарно.
    """
    kb = InlineKeyboardBuilder()
    # 3 цели по весу (взаимоисключающие) — короткие, помещаются в 1 ряд по 3
    weight_codes = [GoalCode.WEIGHT_LOSS, GoalCode.WEIGHT_GAIN, GoalCode.WEIGHT_MAINTAIN]
    for code in weight_codes:
        mark = "✅" if code.value in selected else "▫️"
        kb.button(text=f"{mark} {GOAL_LABELS[code.value]}", callback_data=f"goal:toggle:{code.value}")

    # Остальные — каждая в свой ряд, чтобы подписи не обрезались
    other_codes = [c for c in GoalCode if c not in WEIGHT_GOALS]
    for code in other_codes:
        mark = "✅" if code.value in selected else "▫️"
        kb.button(text=f"{mark} {GOAL_LABELS[code.value]}", callback_data=f"goal:toggle:{code.value}")

    kb.adjust(3, *([1] * len(other_codes)))
    kb.row(InlineKeyboardButton(text="Готово →", callback_data="goal:done"))
    return kb.as_markup()


def confirm_kb(scope: str) -> InlineKeyboardMarkup:
    """[Сохранить] [Отмена] — scope нужен, чтобы хендлеры не пересекались."""
    kb = InlineKeyboardBuilder()
    kb.button(text="Сохранить", callback_data=f"{scope}:save")
    kb.button(text="Отмена", callback_data=f"{scope}:cancel")
    return kb.as_markup()
