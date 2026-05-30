"""Базовые медицинские показатели, выводимые из профиля и последних замеров.

Источники классификаций:
- ИМТ (BMI): ВОЗ — https://www.who.int/health-topics/obesity
- Соотношение талия/рост (WHtR): Ashwell & Hsieh, 2005
- Соотношение талия/бёдра (WHR): пороги ВОЗ по полу
- BMR (базальный метаболизм): формула Mifflin-St Jeor (1990)
- Оценка % жира: формула Deurenberg (1991)
"""
from __future__ import annotations

from dataclasses import dataclass

from app.db.models import Gender, Measurement


@dataclass
class Metric:
    label: str
    value: str
    norm: str
    success: bool | None  # True/False/None — для подсветки строк


@dataclass
class MetricsResult:
    metrics: list[Metric]


def _bmi(weight_kg: float, height_cm: float) -> float:
    h = height_cm / 100.0
    return weight_kg / (h * h)


def _bmi_classify(bmi: float) -> tuple[str, bool | None]:
    """Возвращает (категория, success)."""
    if bmi < 18.5:
        return ("дефицит массы", False)
    if bmi < 25.0:
        return ("норма", True)
    if bmi < 30.0:
        return ("избыточная масса", False)
    return ("ожирение", False)


def _whtr_classify(whtr: float) -> tuple[str, bool | None]:
    if whtr < 0.4:
        return ("низкий", None)
    if whtr < 0.5:
        return ("здоровый", True)
    if whtr < 0.6:
        return ("повышенный риск", False)
    return ("высокий риск", False)


def _whr_classify(whr: float, gender: str) -> tuple[str, bool | None]:
    """Пороги ВОЗ. Мужчины: <0.9 норма, 0.9-0.99 повышенный, ≥1.0 высокий.
    Женщины: <0.8 норма, 0.8-0.84 повышенный, ≥0.85 высокий."""
    if gender == Gender.MALE.value:
        if whr < 0.9:
            return ("норма", True)
        if whr < 1.0:
            return ("повышенный", False)
        return ("высокий", False)
    # female
    if whr < 0.8:
        return ("норма", True)
    if whr < 0.85:
        return ("повышенный", False)
    return ("высокий", False)


def _bmr_mifflin(weight_kg: float, height_cm: float, age: int, gender: str) -> float:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + 5 if gender == Gender.MALE.value else base - 161


def _body_fat_deurenberg(bmi: float, age: int, gender: str) -> float:
    sex = 1 if gender == Gender.MALE.value else 0
    return 1.20 * bmi + 0.23 * age - 10.8 * sex - 5.4


def _bf_classify(bf: float, gender: str, age: int) -> tuple[str, bool | None]:
    """Очень грубо. Норма у мужчин 10–22% (молодой), у женщин 18–32%.
    Стандартные диапазоны (ACE):
      Male: athletic 6-13, fitness 14-17, accept 18-24, obese 25+
      Female: athletic 14-20, fitness 21-24, accept 25-31, obese 32+
    """
    if gender == Gender.MALE.value:
        if bf < 14:
            return ("атлетический", True)
        if bf < 18:
            return ("спортивный", True)
        if bf < 25:
            return ("норма", True)
        return ("выше нормы", False)
    if bf < 21:
        return ("атлетический", True)
    if bf < 25:
        return ("спортивный", True)
    if bf < 32:
        return ("норма", True)
    return ("выше нормы", False)


def compute_metrics(
    *,
    height_cm: float,
    age: int,
    gender: str,
    latest: Measurement | None,
) -> MetricsResult:
    """latest — последний по периоду замер; обычно берётся последний из measurements за период."""
    out: list[Metric] = []
    if latest is None:
        return MetricsResult(metrics=out)

    weight = latest.weight_kg
    waist = latest.waist_cm
    hips = latest.hips_cm

    # ИМТ
    if weight is not None:
        bmi = _bmi(weight, height_cm)
        cat, ok = _bmi_classify(bmi)
        out.append(Metric(
            label="ИМТ",
            value=f"{bmi:.1f} — {cat}",
            norm="18.5–24.9",
            success=ok,
        ))

    # Талия/рост
    if waist is not None:
        whtr = waist / height_cm
        cat, ok = _whtr_classify(whtr)
        out.append(Metric(
            label="Талия / рост",
            value=f"{whtr:.2f} — {cat}",
            norm="< 0.5",
            success=ok,
        ))

    # Талия/бёдра
    if waist is not None and hips is not None and hips > 0:
        whr = waist / hips
        cat, ok = _whr_classify(whr, gender)
        norm = "< 0.9" if gender == Gender.MALE.value else "< 0.85"
        out.append(Metric(
            label="Талия / бёдра",
            value=f"{whr:.2f} — {cat}",
            norm=norm,
            success=ok,
        ))

    # BMR
    if weight is not None:
        bmr = _bmr_mifflin(weight, height_cm, age, gender)
        out.append(Metric(
            label="BMR (базальный метаболизм)",
            value=f"{bmr:.0f} ккал/день",
            norm="—",
            success=None,
        ))
        # Поддержание веса при умеренной активности (×1.4)
        tdee = bmr * 1.4
        out.append(Metric(
            label="TDEE (поддержание)",
            value=f"≈ {tdee:.0f} ккал/день",
            norm="при низкой активности",
            success=None,
        ))

    # % жира (оценка)
    if weight is not None:
        bmi = _bmi(weight, height_cm)
        bf = _body_fat_deurenberg(bmi, age, gender)
        bf = max(0.0, bf)
        cat, ok = _bf_classify(bf, gender, age)
        norm = "10–22% (муж)" if gender == Gender.MALE.value else "18–32% (жен)"
        out.append(Metric(
            label="Жир (оценка)",
            value=f"{bf:.1f}% — {cat}",
            norm=norm,
            success=ok,
        ))

    return MetricsResult(metrics=out)
