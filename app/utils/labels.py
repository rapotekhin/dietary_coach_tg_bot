"""Человекочитаемые лейблы для enum'ов БД."""
from __future__ import annotations

from app.db.models import GoalCode, MealType

MEAL_TYPE_LABELS: dict[str, str] = {
    MealType.BREAKFAST.value: "Завтрак",
    MealType.LUNCH.value: "Обед",
    MealType.DINNER.value: "Ужин",
    MealType.SNACK.value: "Перекус",
    MealType.SPORTS_NUTRITION.value: "Спортпит",
}

MAIN_MEAL_TYPES = {MealType.BREAKFAST.value, MealType.LUNCH.value, MealType.DINNER.value}

GOAL_LABELS: dict[str, str] = {
    GoalCode.WEIGHT_LOSS.value: "Снижение веса",
    GoalCode.WEIGHT_GAIN.value: "Набор веса",
    GoalCode.WEIGHT_MAINTAIN.value: "Удержание веса",
    GoalCode.WAIST_REDUCE.value: "Уменьшение талии",
    GoalCode.SHOULDERS_INCREASE.value: "Увеличение плеч",
    GoalCode.HIPS_INCREASE.value: "Увеличение бёдер",
    GoalCode.REGULAR_TIMING.value: "Регулярное питание",
    GoalCode.FEWER_SNACKS.value: "Меньше перекусов",
    GoalCode.NO_SKIP_MAIN.value: "Не пропускать основные приёмы",
    GoalCode.NO_OVEREAT.value: "Не переедать",
    GoalCode.NO_HUNGER.value: "Не быть сильно голодным",
    GoalCode.REGULAR_SPORTS_NUTRITION.value: "Регулярный спортпит",
}

GENDER_LABELS: dict[str, str] = {"male": "Мужской", "female": "Женский"}
