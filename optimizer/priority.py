"""Приоритет точек по «акценту» маршрута (Оценка/Результат).

Результат нормализуется относительно набора (min-max), поэтому не важно, в чём
он выражен — штуки или проценты. Оценка — фиксированная шкала 0..5; пустая
оценка считается «ещё не оценено» и в режиме «проблемные» получает приоритет.
"""
from __future__ import annotations

from .models import Point

FOCUS_ECONOMY = "economy"
FOCUS_FIX = "fix_problems"
FOCUS_TOP = "top_performers"

ALL_FOCUS = (FOCUS_ECONOMY, FOCUS_FIX, FOCUS_TOP)

_SCORE_MAX = 5.0


def build_priority(points: list[Point], focus: str) -> dict[str, float]:
    """Возвращает {point_id: приоритет 0..1}. Выше — раньше в маршруте.

    `focus=economy` — приоритет выключен (все нули, поведение как раньше).
    """
    if focus == FOCUS_ECONOMY:
        return {p.id: 0.0 for p in points}

    results = [p.result for p in points if p.result is not None]
    rmin = min(results) if results else 0.0
    rmax = max(results) if results else 1.0
    rspan = (rmax - rmin) or 1.0

    pr: dict[str, float] = {}
    for p in points:
        nr = ((p.result - rmin) / rspan) if p.result is not None else 0.5

        if p.score is None:
            ns = None
            ungraded = 1.0
        else:
            ns = max(0.0, min(1.0, p.score / _SCORE_MAX))
            ungraded = 0.0

        if focus == FOCUS_FIX:
            s_part = (1.0 - ns) if ns is not None else 0.0
            pr[p.id] = 0.5 * (1.0 - nr) + 0.3 * s_part + 0.2 * ungraded
        elif focus == FOCUS_TOP:
            s_part = ns if ns is not None else 0.5
            pr[p.id] = 0.6 * nr + 0.4 * s_part
        else:
            pr[p.id] = 0.0
    return pr
