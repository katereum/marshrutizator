"""Автопроверка результата и оценка качества маршрута (раздел 23, 35 ТЗ)."""
from __future__ import annotations

from collections import defaultdict

from .models import Point, RouteResult


def _point_id(visit_id: str) -> str:
    return visit_id.rsplit("#", 1)[0]


def validate_route(result: RouteResult, expected_visits: dict[str, int]) -> list[str]:
    """Проверяет обязательные инварианты результата."""
    violations: list[str] = []

    seen: dict[str, int] = defaultdict(int)
    all_ids: list[str] = []
    for day in result.days:
        if not (result.period_start <= day.date <= result.period_end):
            violations.append(f"Дата {day.date} вне периода")
        if day.date.weekday() >= 5:
            violations.append(f"Дата {day.date} — выходной")
        for vid in day.ordered_visits:
            seen[_point_id(vid)] += 1
            all_ids.append(vid)

    if len(all_ids) != len(set(all_ids)):
        violations.append("Найдены дубликаты visit_id")

    for pid, required in expected_visits.items():
        got = seen.get(pid, 0)
        if got < required:
            violations.append(f"Точка {pid}: потеряно посещений ({got} < {required})")
        elif got > required:
            violations.append(f"Точка {pid}: лишние посещения ({got} > {required})")

    return violations


def _load_balance(result: RouteResult) -> float:
    loads = result.stats.per_day_load
    n = len(loads)
    total = sum(loads)
    if n <= 1 or total == 0:
        return 1.0
    mean = total / n
    var = sum((l - mean) ** 2 for l in loads) / n
    std = var ** 0.5
    return max(0.0, 1.0 - std / mean)


def _cyclic_quality(result: RouteResult) -> float:
    n_days = len(result.days)
    day_of: dict[str, list[int]] = defaultdict(list)
    for di, day in enumerate(result.days):
        for vid in day.ordered_visits:
            day_of[_point_id(vid)].append(di)

    scores: list[float] = []
    for days in day_of.values():
        days = sorted(days)
        f = len(days)
        if f <= 1:
            scores.append(1.0)
            continue
        ideal_gap = (n_days - 1) / (f - 1)
        gaps = [days[i + 1] - days[i] for i in range(f - 1)]
        dev = sum(abs(g - ideal_gap) for g in gaps) / (f - 1)
        scores.append(max(0.0, 1.0 - dev / max(1, n_days)))
    return sum(scores) / len(scores) if scores else 1.0


def _compactness(result: RouteResult, cluster: dict[str, int]) -> float:
    if not result.days:
        return 1.0
    good = 0
    for day in result.days:
        day_clusters = {cluster.get(_point_id(v), -1) for v in day.ordered_visits}
        if len(day_clusters) <= 2:
            good += 1
    return good / len(result.days)


def route_score(result: RouteResult, points: list[Point], cluster: dict[str, int]) -> float:
    """Оценка качества маршрута (выше = лучше). Нарушения доминируют."""
    balance = _load_balance(result)
    cyclic = _cyclic_quality(result)
    compact = _compactness(result, cluster)
    violations = len(result.stats.violations)
    return balance + cyclic + compact - 100.0 * violations
