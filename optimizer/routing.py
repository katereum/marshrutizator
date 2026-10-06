"""Stage B — порядок посещения точек внутри дня (раздел 20 ТЗ).

Жадный ближайший сосед + 2-opt (эвристика TSP). Без координат — детерминированная
сортировка по каноническому адресу. Заменяемо на OR-Tools через единую точку
входа `order_day`.
"""
from __future__ import annotations

from .distance import haversine_km
from .models import Point


def order_day(
    visit_ids: list[str],
    points_by_visit: dict[str, Point],
    home: tuple[float, float] | None = None,
    dist=None,
    home_dist=None,
    end_home_dist=None,
    priority: dict[str, float] | None = None,
    priority_weight: float = 0.0,
) -> list[str]:
    """Возвращает visit_ids в порядке посещения.

    `dist` и `home_dist` позволяют подменить прямую (haversine) метрику на
    дорожную. `home_dist` — расстояние от дома СТАРТА дня до точки, а
    `end_home_dist` — от точки до дома ВОЗВРАТА (если None — дом тот же, что
    стартовый, т.е. круг дом→точки→дом). `priority` (point_id -> 0..1) и
    `priority_weight` (в «км») мягко вытаскивают приоритетные точки раньше:
    жадный сосед выбирает `dist - priority_weight * priority`, а 2-opt остаётся
    чисто дорожным.
    """
    if len(visit_ids) <= 2:
        return list(visit_ids)
    if all(points_by_visit[v].has_coords for v in visit_ids):
        return _nn_2opt(visit_ids, points_by_visit, home, dist, home_dist, end_home_dist, priority, priority_weight)
    return sorted(
        visit_ids,
        key=lambda v: (points_by_visit[v].normalized_address, v),
    )


def _pid(visit_id: str) -> str:
    return visit_id.rsplit("#", 1)[0]


def _nn_2opt(
    visit_ids: list[str],
    points: dict[str, Point],
    home: tuple[float, float] | None = None,
    dist=None,
    home_dist=None,
    end_home_dist=None,
    priority: dict[str, float] | None = None,
    priority_weight: float = 0.0,
) -> list[str]:
    if dist is None:
        def dist(a: str, b: str) -> float:
            pa, pb = points[a], points[b]
            return haversine_km(pa.latitude, pa.longitude, pb.latitude, pb.longitude)

    if home_dist is None and home is not None:
        def home_dist(v: str) -> float:
            p = points[v]
            return haversine_km(home[0], home[1], p.latitude, p.longitude)

    use_priority = priority is not None and priority_weight > 0.0

    def prio(v: str) -> float:
        return priority.get(_pid(v), 0.0) if priority is not None else 0.0

    # 1. Жадный ближайший сосед (от дома/приоритетной точки), с мягким приоритетом.
    remaining = set(visit_ids)
    if home_dist is not None:
        if use_priority:
            start = min(remaining, key=lambda v: home_dist(v) - priority_weight * prio(v))
        else:
            start = min(remaining, key=home_dist)
    elif use_priority:
        start = max(remaining, key=prio)
    else:
        start = visit_ids[0]

    order = [start]
    remaining.remove(start)
    cur = start
    while remaining:
        if use_priority:
            nxt = min(remaining, key=lambda v: dist(cur, v) - priority_weight * prio(v))
        else:
            nxt = min(remaining, key=lambda v: dist(cur, v))
        order.append(nxt)
        remaining.remove(nxt)
        cur = nxt

    # 2. Локальная оптимизация 2-opt (чисто по дорогам — приоритет не «размазывает»).
    order = _two_opt(order, dist, home_dist, end_home_dist)
    return order


def _two_opt(order: list[str], dist, home_dist=None, end_home_dist=None) -> list[str]:
    n = len(order)
    if n < 3:
        return order

    def leg(i: int, j: int) -> float:
        """Стоимость перехода между позициями i и j.

        `-1` — виртуальный дом перед маршрутом (старт дня), `n` — дом после
        маршрута (конец дня). Старт считается от дома дня (`home_dist`), конец —
        от дома возврата (`end_home_dist`, если задан; иначе тот же дом).
        """
        a = order[i] if 0 <= i < n else None
        b = order[j] if 0 <= j < n else None
        if a is not None and b is not None:
            return dist(a, b)
        if a is None and b is None:
            return 0.0
        if a is None:
            # виртуальный дом ПЕРЕД маршрутом — старт дня
            return home_dist(b) if home_dist is not None else 0.0
        # b is None: виртуальный дом ПОСЛЕ маршрута — конец дня
        if end_home_dist is not None:
            return end_home_dist(a)
        return home_dist(a) if home_dist is not None else 0.0

    improved = True
    passes = 0
    while improved and passes < 50:
        improved = False
        passes += 1
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                if j - i == 1:
                    continue
                before = leg(i - 1, i) + leg(j, j + 1)
                after = leg(i - 1, j) + leg(i, j + 1)
                if after < before - 1e-9:
                    order[i : j + 1] = list(reversed(order[i : j + 1]))
                    improved = True
    return order
