"""Генерирует синтетические данные за 3 месяца и собирает PDF-отчёт.

Запуск:
    python scripts/generate_test_report.py [--out reports/sample_report.pdf] [--seed 42]

Никаких записей в БД не делает — данные хранятся только в памяти.
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.models import GoalCode, Meal, Measurement, MealType  # noqa: E402
from app.services.report_service import ReportData, build_pdf  # noqa: E402


def _gauss_int(mean: float, sd: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(random.gauss(mean, sd)))))


def _make_meal(
    meal_id: int,
    user_id: int,
    occurred_at: datetime,
    meal_type: str,
    hunger: int,
    satiety: int,
) -> Meal:
    m = Meal(
        id=meal_id,
        user_id=user_id,
        chat_id=1,
        message_id=meal_id,
        meal_type=meal_type,
        hunger=hunger,
        satiety=satiety,
        text=None,
        occurred_at=occurred_at,
        media_group_id=None,
    )
    m.photos = []
    return m


def generate_meals(user_id: int, start: datetime, days: int) -> list[Meal]:
    meals: list[Meal] = []
    next_id = 1

    # Якорные времена основных приёмов с разбросом
    anchors = {
        MealType.BREAKFAST.value: (8 * 60 + 30, 40),  # 08:30 ± 40 min
        MealType.LUNCH.value: (13 * 60 + 30, 50),
        MealType.DINNER.value: (19 * 60 + 30, 45),
    }

    for d in range(days):
        day = start + timedelta(days=d)

        # Основные приёмы пищи. С шансом 8% — пропуск.
        for mt, (mean_min, sd_min) in anchors.items():
            if random.random() < 0.08:
                continue
            minute_of_day = _gauss_int(mean_min, sd_min, 5 * 60, 23 * 60 + 30)
            dt = day.replace(hour=minute_of_day // 60, minute=minute_of_day % 60)

            # Голод: чаще 2-3, иногда 4
            hunger = _gauss_int(3, 1.0, 1, 5)
            # Насыщение: чаще 3, иногда 2 или 4
            satiety = _gauss_int(3, 0.9, 1, 5)

            meals.append(_make_meal(next_id, user_id, dt, mt, hunger, satiety))
            next_id += 1

        # Перекус — 35% дней, обычно днём
        if random.random() < 0.35:
            minute_of_day = _gauss_int(16 * 60, 90, 10 * 60, 22 * 60)
            dt = day.replace(hour=minute_of_day // 60, minute=minute_of_day % 60)
            hunger = _gauss_int(2, 0.8, 1, 5)
            satiety = _gauss_int(2, 0.7, 1, 4)
            meals.append(_make_meal(next_id, user_id, dt, MealType.SNACK.value, hunger, satiety))
            next_id += 1

        # Спортпит — 5 раз в неделю (пн-пт), утром или после обеда
        if day.weekday() < 5:
            minute_of_day = random.choice([9 * 60 + 0, 14 * 60 + 0, 18 * 60 + 30])
            dt = day.replace(hour=minute_of_day // 60, minute=minute_of_day % 60)
            meals.append(
                _make_meal(
                    next_id, user_id, dt, MealType.SPORTS_NUTRITION.value,
                    hunger=_gauss_int(2, 0.5, 1, 4),
                    satiety=_gauss_int(2, 0.5, 1, 4),
                )
            )
            next_id += 1

    meals.sort(key=lambda m: m.occurred_at)
    return meals


def generate_measurements(user_id: int, start: datetime, days: int) -> list[Measurement]:
    """Замеры раз в ~14 дней. Вес и талия плавно уменьшаются, плечи слегка растут."""
    measurements: list[Measurement] = []
    weight = 82.0
    waist = 86.0
    shoulders = 115.0
    hips = 102.0
    next_id = 1

    d = 0
    while d <= days:
        when = start + timedelta(days=d)
        measurements.append(
            Measurement(
                id=next_id,
                user_id=user_id,
                shoulders_cm=round(shoulders + random.uniform(-0.3, 0.3), 1),
                waist_cm=round(waist + random.uniform(-0.3, 0.3), 1),
                hips_cm=round(hips + random.uniform(-0.3, 0.3), 1),
                weight_kg=round(weight + random.uniform(-0.4, 0.4), 1),
                measured_at=when,
            )
        )
        next_id += 1
        # тренды
        weight -= random.uniform(0.4, 0.9)
        waist -= random.uniform(0.2, 0.5)
        shoulders += random.uniform(0.0, 0.2)
        hips -= random.uniform(0.0, 0.2)
        d += random.randint(13, 16)

    return measurements


def main() -> None:
    parser = argparse.ArgumentParser(description="Сгенерировать тестовый PDF-отчёт")
    parser.add_argument("--out", default="reports/sample_report.pdf", help="путь к PDF")
    parser.add_argument("--seed", type=int, default=42, help="seed для random")
    parser.add_argument("--days", type=int, default=92, help="длина периода в днях (по умолчанию ~3 месяца)")
    args = parser.parse_args()

    random.seed(args.seed)

    end = datetime.now().replace(hour=23, minute=59, second=0, microsecond=0)
    start = (end - timedelta(days=args.days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    user_id = 1

    meals = generate_meals(user_id, start, args.days)
    measurements = generate_measurements(user_id, start, args.days)

    goals = {
        GoalCode.WEIGHT_LOSS.value,
        GoalCode.WAIST_REDUCE.value,
        GoalCode.SHOULDERS_INCREASE.value,
        GoalCode.REGULAR_TIMING.value,
        GoalCode.NO_SKIP_MAIN.value,
        GoalCode.FEWER_SNACKS.value,
        GoalCode.NO_OVEREAT.value,
        GoalCode.NO_HUNGER.value,
        GoalCode.REGULAR_SPORTS_NUTRITION.value,
    }

    report = ReportData(
        period_start=start,
        period_end=end,
        goals=goals,
        meals=meals,
        measurements=measurements,
        prev_measurement=None,
        height_cm=178.0,
        age=32,
        gender="male",
    )

    pdf = build_pdf(report)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(pdf.read())

    print(f"PDF generated: {out_path}")
    print(f"Period: {start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')} ({args.days} days)")
    print(f"Meals: {len(meals)}, measurements: {len(measurements)}")
    print("Goal evaluations:")
    for ev in report.evaluations:
        status = "OK" if ev.success is True else ("FAIL" if ev.success is False else "--")
        print(f"  [{status}] {ev.label}: {ev.value}")


if __name__ == "__main__":
    main()
