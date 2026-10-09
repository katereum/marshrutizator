"""Географическая кластеризация точек (раздел 15 ТЗ).

Если у всех точек есть координаты — кластеризация по расстоянию (связные
компоненты графа соседства в радиусе eps). Иначе — fallback-группировка по
(населённый пункт, станция метро), см. решение R1.
"""
from __future__ import annotations

from .distance import haversine_km
from .models import Point


def cluster_points(points: list[Point], eps_km: float = 5.0, dist_fn=None) -> dict[str, int]:
    """Возвращает отображение point_id -> cluster_id.

    Дискретный «район» = станция метро (или населённый пункт). Кластеризация по
    расстоянию здесь НЕ годится: в плотном городе точки выстраиваются в цепочки
    меньше eps и склеиваются в один гигантский кластер (весь город), из-за чего
    «районы» теряют смысл. Поэтому когда есть метро — группируем по нему; иначе
    (нет метро) — по расстоянию, `dist_fn` позволяет использовать дорожные
    расстояния вместо прямой (haversine).
    """
    if not points:
        return {}
    if any(p.metro.strip() for p in points):
        return _cluster_by_address(points)
    if all(p.has_coords for p in points):
        return _cluster_by_grid(points, eps_km / 111.0)
    return _cluster_by_address(points)


def _cluster_by_distance(points: list[Point], eps_km: float, dist_fn=None) -> dict[str, int]:
    n = len(points)

    def d(i: int, j: int) -> float:
        if dist_fn is not None:
            return dist_fn(points[i].id, points[j].id)
        return haversine_km(
            points[i].latitude, points[i].longitude,
            points[j].latitude, points[j].longitude,
        )

    adj: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if d(i, j) <= eps_km:
                adj[i].append(j)
                adj[j].append(i)

    cluster: dict[str, int] = {}
    visited = [False] * n
    label = 0
    for i in range(n):
        if visited[i]:
            continue
        stack = [i]
        visited[i] = True
        while stack:
            x = stack.pop()
            cluster[points[x].id] = label
            for y in adj[x]:
                if not visited[y]:
                    visited[y] = True
                    stack.append(y)
        label += 1
    return cluster


def _cluster_by_address(points: list[Point]) -> dict[str, int]:
    cluster: dict[str, int] = {}
    seen: dict[tuple[str, str], int] = {}
    next_id = 0
    for p in points:
        key = (p.locality.strip().lower(), p.metro.strip().lower())
        if key not in seen:
            seen[key] = next_id
            next_id += 1
        cluster[p.id] = seen[key]
    return cluster


def _cluster_by_grid(points: list[Point], cell_deg: float) -> dict[str, int]:
    """Группировка по квадратной сетке (без цепочек).

    Точки в одной ячейке (~5 км) — один «район». Цепочечная кластеризация по
    расстоянию здесь не годится: в плотном городе она склеивает всё в один
    кластер. Сетка даёт дискретные районы без склейки.
    """
    cluster: dict[str, int] = {}
    seen: dict[tuple, int] = {}
    next_id = 0
    for p in points:
        if p.latitude is not None and p.longitude is not None:
            key = (round(p.latitude / cell_deg), round(p.longitude / cell_deg))
        else:
            key = (p.locality.strip().lower(), p.metro.strip().lower())
        if key not in seen:
            seen[key] = next_id
            next_id += 1
        cluster[p.id] = seen[key]
    return cluster
