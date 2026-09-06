"""Stage A — распределение визитов по рабочим дням (разделы 16, 18–19 ТЗ).

Подход (greedy + repair, см. docs/algorithm.md §2.3–2.4):
1. Каждый слот-визит кладётся в свой «идеальный» день (равномерная раскладка
   цикличности — приоритет №3).
2. Ремонт балансировки: пока разброс нагрузки по дням > 1, переносим визит из
   самого загруженного дня в самый незагруженный, предпочитая день, где уже
   есть тот же кластер (география, приоритет №2) и ближе к идеальному дню
   (сохраняем цикличность). Гарантирует разброс нагрузки ≤ 1.
"""
from __future__ import annotations

from .models import Visit


def ideal_day(slot: int, frequency: int, n_days: int) -> int:
    """Идеальный день для слота: равномерная раскладка по месяцу."""
    if n_days <= 1:
        return 0
    if frequency <= 1:
        return (n_days - 1) // 2
    if frequency >= n_days:
        return slot
    return round(slot * (n_days - 1) / (frequency - 1))


def assign_days(visits: list[Visit], n_days: int) -> tuple[list[list[str]], list[int]]:
    """Распределяет визиты по дням. Возвращает (day_visits, load)."""
    if n_days < 1:
        raise ValueError("n_days должен быть >= 1")
    total = len(visits)
    if total == 0:
        return [[] for _ in range(n_days)], [0] * n_days

    frequency: dict[str, int] = {}
    for v in visits:
        frequency[v.point_id] = frequency.get(v.point_id, 0) + 1
    visit_info = {v.visit_id: v for v in visits}

    day_visits: list[list[str]] = [[] for _ in range(n_days)]
    day_points: list[set[str]] = [set() for _ in range(n_days)]
    day_clusters: list[set[int]] = [set() for _ in range(n_days)]
    load = [0] * n_days

    # 1. Начальное размещение по идеальному дню.
    for v in visits:
        d = ideal_day(v.slot_index, frequency[v.point_id], n_days)
        day_visits[d].append(v.visit_id)
        day_points[d].add(v.point_id)
        day_clusters[d].add(v.cluster_id)
        load[d] += 1

    # 2. Ремонт балансировки с сохранением цикличности (и географии).
    max_iter = max(1, total * n_days * 10)
    for _ in range(max_iter):
        o = load.index(max(load))
        under = [u for u in range(n_days) if load[u] <= load[o] - 2]
        if not under:
            break  # разброс нагрузки <= 1

        # Лучший перенос: минимальный ущерб цикличности (|u - ideal|),
        # затем кластерная связность, затем наименее загруженный день.
        best = None  # (key, vid, u)
        for vid in day_visits[o]:
            v = visit_info[vid]
            ideal = ideal_day(v.slot_index, frequency[v.point_id], n_days)
            for u in under:
                if v.point_id in day_points[u]:
                    continue  # не два визита одной точки в один день
                cluster_match = 0 if v.cluster_id in day_clusters[u] else 1
                key = (abs(u - ideal), cluster_match, load[u], u)
                if best is None or key < best[0]:
                    best = (key, vid, u)

        if best is None:
            vid = day_visits[o][0]
            u = min(under, key=lambda x: load[x])
        else:
            _, vid, u = best

        v = visit_info[vid]
        day_visits[o].remove(vid)
        day_visits[u].append(vid)
        day_points[o].discard(v.point_id)
        day_points[u].add(v.point_id)
        day_clusters[u].add(v.cluster_id)
        load[o] -= 1
        load[u] += 1

    return day_visits, load
