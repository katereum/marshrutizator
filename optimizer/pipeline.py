"""Оркестрация полного конвейера построения маршрута.

Конвейер (раздел 29 ТЗ): кластеризация -> размножение визитов -> Stage A ->
Stage B -> валидация -> статистика. Выполняется независимо для каждого
сотрудника (R2).
"""
from __future__ import annotations

from datetime import date

from .assignment import assign_days
from .calendar import working_days
from .clusterer import cluster_points
from .distance import haversine_km
from .models import HOME_ID, DaySchedule, Point, RouteResult, RouteStats, Visit
from .routing import order_day
from .validator import route_score, validate_route
from .visits import expand_visits


def _pid(visit_id: str) -> str:
    return visit_id.rsplit("#", 1)[0]


def _node_distance(
    points: list[Point],
    home: tuple[float, float] | None,
    road_matrix: dict | None,
):
    """Метрика расстояния по id узлов (точка или HOME_ID).

    Если задан `road_matrix` (id -> id -> км), используется он; иначе — haversine.
    """
    by_id = {p.id: p for p in points}

    def coords(node: str) -> tuple[float, float] | None:
        if node == HOME_ID:
            return home
        p = by_id.get(node)
        return (p.latitude, p.longitude) if p is not None and p.has_coords else None

    def distance(a: str, b: str) -> float:
        if road_matrix is not None:
            v = road_matrix.get((a, b))
            if v is not None:
                return v
        ca, cb = coords(a), coords(b)
        if ca is None or cb is None:
            return 0.0
        return haversine_km(ca[0], ca[1], cb[0], cb[1])

    return distance


def _total_km(schedules: list[DaySchedule], home, node_distance) -> float:
    """Суммарный километраж всех дней (дом -> точки -> дом)."""
    total = 0.0
    for day in schedules:
        ids = day.ordered_visits
        if not ids:
            continue
        if home is not None:
            total += node_distance(HOME_ID, _pid(ids[0]))
            total += node_distance(_pid(ids[-1]), HOME_ID)
        for a, b in zip(ids, ids[1:]):
            total += node_distance(_pid(a), _pid(b))
    return total


def build_route(
    points: list[Point],
    period_start: date,
    period_end: date,
    *,
    job_id: str = "",
    trade_rep_code: str = "",
    eps_km: float = 5.0,
    work_on_weekends: bool = False,
    home: tuple[float, float] | None = None,
    road_matrix: dict | None = None,
) -> RouteResult:
    """Строит месячный маршрут для набора точек одного сотрудника."""
    days = working_days(period_start, period_end, work_on_weekends)
    if not days:
        raise ValueError("В периоде нет рабочих дней")
    n_days = len(days)

    node_distance = _node_distance(points, home, road_matrix)
    cluster = cluster_points(points, eps_km, node_distance)
    visits, warnings = expand_visits(points, n_days, cluster)

    coords = {p.id: (p.latitude, p.longitude) for p in points if p.has_coords}
    day_visits, load = assign_days(visits, n_days, dist_fn=node_distance, coords=coords)

    point_by_id = {p.id: p for p in points}
    points_by_visit = {v.visit_id: point_by_id[v.point_id] for v in visits}

    visit_dist = lambda a, b: node_distance(_pid(a), _pid(b))
    visit_home_dist = (lambda v: node_distance(HOME_ID, _pid(v))) if home is not None else None

    schedules: list[DaySchedule] = []
    for d in range(n_days):
        ordered = order_day(day_visits[d], points_by_visit, home, visit_dist, visit_home_dist)
        schedules.append(
            DaySchedule(date=days[d], weekday=days[d].weekday(), ordered_visits=ordered)
        )

    result = RouteResult(
        job_id=job_id,
        trade_rep_code=trade_rep_code,
        period_start=period_start,
        period_end=period_end,
        days=schedules,
        warnings=warnings,
    )

    expected = {p.id: min(p.frequency, n_days) for p in points}
    violations = validate_route(result, expected)
    result.stats = RouteStats(
        total_points=len(points),
        total_visits=len(visits),
        per_day_load=load,
        violations=violations,
        total_km=_total_km(schedules, home, node_distance),
    )
    result.stats.score = route_score(result, points, cluster)
    return result


def build_routes(
    points: list[Point],
    period_start: date,
    period_end: date,
    *,
    job_id: str = "",
    eps_km: float = 5.0,
    work_on_weekends: bool = False,
    home: tuple[float, float] | None = None,
    road_matrix: dict | None = None,
) -> list[RouteResult]:
    """Строит маршруты, разбивая базу по `Код торгового представителя` (R2)."""
    groups: dict[str, list[Point]] = {}
    for p in points:
        groups.setdefault(p.trade_rep_code, []).append(p)

    results: list[RouteResult] = []
    for code, group in groups.items():
        results.append(
            build_route(
                group,
                period_start,
                period_end,
                job_id=job_id,
                trade_rep_code=code,
                eps_km=eps_km,
                work_on_weekends=work_on_weekends,
                home=home,
                road_matrix=road_matrix,
            )
        )
    return results
