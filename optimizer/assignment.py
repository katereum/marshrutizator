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

from .distance import haversine_km
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
    home: tuple[float, float] | None = None,
) -> tuple[list[list[str]], list[int]]:
    """Распределяет визиты по дням. Возвращает (day_visits, load).

    `dist_fn(a, b) -> км` — дорожное расстояние между точками (опционально);
    `coords` — {point_id: (lat, lon)} для пространственного порядка;
    `caps` — макс. число точек на каждый день (len == n_days). None — авто-баланс.
    `home` — (lat, lon) дома старта: районы сортируются по удалённости от дома,
    чтобы ближние обслуживались в первые недели, дальние — позже.
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
        # Лимиты — жёсткий потолок, НЕ смягчаем. Если визитов больше, чем
        # вмещают лимиты, лишние не планируются (срезаем хвост списка ordered).
        hard_caps = True

    by_point: dict[str, list[Visit]] = {}
    for v in visits:
        by_point.setdefault(v.point_id, []).append(v)
    freq = {pid: len(vs) for pid, vs in by_point.items()}
    visit_info = {v.visit_id: v for v in visits}

    points = list(by_point.keys())
    # Кластер (район) каждой точки — для компактных дней по районам.
    point_cluster: dict[str, int] = {}
    for v in visits:
        if v.cluster_id >= 0:
            point_cluster.setdefault(v.point_id, v.cluster_id)
    # Размер кластера (число точек) — чтобы отличить одиночную точку от района.
    cluster_size: dict[int, int] = {}
    for pid, c in point_cluster.items():
        cluster_size[c] = cluster_size.get(c, 0) + 1

    # Порядок точек: сначала по району (кластеру), затем внутри района — по
    # частоте (якоря) и географии. Так точки одного района идут подряд и
    # попадают в один (или соседние) дни, а не размазываются по всему городу.
    if coords is not None and point_cluster and all(coords.get(p) for p in points):
        centroid: dict[int, tuple[float, float, int]] = {}
        for pid, c in point_cluster.items():
            cc = coords.get(pid)
            if cc is None:
                continue
            lat, lon, n = centroid.get(c, (0.0, 0.0, 0))
            centroid[c] = (lat + cc[0], lon + cc[1], n + 1)
        center = {c: (v[0] / v[2], v[1] / v[2]) for c, v in centroid.items()}
        if home is not None:
            # От дома наружу: ближние районы обслуживаются раньше (недели 1–2),
            # дальние — позже. Так маршрут идёт «спиралью» от дома, а не кругами
            # по всему городу.
            ranked = sorted(
                center.keys(),
                key=lambda c: haversine_km(home[0], home[1], center[c][0], center[c][1]),
            )
        else:
            ranked = sorted(center.keys(), key=lambda c: center[c])
        cluster_rank = {c: i for i, c in enumerate(ranked)}

        def _key(p):
            c = point_cluster.get(p, -1)
            rk = cluster_rank.get(c, 1 << 30)
            cc = coords.get(p, (0.0, 0.0))
            return (rk, -freq[p], cc[1], cc[0], p)

        order = sorted(points, key=_key)
    elif coords is not None and all(coords.get(p) for p in points):
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
    # Центроид дня (сумма координат размещённых точек) — чтобы новый куст шёл в
    # день с ближайшим ЦЕНТРОМ, а не к первой точке (иначе день «расползается»).
    day_slat = [0.0] * n_days
    day_slon = [0.0] * n_days
    day_cnt = [0] * n_days

    # Кластеры по дням — чтобы точки одного района шли в один день.
    day_clusters: list[set[int]] = [set() for _ in range(n_days)]
    placed_clusters: set[int] = set()
    # Отдельная привязка района для ПОВТОРНЫХ визитов (цикличность): повторный
    # визит района идёт в ДРУГУЮ неделю (по циклу), а не в день покрытия, но при
    # этом вместе с другими повторными визитами того же района (не разлетается).
    day_clusters2: list[set[int]] = [set() for _ in range(n_days)]
    placed_clusters2: set[int] = set()
    # Большой фиксированный штраф: точка одного района ОЧЕНЬ не хочет идти в день,
    # где её района ещё нет (кроме случая, когда «родной» день уже заполнен).
    cluster_penalty_km = 1e6

    def _cluster_penalty(pid: str, d: int, day_cl: list[set[int]], placed_cl: set[int]) -> float:
        c = point_cluster.get(pid)
        if c is None:
            return 0.0
        if c in day_cl[d]:
            return 0.0
        if c not in placed_cl:
            return 0.0
        # Одиночный кластер (одна точка) — некуда «держаться»: работает глобальная
        # цикличность. Многокточечный кластер (район) — точка тянется к «родным»
        # дням района: спилл идёт в соседний день, а не разлетается по всему городу.
        if cluster_size.get(c, 1) <= 1:
            return cluster_penalty_km
        anchor = min(day for day in range(n_days) if c in day_cl[day])
        return cluster_penalty_km + abs(d - anchor) * seed_km

    def cluster_penalty(pid: str, d: int) -> float:
        return _cluster_penalty(pid, d, day_clusters, placed_clusters)

    def cluster_penalty2(pid: str, d: int) -> float:
        return _cluster_penalty(pid, d, day_clusters2, placed_clusters2)

    def day_cost(pid: str, d: int) -> float:
        if day_cnt[d] == 0:
            return seed_km
        cc = coords.get(pid) if coords is not None else None
        if cc is None:
            return seed_km
        clat = day_slat[d] / day_cnt[d]
        clon = day_slon[d] / day_cnt[d]
        return haversine_km(clat, clon, cc[0], cc[1])

    def cycle_penalty(pid: str, slot: int, f: int, d: int) -> float:
        if f < 2:
            return 0.0
        ideal = ideal_day(slot, f, n_days)
        return abs(d - ideal) / max(1, n_days - 1)

    # 1. Географическое размещение — в два прохода:
    #    а) покрытие: первые визиты (слот 0), ближние районы раньше;
    #    б) цикличность: повторные визиты (слот 1+) — по циклу на разные недели.
    chosen_by_pid: dict[str, set[int]] = {}

    def _place(pid: str, v: Visit, f: int, use_cycle: bool) -> bool:
        chosen = chosen_by_pid.setdefault(pid, set())
        best_d = None
        best_key = None
        for d in range(n_days):
            if d in chosen or load[d] >= caps[d]:
                continue
            if use_cycle:
                cost = cluster_penalty2(pid, d) + cycle_weight * cycle_penalty(pid, v.slot_index, f, d)
            else:
                cost = day_cost(pid, d) + cluster_penalty(pid, d)
            key = (cost, load[d], d)
            if best_key is None or key < best_key:
                best_key = key
                best_d = d
        if best_d is None:
            if hard_caps:
                # Жёсткий лимит: визит не помещается — лишний, не планируем.
                return False
            # Авто-баланс: кладём в наименее загруженный день (ремонт выровняет).
            best_d = min((d for d in range(n_days) if d not in chosen), key=lambda d: load[d])

        chosen.add(best_d)
        day_points[best_d].add(pid)
        day_visits[best_d].append(v.visit_id)
        load[best_d] += 1
        cc = coords.get(pid) if coords is not None else None
        if cc is not None:
            day_slat[best_d] += cc[0]
            day_slon[best_d] += cc[1]
            day_cnt[best_d] += 1
        c = point_cluster.get(pid)
        if c is not None:
            if use_cycle:
                day_clusters2[best_d].add(c)
                placed_clusters2.add(c)
            else:
                day_clusters[best_d].add(c)
                placed_clusters.add(c)
        return True

    # 1. Географическое размещение в два прохода, собранных в один список:
    #    а) покрытие: первые визиты (слот 0), ближние районы раньше;
    #    б) цикличность: повторные визиты (слот 1+) — по циклу на разные недели.
    # Лимиты жёсткие: если визитов больше, чем вмещают лимиты, лишние НЕ
    # планируются — срезаем хвост списка (дальние районы и их повторные визиты).
    ordered: list[tuple[str, Visit, bool]] = []
    for pid in order:
        ordered += [(pid, v, False) for v in by_point[pid] if v.slot_index == 0]
    for pid in order:
        ordered += [(pid, v, True) for v in by_point[pid] if v.slot_index > 0]

    for pid, v, use_cycle in ordered:
        _place(pid, v, freq[pid], use_cycle)

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
                    cl = cluster_penalty(pid, u)
                    cycle_delta = max(0.0, abs(u - ideal) - abs(o - ideal)) / max(1, n_days - 1)
                    key = (geo + cl + cycle_weight * cycle_delta, load[u], u)
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
    caps: list[int] | None = None,
) -> tuple[list[list[str]], list[int]]:
    """Собирает точки одного места (одинаковые координаты) в один день.

    Обратная связь с полей: если в одном месте (ТЦ, бизнес-центр) много точек,
    удобнее объехать их все за один день, чем дробить на несколько дней и
    возвращаться. Запускается ПОСЛЕ assign_days (включая балансировку). Если
    заданы дневные лимиты (caps), они соблюдаются жёстко: в заполненный день
    точки не перекладываются.
    """
    if not coords:
        return day_visits, load

    visit_day: dict[str, int] = {}
    for d, vids in enumerate(day_visits):
        for vid in vids:
            visit_day[vid] = d

    # Лишние визиты (не влезшие в лимит) уже отброшены в assign_days — работаем
    # только с размещёнными, иначе ниже KeyError на отброшенном visit_id.
    visits = [v for v in visits if v.visit_id in visit_day]

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
                # Лимит жёсткий: не перекладываем в уже заполненный день (17/12 и т.п.).
                if caps is not None and load[target] >= caps[target]:
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


def tidy_days(
    day_visits: list[list[str]],
    load: list[int],
    visits: list[Visit],
    coords: dict[str, tuple[float, float]],
    caps: list[int] | None = None,
) -> tuple[list[list[str]], list[int]]:
    """Убирает «выбросы»: точку далеко от центра своего дня тянет в ближайший день.

    Идёт ПОСЛЕ assign_days и consolidate_locations. Добивает последние «круги» —
    когда в день случайно попала точка из другого конца города (например, второй
    слот частой точки, которой не хватило места в «родном» дне).
    """
    n_days = len(day_visits)
    total = sum(load)
    cap = list(caps) if caps else [((total + n_days - 1) // n_days)] * n_days

    point_coords = {v.point_id: coords[v.point_id] for v in visits if v.point_id in coords}
    visit_pid = {v.visit_id: v.point_id for v in visits}

    for _ in range(3):
        # Центроид каждого дня по геокодированным точкам.
        centroid: dict[int, tuple[float, float]] = {}
        for d in range(n_days):
            cs = [point_coords[visit_pid[vid]] for vid in day_visits[d] if visit_pid[vid] in point_coords]
            if cs:
                centroid[d] = (sum(c[0] for c in cs) / len(cs), sum(c[1] for c in cs) / len(cs))

        day_pids = [{visit_pid[v] for v in day_visits[d]} for d in range(n_days)]
        moved = False
        for d in range(n_days):
            if d not in centroid:
                continue
            for vid in list(day_visits[d]):
                pid = visit_pid[vid]
                if pid not in point_coords:
                    continue
                c = point_coords[pid]
                own = haversine_km(c[0], c[1], centroid[d][0], centroid[d][1])
                best = None
                for d2 in range(n_days):
                    if d2 == d or d2 not in centroid or load[d2] >= cap[d2]:
                        continue
                    if pid in day_pids[d2]:
                        continue
                    dist = haversine_km(c[0], c[1], centroid[d2][0], centroid[d2][1])
                    if dist < own and (best is None or dist < best[0]):
                        best = (dist, d2)
                # Перекладываем, только если это заметно сокращает разлёт (> 2 км).
                if best is not None and own - best[0] > 2.0:
                    d2 = best[1]
                    day_visits[d].remove(vid)
                    day_visits[d2].append(vid)
                    day_pids[d].discard(pid)
                    day_pids[d2].add(pid)
                    load[d] -= 1
                    load[d2] += 1
                    moved = True
        if not moved:
            break

    return day_visits, load
