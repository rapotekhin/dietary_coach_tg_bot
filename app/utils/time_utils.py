from __future__ import annotations

import re
from datetime import datetime

import pytz

CAPTION_TIME_RE = re.compile(r"@(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})")


def parse_caption_time(caption: str | None, tz_name: str) -> datetime | None:
    """Извлекает дату/время из caption формата @DD.MM.YYYY HH:MM. Возвращает naive datetime в локальном TZ."""
    if not caption:
        return None
    m = CAPTION_TIME_RE.search(caption)
    if not m:
        return None
    day, month, year, hour, minute = (int(x) for x in m.groups())
    try:
        tz = pytz.timezone(tz_name)
        return tz.localize(datetime(year, month, day, hour, minute)).replace(tzinfo=None)
    except (ValueError, pytz.UnknownTimeZoneError):
        return None


def to_local(message_dt: datetime, tz_name: str) -> datetime:
    """Конвертирует UTC datetime в локальный TZ (возвращает naive)."""
    tz = pytz.timezone(tz_name)
    if message_dt.tzinfo is None:
        message_dt = pytz.utc.localize(message_dt)
    return message_dt.astimezone(tz).replace(tzinfo=None)


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y %H:%M")


def fmt_date(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y")


def parse_period(text: str) -> tuple[datetime, datetime] | None:
    """Парсит период вида DDMMYYYY-DDMMYYYY → (start_dt_00:00, end_dt_23:59)."""
    text = text.strip()
    m = re.fullmatch(r"(\d{2})(\d{2})(\d{4})-(\d{2})(\d{2})(\d{4})", text)
    if not m:
        return None
    d1, m1, y1, d2, m2, y2 = (int(x) for x in m.groups())
    try:
        start = datetime(y1, m1, d1, 0, 0, 0)
        end = datetime(y2, m2, d2, 23, 59, 59)
    except ValueError:
        return None
    if end < start:
        return None
    return start, end
