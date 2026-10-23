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
    with_metro = [p for p in points if p.metro.strip()]
    without_metro = [p for p in points if not p.metro.strip()]
    cluster: dict[str, int] = {}
    if with_metro:
        c = _cluster_by_address(with_metro)
        cluster.update(_merge_neighbors(c, with_metro, max_diameter_km=2.5))
    if without_metro:
        # Точки БЕЗ метро — по географии (сетка), а не по населённому пункту:
        # иначе все «Москва без метро» склеиваются в один гигантский кластер, и
        # дальние точки размазываются по дням (получаются «круги»).
        if all(p.has_coords for p in without_metro):
            c = _cluster_by_grid(without_metro, eps_km / 111.0)
        else:
            c = _cluster_by_address(without_metro)
        offset = max(cluster.values(), default=-1) + 1
        for pid, cid in c.items():
            cluster[pid] = cid + offset
    if not cluster:
        if all(p.has_coords for p in points):
            return _cluster_by_grid(points, eps_km / 111.0)
        return _cluster_by_address(points)
    return cluster


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


def _merge_neighbors(
    cluster: dict[str, int],
    points: list[Point],
    max_diameter_km: float,
) -> dict[str, int]:
    """Сливает соседние станции метро в один «район»-куст.

    Станция метро — слишком мелкая единица: соседние станции (1,5–2 км) — это
    один район, и объезжать их надо вместе, а не ездить туда-обратно. Жадное
    слияние по возрастанию расстояния между станциями, но диаметр куста
    ограничен `max_diameter_km` — поэтому цепочка станций вдоль линии НЕ
    склеивается в один гигантский куст, а делится на компактные сегменты.
    """
    by_c: dict[int, list[tuple[float, float]]] = {}
    for p in points:
        c = cluster.get(p.id)
        if c is not None and p.latitude is not None and p.longitude is not None:
            by_c.setdefault(c, []).append((p.latitude, p.longitude))
    if not by_c:
        return cluster

    centroids = {
        c: (sum(x[0] for x in cs) / len(cs), sum(x[1] for x in cs) / len(cs))
        for c, cs in by_c.items()
    }
    parent = {c: c for c in centroids}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    # BBox каждой группы для ограничения диаметра.
    bbox = {
        c: [centroids[c][0], centroids[c][0], centroids[c][1], centroids[c][1]]
        for c in centroids
    }

    def merged_diag(a: int, b: int) -> float:
        la1, la2, lo1, lo2 = bbox[a]
        bb = bbox[b]
        return haversine_km(
            min(la1, bb[0]), min(lo1, bb[2]), max(la2, bb[1]), max(lo2, bb[3])
        )

    keys = sorted(centroids)
    pairs: list[tuple[float, int, int]] = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            ca, cb = centroids[a], centroids[b]
            pairs.append((haversine_km(ca[0], ca[1], cb[0], cb[1]), a, b))
    pairs.sort()

    for d, a, b in pairs:
        ra, rb = find(a), find(b)
        if ra == rb:
            continue
        if merged_diag(ra, rb) <= max_diameter_km:
            parent[ra] = rb
            bb = bbox[rb]
            la1, la2, lo1, lo2 = bbox[ra]
            bbox[rb] = [min(la1, bb[0]), max(la2, bb[1]), min(lo1, bb[2]), max(lo2, bb[3])]

    root_to_new: dict[int, int] = {}
    new_cluster: dict[str, int] = {}
    for pid, c in cluster.items():
        r = find(c) if c in parent else c
        if r not in root_to_new:
            root_to_new[r] = len(root_to_new)
        new_cluster[pid] = root_to_new[r]
    return new_cluster
