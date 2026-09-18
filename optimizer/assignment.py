"""Stage A — распределение визитов по рабочим дням (разделы 16, 18–19 ТЗ).

Подход — географический жадный + ремонт баланса (см. docs/algorithm.md §2.3–2.4):

1. Сначала обрабатываются «якоря» — точки с большей частотой (они задают
   разнесённые по месяцу дни), затем остальные точки в пространственном порядке
   (развёртка «запад→восток») группируются вокруг ближайших якорей. Так день
   превращается в компактный «район», а точки с частотой >1 обслуживаются в
   своих же районах, а не в одиночных дальних выездах.
2. Каждый слот-визит кладётся в день, минимизирующий дорожное расстояние до уже
   назначенных точек этого дня (плюс мягкое предпочтение «идеального» дня для
   сохранения цикличности).
3. Ремонт балансировки: пока разброс нагрузки по дням > 1, переносим визит из
   самого загруженного дня в самый незагруженный, выбирая перенос с минимальным
   ущербом для географии и цикличности. Гарантирует разброс нагрузки ≤ 1.

Без дорожной матрицы (`dist_fn is None`) алгоритм вырождается в прежнее
распределение по идеальному дню + балансировку — поведение совместимо.
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


def estimate_scale(dist_fn, point_ids) -> float:
    """Оценка характерного дорожного расстояния между точками (медиана NN).

    Используется как масштаб для веса цикличности и стоимости «пустого дня».
    Без dist_fn возвращает 1.0 (география не участвует).
    """
    if dist_fn is None:
        return 1.0
    ids = list(point_ids)
    if len(ids) < 2:
        return 1.0

    # Детерминированная выборка, чтобы оценка оставалась O(n^2) в худшем случае.
    if len(ids) > 200:
        step = len(ids) / 200.0
        sample = [ids[int(i * step)] for i in range(200)]
    else:
        sample = ids

    nearest = []
    for a in sample:
        best = None
        for b in sample:
            if a == b:
                continue
            d = dist_fn(a, b)
            if d is not None and (best is None or d < best):
                best = d
        if best is not None:
            nearest.append(best)

    if not nearest:
        return 1.0
    nearest.sort()
    return nearest[len(nearest) // 2]


def assign_days(
    visits: list[Visit],
    n_days: int,
    dist_fn=None,
    coords: dict[str, tuple[float, float]] | None = None,
    caps: list[int] | None = None,
) -> tuple[list[list[str]], list[int]]:
    """Распределяет визиты по дням. Возвращает (day_visits, load).

    `dist_fn(a, b) -> км` — дорожное расстояние между точками (опционально);
    `coords` — {point_id: (lat, lon)} для пространственного порядка;
    `caps` — макс. число точек на каждый день (len == n_days). None — авто-баланс.
    """
    if n_days < 1:
        raise ValueError("n_days должен быть >= 1")

    total = len(visits)
    if total == 0:
        return [[] for _ in range(n_days)], [0] * n_days

    if caps is None:
        cap = (total + n_days - 1) // n_days
        caps = [cap] * n_days
        hard_caps = False
    else:
        caps = list(caps)
        if len(caps) != n_days:
            raise ValueError(f"caps: ожидалось {n_days} значений, получено {len(caps)}")
        if sum(caps) < total:
            raise ValueError(
                f"Не хватает ёмкости: {total} визитов не помещаются в лимиты ({sum(caps)})"
            )
        hard_caps = True

    by_point: dict[str, list[Visit]] = {}
    for v in visits:
        by_point.setdefault(v.point_id, []).append(v)
    freq = {pid: len(vs) for pid, vs in by_point.items()}
    visit_info = {v.visit_id: v for v in visits}

    points = list(by_point.keys())
    if coords is not None and all(coords.get(p) for p in points):
        # Сначала «якоря» — точки с большей частотой: они задают разнесённые по
        # месяцу дни, вокруг которых затем группируются соседние точки (частота 1).
        # Вторично — пространственная развёртка (запад→восток).
        order = sorted(points, key=lambda p: (-freq[p], coords[p][1], coords[p][0], p))
    else:
        order = sorted(points, key=lambda p: (-freq[p], p))

    cap = (total + n_days - 1) // n_days  # потолок нагрузки на день
    scale = estimate_scale(dist_fn, points)
    seed_km = 2.0 * scale      # стоимость начала нового (пустого) дня
    cycle_weight = scale       # вес цикличности, в «километрах»

    day_points: list[set[str]] = [set() for _ in range(n_days)]
    day_visits: list[list[str]] = [[] for _ in range(n_days)]
    load = [0] * n_days
    medoid: list[str | None] = [None] * n_days

    def day_cost(pid: str, d: int) -> float:
        if dist_fn is None:
            return 0.0
        m = medoid[d]
        if m is None:
            return seed_km
        v = dist_fn(pid, m)
        return seed_km if v is None else v

    def cycle_penalty(pid: str, slot: int, f: int, d: int) -> float:
        if f < 2:
            return 0.0
        ideal = ideal_day(slot, f, n_days)
        return abs(d - ideal) / max(1, n_days - 1)

    # 1. Географическое размещение.
    for pid in order:
        f = freq[pid]
        chosen: set[int] = set()
        for v in by_point[pid]:
            best_d = None
            best_key = None
            for d in range(n_days):
                if d in chosen or load[d] >= caps[d]:
                    continue
                cost = day_cost(pid, d) + cycle_weight * cycle_penalty(pid, v.slot_index, f, d)
                key = (cost, load[d], d)
                if best_key is None or key < best_key:
                    best_key = key
                    best_d = d
            if best_d is None:
                # Все непустые дни заполнены или уже заняты точкой — берём
                # наименее загруженный свободный день.
                best_d = min((d for d in range(n_days) if d not in chosen), key=lambda d: load[d])

            chosen.add(best_d)
            day_points[best_d].add(pid)
            day_visits[best_d].append(v.visit_id)
            load[best_d] += 1
            if medoid[best_d] is None:
                medoid[best_d] = pid

    # 2. Ремонт балансировки (разброс нагрузки ≤ 1), минимальный ущерб географии.
    # При явных лимитах на день баланс уже задан лимитами — ремонт не нужен.
    if not hard_caps:
        max_iter = max(1, total * n_days * 10)
        for _ in range(max_iter):
            o = load.index(max(load))
            under = [u for u in range(n_days) if load[u] <= load[o] - 2]
            if not under:
                break

            best = None  # (key, vid, u)
            for vid in day_visits[o]:
                v = visit_info[vid]
                pid = v.point_id
                ideal = ideal_day(v.slot_index, freq[pid], n_days)
                for u in under:
                    if pid in day_points[u]:
                        continue  # одна точка не должна быть дважды в один день
                    geo = day_cost(pid, u)
                    cycle_delta = max(0.0, abs(u - ideal) - abs(o - ideal)) / max(1, n_days - 1)
                    key = (geo + cycle_weight * cycle_delta, load[u], u)
                    if best is None or key < best[0]:
                        best = (key, vid, u)

            if best is None:
                vid = day_visits[o][0]
                u = min(under, key=lambda x: load[x])
            else:
                _, vid, u = best

            v = visit_info[vid]
            pid = v.point_id
            day_visits[o].remove(vid)
            day_visits[u].append(vid)
            day_points[o].discard(pid)
            day_points[u].add(pid)
            load[o] -= 1
            load[u] += 1

            if medoid[o] == pid:
                medoid[o] = next(iter(day_points[o]), None)
            if medoid[u] is None:
                medoid[u] = pid

    return day_visits, load
