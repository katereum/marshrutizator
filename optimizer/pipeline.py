"""Оркестрация полного конвейера построения маршрута.

Конвейер (раздел 29 ТЗ): кластеризация -> размножение визитов -> Stage A ->
Stage B -> валидация -> статистика. Выполняется независимо для каждого
сотрудника (R2).
"""
from __future__ import annotations

from datetime import date

from .assignment import assign_days, consolidate_clusters, consolidate_locations, estimate_scale
from .calendar import working_days
from .clusterer import cluster_points
from .distance import haversine_km
from .models import HOME_ID, DaySchedule, Point, RouteResult, RouteStats, Visit
from .priority import FOCUS_ECONOMY, build_priority
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


def _total_km(schedules: list[DaySchedule], node_distance, day_home_dist, end_home_dist=None) -> float:
    """Суммарный километраж всех дней (дом старта -> точки -> дом возврата).

    `day_home_dist(day_idx, point_id) -> км` — расстояние от дома старта дня до
    точки (0, если дома для дня нет). `end_home_dist(point_id) -> км` — от точки
    до дома возврата (если None — возврат в тот же дом, что и старт).
    """
    total = 0.0
    for idx, day in enumerate(schedules):
        ids = day.ordered_visits
        if not ids:
            continue
        total += day_home_dist(idx, _pid(ids[0]))
        if end_home_dist is not None:
            total += end_home_dist(_pid(ids[-1]))
        else:
            total += day_home_dist(idx, _pid(ids[-1]))
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
    home_by_weekday: dict[int, tuple[float, float]] | None = None,
    road_matrix: dict | None = None,
    focus: str = FOCUS_ECONOMY,
    caps: list[int] | None = None,
) -> RouteResult:
    """Строит месячный маршрут для набора точек одного сотрудника.

    `home` — базовый дом (по умолчанию для всех дней). `home_by_weekday` —
    переопределение дома для конкретного дня недели (0=Пн..6=Вс).
    """
    days = working_days(period_start, period_end, work_on_weekends)
    if not days:
        raise ValueError("В периоде нет рабочих дней")
    n_days = len(days)

    node_distance = _node_distance(points, home, road_matrix)
    cluster = cluster_points(points, eps_km, node_distance)
    visits, warnings = expand_visits(points, n_days, cluster)

    coords: dict[str, tuple[float, float]] = {}
    for p in points:
        if p.latitude is not None and p.longitude is not None:
            coords[p.id] = (p.latitude, p.longitude)
    if caps is not None and sum(caps) < len(visits):
        floor = (len(visits) + n_days - 1) // n_days
        warnings.append(
            f"Лимит точек в день не вмещает все визиты: {len(visits)} визитов при "
            f"суммарной ёмкости {sum(caps)}. Лимиты смягчены до минимум {floor} в день."
        )
    day_visits, load = assign_days(visits, n_days, dist_fn=node_distance, coords=coords, caps=caps)
    # Точки одного места (одинаковые координаты) — в один день, а не вразнобой.
    day_visits, load = consolidate_locations(day_visits, load, visits, coords)
    # Точки одного района (метро) — в смежные дни, а не разбросаны по месяцу.
    day_visits, load = consolidate_clusters(day_visits, load, visits, caps)

    point_by_id = {p.id: p for p in points}
    points_by_visit = {v.visit_id: point_by_id[v.point_id] for v in visits}

    visit_dist = lambda a, b: node_distance(_pid(a), _pid(b))

    # Дом конкретного дня: переопределение по дню недели, иначе базовый дом.
    def day_home(d: int):
        if home_by_weekday is None:
            return home
        return home_by_weekday.get(days[d].weekday(), home)

    def day_home_dist(idx: int, pid: str) -> float:
        h = day_home(idx)
        if h is None:
            return 0.0
        if home is not None and h == home:
            return node_distance(HOME_ID, pid)
        p = point_by_id.get(pid)
        if p is None or not p.has_coords:
            return 0.0
        return haversine_km(h[0], h[1], p.latitude, p.longitude)

    def base_home_dist(pid: str) -> float:
        """Расстояние от точки до БАЗОВОГО дома (возврат всегда туда)."""
        if home is None:
            return 0.0
        return node_distance(HOME_ID, pid)

    # Мягкий приоритет: вес λ = половина типичного расстояния между соседними точками,
    # чтобы приоритет переставлял точки внутри района, не ломая географию.
    priority = build_priority(points, focus)
    scale = estimate_scale(node_distance, [p.id for p in points])
    priority_weight = 0.5 * scale if focus != FOCUS_ECONOMY else 0.0

    schedules: list[DaySchedule] = []
    for d in range(n_days):
        h = day_home(d)
        home_dist = (lambda v, d=d: day_home_dist(d, _pid(v))) if h is not None else None
        end_home_dist = (lambda v: base_home_dist(_pid(v))) if home is not None else None
        ordered = order_day(
            day_visits[d], points_by_visit, h, visit_dist, home_dist,
            end_home_dist=end_home_dist,
            priority=priority, priority_weight=priority_weight,
        )
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
        focus=focus,
        priority=priority,
    )

    expected = {p.id: min(p.frequency, n_days) for p in points}
    violations = validate_route(result, expected)
    result.stats = RouteStats(
        total_points=len(points),
        total_visits=len(visits),
        per_day_load=load,
        violations=violations,
        total_km=_total_km(schedules, node_distance, day_home_dist, base_home_dist),
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
    home_by_weekday: dict[int, tuple[float, float]] | None = None,
    road_matrix: dict | None = None,
    focus: str = FOCUS_ECONOMY,
    caps: list[int] | None = None,
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
                home_by_weekday=home_by_weekday,
                road_matrix=road_matrix,
                focus=focus,
                caps=caps,
            )
        )
    return results
