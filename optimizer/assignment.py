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

from collections import Counter

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
            # Мягкое ограничение (R3): визиты не помещаются в лимиты — смягчаем
            # лимиты, а не падаем. Каждый день получает не меньше ceil(total/n_days),
            # но заданные пользователем более высокие значения на отдельные дни
            # сохраняются. Цикличность при этом не нарушается.
            floor = (total + n_days - 1) // n_days
            caps = [max(c, floor) for c in caps]
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


def _coords_key(c: tuple[float, float]) -> tuple[float, float]:
    """Ключ «одного места»: координаты, округлённые до ~10 м."""
    return (round(c[0], 4), round(c[1], 4))


def consolidate_locations(
    day_visits: list[list[str]],
    load: list[int],
    visits: list[Visit],
    coords: dict[str, tuple[float, float]],
) -> tuple[list[list[str]], list[int]]:
    """Собирает точки одного места (одинаковые координаты) в один день.

    Обратная связь с полей: если в одном месте (ТЦ, бизнес-центр) много точек,
    удобнее объехать их все за один день, чем дробить на несколько дней и
    возвращаться. Запускается ПОСЛЕ assign_days (включая балансировку) — это
    финальное слово; ради «кучности» одного места дневной лимит может быть
    превышен.
    """
    if not coords:
        return day_visits, load

    visit_day: dict[str, int] = {}
    for d, vids in enumerate(day_visits):
        for vid in vids:
            visit_day[vid] = d

    point_visits: dict[str, list[Visit]] = {}
    for v in visits:
        point_visits.setdefault(v.point_id, []).append(v)

    # group_key -> slot_index -> [visit_id]
    slot_groups: dict[tuple, dict[int, list[str]]] = {}
    for v in visits:
        c = coords.get(v.point_id)
        if c is None:
            continue
        slot_groups.setdefault(_coords_key(c), {}).setdefault(v.slot_index, []).append(v.visit_id)

    for key, slots in slot_groups.items():
        for slot, vids in slots.items():
            if len(vids) < 2:
                continue
            days = [visit_day[v] for v in vids]
            if len(set(days)) <= 1:
                continue
            # Целевой день — с наибольшим числом визитов этого слота (при равенстве — менее загруженный).
            cnt = Counter(days)
            target = max(cnt.keys(), key=lambda d: (cnt[d], -load[d]))
            for vid in vids:
                old = visit_day[vid]
                if old == target:
                    continue
                pid = vid.rsplit("#", 1)[0]
                # Не ставим одну точку дважды в один день (разные слоты точки).
                if any(v2.visit_id in day_visits[target] for v2 in point_visits.get(pid, [])):
                    continue
                day_visits[old].remove(vid)
                day_visits[target].append(vid)
                load[old] -= 1
                load[target] += 1
                visit_day[vid] = target

    return day_visits, load
