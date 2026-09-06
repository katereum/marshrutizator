"""Размножение точек в визиты по цикличности (раздел 19 ТЗ, решение R5)."""
from __future__ import annotations

from .models import Point, Visit


def expand_visits(
    points: list[Point],
    working_day_count: int,
    cluster: dict[str, int] | None = None,
) -> tuple[list[Visit], list[str]]:
    """Создаёт слоты-визиты.

    Для точки с цикличностью `f` создаётся `min(f, working_day_count)` визитов:
    если `f` превышает число рабочих дней, визиты укладываются «сколько влезает»
    и формируется предупреждение (R5).
    """
    if working_day_count < 1:
        raise ValueError("Нет рабочих дней в периоде")
    cluster = cluster or {}
    visits: list[Visit] = []
    warnings: list[str] = []
    for p in points:
        effective = min(p.frequency, working_day_count)
        if p.frequency > working_day_count:
            warnings.append(
                f"Точка {p.id}: цикличность {p.frequency} > рабочих дней "
                f"{working_day_count}, учтено {effective}"
            )
        cid = cluster.get(p.id, -1)
        for slot in range(effective):
            visits.append(Visit(point_id=p.id, slot_index=slot, cluster_id=cid))
    return visits, warnings
