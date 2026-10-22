"""Переделка отдельного дня маршрута (без полной перестройки).

Две операции поверх готового `RouteResult`:
- `reorder_day` — меняет ПОРЯДОК точек дня (вариант через seed-старт);
- `recluster_day` — пересобирает день в ОДИН компактный куст: точки дня и
  соседних незафиксированных дней перераспределяются по близости к «якорю»
  каждого дня (усечённый центроид = доминирующий район). Убирает «круги» —
  день перестаёт смешивать разные концы города. Общее число точек окна не
  меняется (лишние уходят в пул «Не запланировано»).

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


def _trimmed_anchor(coords, frac=0.7):
    """Усечённый центроид: итеративно отбрасываем дальние точки-выбросы, чтобы
    получить центр ДОМИНИРУЮЩЕГО района (а не середину между двумя секторами)."""
    pts = list(coords)
    target = max(2, int(len(coords) * frac))
    while len(pts) > target:
        clat = sum(p[0] for p in pts) / len(pts)
        clon = sum(p[1] for p in pts) / len(pts)
        far = max(pts, key=lambda p: haversine_km(clat, clon, p[0], p[1]))
        pts.remove(far)
    clat = sum(p[0] for p in pts) / len(pts)
    clon = sum(p[1] for p in pts) / len(pts)
    return (clat, clon)


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


def recluster_day(
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
    locked_dates: set[str] | None = None,
):
    """Пересобирает день в один компактный куст (без «кругов»).

    Точки целевого дня и соседних НЕЗАФИКСИРОВАННЫХ дней объединяются в окно и
    перераспределяются: каждый день берёт ближайшие к своему якорю точки. Так
    день, смешавший запад с севером, отдаёт «чужие» точки соседям и забирает
    «свои». Зафиксированные дни не трогаются. Число точек окна не меняется.
    """
    locked_dates = locked_dates or set()
    ds = result.days[day_idx]
    cur = list(ds.ordered_visits)
    if len(cur) < 2:
        return ds

    ctx = _rebuild(result, points, home, home_by_weekday, road_matrix, focus, work_on_weekends)
    point_by_id = ctx["point_by_id"]

    def coords_of(v):
        p = point_by_id.get(_pid(v))
        return (p.latitude, p.longitude) if p is not None and p.has_coords else None

    # Окно: целевой день + соседние незафиксированные дни (до ±2).
    window = [day_idx]
    for delta in (-1, 1, -2, 2):
        nd = day_idx + delta
        if 0 <= nd < len(result.days) and result.days[nd].date.isoformat() not in locked_dates and nd not in window:
            window.append(nd)

    # Все визиты окна (дни + пул) с координатами, без дублей visit_id.
    visits: list[tuple[str, tuple[float, float]]] = []
    seen: set[str] = set()
    for nd in window:
        for v in result.days[nd].ordered_visits:
            if v in seen:
                continue
            seen.add(v)
            c = coords_of(v)
            if c:
                visits.append((v, c))
    for v in result.unplanned:
        if v in seen:
            continue
        seen.add(v)
        c = coords_of(v)
        if c:
            visits.append((v, c))

    if len(visits) < len(cur):
        return ds

    # Якорь каждого дня окна — усечённый центроид его текущих точек.
    anchors = {}
    for nd in window:
        cs = [c for v in result.days[nd].ordered_visits if (c := coords_of(v)) is not None]
        if len(cs) >= 2:
            anchors[nd] = _trimmed_anchor(cs)
        elif cs:
            anchors[nd] = cs[0]
        else:
            anchors[nd] = None

    targets = {nd: len(result.days[nd].ordered_visits) for nd in window}

    # Жадное перераспределение: день окна берёт ближайшие к своему якорю точки.
    # Один point_id не ставится в окно дважды (повтор точки не должен падать в
    # соседний день).
    remaining = list(visits)
    assigned: dict[int, list[str]] = {nd: [] for nd in window}
    used_pids: set[str] = set()
    for nd in window:
        a = anchors[nd]
        if a is None:
            continue
        cand = sorted(remaining, key=lambda vc: haversine_km(a[0], a[1], vc[1][0], vc[1][1]))
        for v, c in cand:
            if len(assigned[nd]) >= targets[nd]:
                break
            if _pid(v) in used_pids:
                continue
            assigned[nd].append(v)
            used_pids.add(_pid(v))
            remaining.remove((v, c))

    # Добрать недозаполненные дни из остатка.
    for nd in window:
        for v, c in list(remaining):
            if len(assigned[nd]) >= targets[nd]:
                break
            if _pid(v) in used_pids:
                continue
            assigned[nd].append(v)
            used_pids.add(_pid(v))
            remaining.remove((v, c))

    # Применить.
    all_assigned: set[str] = set()
    for nd in window:
        result.days[nd].ordered_visits = assigned[nd]
        all_assigned.update(assigned[nd])

    # Пул: старый пул без назначенных + точки окна, оставшиеся неназначенными.
    new_pool = [v for v in result.unplanned if v not in all_assigned]
    for v, c in visits:
        if v not in all_assigned and v not in new_pool:
            new_pool.append(v)
    result.unplanned = new_pool

    # Пересортировать все дни окна.
    for nd in window:
        reorder_day(
            result, nd, variant,
            points=points, home=home, home_by_weekday=home_by_weekday,
            road_matrix=road_matrix, focus=focus, work_on_weekends=work_on_weekends,
        )

    return result.days[day_idx]


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
    locked_dates: set[str] | None = None,
):
    """Полная переделка дня: (опционально) компактный состав + порядок."""
    if swap:
        recluster_day(
            result, day_idx, variant,
            points=points, home=home, home_by_weekday=home_by_weekday,
            road_matrix=road_matrix, focus=focus, work_on_weekends=work_on_weekends,
            locked_dates=locked_dates,
        )
    return reorder_day(
        result, day_idx, variant,
        points=points, home=home, home_by_weekday=home_by_weekday,
        road_matrix=road_matrix, focus=focus, work_on_weekends=work_on_weekends,
    )
