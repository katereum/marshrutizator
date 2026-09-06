"""Календарь рабочих дней (раздел 22 ТЗ, решение R4)."""
from __future__ import annotations

from datetime import date, timedelta


def working_days(start: date, end: date, work_on_weekends: bool = False) -> list[date]:
    """Список рабочих дней периода.

    По умолчанию выходные (Сб/Вс) исключены (R4). `work_on_weekends=True`
    оставляет возможность расширения в будущем.
    """
    if end < start:
        raise ValueError("period_end раньше period_start")
    days: list[date] = []
    d = start
    while d <= end:
        if work_on_weekends or d.weekday() < 5:  # Пн=0 .. Пт=4
            days.append(d)
        d += timedelta(days=1)
    return days
