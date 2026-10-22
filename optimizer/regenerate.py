"""Переделка отдельного дня маршрута (без полной перестройки).

Две операции поверх готового `RouteResult`:
- `reorder_day` — меняет ПОРЯДОК точек дня (вариант через seed-старт);
- `swap_day` — меняет СОСТАВ дня, обмениваясь визитами с пулом
  «Не запланировано» (точки возвращаются в маршрут, «худшие» уходят в пул).

Обе используют те же метрики, что и `build_route` (через `_home_context` и
`_node_distance` из pipeline), поэтому дорожные расстояния, стартовые адреса и
дома возврата учитываются одинаково.
"""
from __future__ import annotations

from .distance import haversine_km
from .models import Point, RouteResult
from .pipeline import _home_context, _node_distance, _pid, _total_km
from .priority import FOCUS_ECONOMY
from .routing import order_day


def _rebuild(result: RouteResult, points, home, home_by_weekday, road_matrix, focus, work_on_weekends):
    """Восстанавливает контекст маршрута (метрики дома и расстояний)."""
    from .assignment import estimate_scale
    from .calendar import working_days

    days = working_days(result.period_start, result.period_end, work_on_weekends)
    node_distance = _node_distance(points, home, road_matrix)
    day_home, day_home_dist, base_home_dist = _home_context(
        points, home, home_by_weekday, node_distance, days
    )
    point_by_id = {p.id: p for p in points}

    def visit_dist(a: str, b: str) -> float:
        return node_distance(_pid(a), _pid(b))

    scale = estimate_scale(node_distance, [p.id for p in points])
    priority_weight = 0.5 * scale if focus != FOCUS_ECONOMY else 0.0

    return {
        "days": days,
        "node_distance": node_distance,
        "day_home": day_home,
        "day_home_dist": day_home_dist,
        "base_home_dist": base_home_dist,
        "point_by_id": point_by_id,
        "visit_dist": visit_dist,
        "priority_weight": priority_weight,
    }


def _points_by_visit(visit_ids, point_by_id):
    return {v: point_by_id[_pid(v)] for v in visit_ids if _pid(v) in point_by_id}


def reorder_day(
    result: RouteResult,
    day_idx: int,
    variant: int,
    *,
    points,
    home,
    home_by_weekday,
    road_matrix,
    focus,
    work_on_weekends,
):
    """Меняет порядок точек дня (variant — номер варианта). Возвращает день."""
    ctx = _rebuild(result, points, home, home_by_weekday, road_matrix, focus, work_on_weekends)
    ds = result.days[day_idx]
    visit_ids = list(ds.ordered_visits)
    if len(visit_ids) <= 2:
        return ds
    h = ctx["day_home"](day_idx)
    home_dist = (lambda v: ctx["day_home_dist"](day_idx, _pid(v))) if h is not None else None
    end_home_dist = (lambda v: ctx["base_home_dist"](_pid(v))) if home is not None else None
    pv = _points_by_visit(visit_ids, ctx["point_by_id"])
    ordered = order_day(
        visit_ids,
        pv,
        h,
        ctx["visit_dist"],
        home_dist,
        end_home_dist=end_home_dist,
        priority=result.priority,
        priority_weight=ctx["priority_weight"],
        variant=variant,
    )
    ds.ordered_visits = ordered
    result.stats.total_km = _total_km(result.days, ctx["node_distance"], ctx["day_home_dist"], ctx["base_home_dist"])
    return ds


def swap_day(
    result: RouteResult,
    day_idx: int,
    variant: int,
    *,
    points,
    home,
    home_by_weekday,
    road_matrix,
    focus,
    work_on_weekends,
):
    """Меняет состав дня: обмен визитами с пулом «Не запланировано».

    Возвращает в маршрут визиты из пула, а в пул отправляет точки дня, дальние
    от его центра («худшие»). Размер дня не меняется (1-в-1). Один и тот же
    point_id не ставится в один день дважды.
    """
    ctx = _rebuild(result, points, home, home_by_weekday, road_matrix, focus, work_on_weekends)
    ds = result.days[day_idx]
    cur = list(ds.ordered_visits)
    pool = list(result.unplanned)
    if not cur or not pool:
        return ds

    point_by_id = ctx["point_by_id"]

    # Точки, которые уже есть в этот день — нельзя ставить их второй раз.
    here = {_pid(v) for v in cur}

    # Кандидаты на вход: из пула, чьей точки ещё нет в этот день.
    in_cand = [v for v in pool if _pid(v) not in here]
    if not in_cand:
        return ds

    # Центроид дня — чтобы «жертвами» (уходящими) стали дальние точки.
    coords = []
    for v in cur:
        p = point_by_id.get(_pid(v))
        if p is not None and p.has_coords:
            coords.append((v, p.latitude, p.longitude))
    if not coords:
        return ds
    clat = sum(c[1] for c in coords) / len(coords)
    clon = sum(c[2] for c in coords) / len(coords)

    def dist_from_center(item):
        return haversine_km(clat, clon, item[1], item[2])

    coords.sort(key=dist_from_center)  # ближние -> дальние
    victims = [v for v, _, _ in coords][::-1]  # дальние -> ближние (худшие первыми)

    # Кандидаты на вход: ближние к центру дня первыми (куст остаётся компактным);
    # вариант сдвигает окно, чтобы каждое нажатие давало немного другой набор.
    def _cdist(v):
        p = point_by_id.get(_pid(v))
        if p is None or not p.has_coords:
            return float("inf")
        return haversine_km(clat, clon, p.latitude, p.longitude)

    in_cand.sort(key=_cdist)
    off = variant % max(1, len(in_cand))
    in_cand = in_cand[off:] + in_cand[:off]

    k = max(1, min(len(cur) // 4, len(in_cand), len(victims)))
    if k < 1:
        return ds

    out = victims[:k]
    inc = in_cand[:k]

    for c, v in zip(inc, out):
        if c not in ds.ordered_visits and v in ds.ordered_visits:
            ds.ordered_visits[ds.ordered_visits.index(v)] = c
            if c in result.unplanned:
                result.unplanned.remove(c)
            result.unplanned.append(v)

    # Пересортировать день после замены состава.
    return reorder_day(
        result,
        day_idx,
        variant,
        points=points,
        home=home,
        home_by_weekday=home_by_weekday,
        road_matrix=road_matrix,
        focus=focus,
        work_on_weekends=work_on_weekends,
    )


def regenerate_day(
    result: RouteResult,
    day_idx: int,
    variant: int,
    *,
    points,
    home,
    home_by_weekday,
    road_matrix,
    focus,
    work_on_weekends,
    swap: bool = True,
):
    """Полная переделка дня: (опционально) состав + порядок. Возвращает день."""
    if swap:
        swap_day(
            result, day_idx, variant,
            points=points, home=home, home_by_weekday=home_by_weekday,
            road_matrix=road_matrix, focus=focus, work_on_weekends=work_on_weekends,
        )
    return reorder_day(
        result, day_idx, variant,
        points=points, home=home, home_by_weekday=home_by_weekday,
        road_matrix=road_matrix, focus=focus, work_on_weekends=work_on_weekends,
    )
