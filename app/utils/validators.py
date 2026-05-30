from __future__ import annotations

import pytz


def parse_positive_float(text: str, low: float, high: float) -> float | None:
    text = text.strip().replace(",", ".")
    try:
        v = float(text)
    except ValueError:
        return None
    if not (low <= v <= high):
        return None
    return v


def parse_positive_int(text: str, low: int, high: int) -> int | None:
    text = text.strip()
    try:
        v = int(text)
    except ValueError:
        return None
    if not (low <= v <= high):
        return None
    return v


def is_valid_tz(name: str) -> bool:
    return name in pytz.all_timezones_set
