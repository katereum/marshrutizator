"""Приоритет точек по «акценту» маршрута (Оценка/Результат).

Идея (см. docs/algorithm.md, раздел «Приоритет точек»):

- **Оценка** — субъективное качество точки, шкала 0..5 (выше = лучше).
  Пустая ячейка или значение «нет» = «не оценено».
- **Результат** — объективный показатель (штуки, %, доля — неважно; выше = лучше).
  Единицы не важны: он нормализуется min-max по набору, поэтому «0.9» и «90%»
  дают одинаковый ранг.

Из двух полей собирается единый **индекс 0..1** (чем выше — тем раньше точка в
маршруте). Индекс действует *мягко*: он подтягивает приоритетные точки вперёд
внутри дня, но не ломает географию (см. optimizer/routing.py `order_day` —
приоритет вычитается из дорожного расстояния с весом `priority_weight`). Так
достигается цель «покрыть всю территорию И поехать туда, где нужна реакция»:
территорию покрывает кластеризация и распределение по дням, а порядок внутри
дня — приоритет.

Режимы (focus):
- `economy` — приоритет выключен (все нули), чистая экономия бензина;
- `fix_problems` — раньше проблемные (низкий результат/оценка или «не оценено»);
- `top_performers` — раньше лучшие (высокий результат/оценка).
"""
from __future__ import annotations

from .models import Point

FOCUS_ECONOMY = "economy"
FOCUS_FIX = "fix_problems"
FOCUS_TOP = "top_performers"

ALL_FOCUS = (FOCUS_ECONOMY, FOCUS_FIX, FOCUS_TOP)

_SCORE_MAX = 5.0

# Веса «индекса» приоритета. Результат весит больше оценки, потому что он
# объективнее; «не оценено» — отдельный вклад только в режиме «проблемные»
# (не оценено = точка требует внимания, чтобы понять, что с ней).
_W_RESULT_FIX = 0.5   # вклад низкого результата
_W_SCORE_FIX = 0.3    # вклад низкой оценки
_W_UNGRADED_FIX = 0.2  # вклад «не оценено»
_W_RESULT_TOP = 0.6   # вклад высокого результата
_W_SCORE_TOP = 0.4    # вклад высокой оценки


def _result_minmax(points: list[Point]) -> tuple[float, float]:
    """(rmin, rspan) по набору; rspan никогда не 0, чтобы не делить на ноль."""
    results = [p.result for p in points if p.result is not None]
    rmin = min(results) if results else 0.0
    rmax = max(results) if results else 1.0
    return rmin, (rmax - rmin) or 1.0


def build_priority(points: list[Point], focus: str) -> dict[str, float]:
    """Возвращает {point_id: приоритет 0..1}. Выше — раньше в маршруте.

    `focus=economy` — приоритет выключен (все нули, поведение как раньше).
    """
    if focus == FOCUS_ECONOMY:
        return {p.id: 0.0 for p in points}

    rmin, rspan = _result_minmax(points)

    pr: dict[str, float] = {}
    for p in points:
        # Нормированный результат: 1 = лучший в наборе; None -> 0.5 (нейтрально).
        nr = ((p.result - rmin) / rspan) if p.result is not None else 0.5

        if p.score is None:
            ns = None          # оценка неизвестна
            ungraded = 1.0
        else:
            ns = max(0.0, min(1.0, p.score / _SCORE_MAX))
            ungraded = 0.0

        if focus == FOCUS_FIX:
            # Чем хуже (ниже результат/оценка) или чем меньше известно — тем раньше.
            s_part = (1.0 - ns) if ns is not None else 0.0
            pr[p.id] = (
                _W_RESULT_FIX * (1.0 - nr)
                + _W_SCORE_FIX * s_part
                + _W_UNGRADED_FIX * ungraded
            )
        elif focus == FOCUS_TOP:
            s_part = ns if ns is not None else 0.5
            pr[p.id] = _W_RESULT_TOP * nr + _W_SCORE_TOP * s_part
        else:
            pr[p.id] = 0.0
    return pr
