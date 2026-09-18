"""GeoJSON маршрутов по дням (R7). Координаты — [lon, lat].

В FeatureCollection два вида объектов:
- LineString — дорожная линия одного дня (свойства: employee, date, weekday, week);
- Point — торговая точка (свойства: code, address) для маркеров на карте.
"""
from __future__ import annotations

from optimizer.models import Point, RouteResult


def _compact_address(point: Point) -> str:
    """Компактный адрес для подсказки: «Москва, ул. Ленина, 1»."""
    o = point.original or {}

    def s(key: str) -> str:
        v = o.get(key)
        return str(v).strip() if v is not None else ""

    street = " ".join(x for x in [s("Тип улицы"), s("Название улицы")] if x)
    house = " ".join(x for x in [s("Номер дома"), s("Номер строения"), s("Номер корпуса")] if x)
    address = ", ".join(x for x in [s("Населенный пункт"), street, house] if x)
    if address:
        return address
    # Точки без original (например, в тестах) — собираем из нормализованных полей.
    return ", ".join(x for x in [point.locality, point.street, point.house] if x and x.strip())


def _display(point: Point, key: str) -> str:
    """Исходное значение колонки без учёта регистра (для подсказки на карте).

    Парсер уже сохранил видимое значение («90%», «нет»), поэтому здесь возвращаем
    его как есть; пусто -> «—».
    """
    o = point.original or {}
    for k, v in o.items():
        if str(k).strip().lower() == key.lower():
            s = str(v).strip() if v is not None else ""
            return s if s else "—"
    return "—"


def build_geojson(
    results: list[RouteResult],
    points_by_id: dict[str, Point],
    home: tuple[float, float] | None = None,
    home_by_weekday: dict[int, tuple[float, float]] | None = None,
    geometries: dict[tuple[str, str], list[list[float]]] | None = None,
) -> dict:
    """Собирает GeoJSON маршрутов (R7): линии по дням + точки-маркеры.

    `geometries` — дорожные полилинии {(employee, date.isoformat()): [[lon, lat], ...]}.
    Если для дня полилиния есть, линия идёт по дорогам; иначе — по прямой
    между точками (fallback).

    Точки несут в свойствах `score`/`result`/`priority`, чтобы фронтенд мог
    раскрасить маркеры по рейтингу (проблемные/средние/хорошие).
    """
    geometries = geometries or {}

    # Единая карта приоритетов по всем сотрудникам (point_id -> 0..1).
    priority_by_id: dict[str, float] = {}
    for r in results:
        priority_by_id.update(r.priority or {})
    features = []
    for result in results:
        for day in result.days:
            line = geometries.get((result.trade_rep_code, day.date.isoformat()))
            if line is None:
                coords = []
                for vid in day.ordered_visits:
                    point = points_by_id.get(vid.rsplit("#", 1)[0])
                    if point is not None and point.has_coords:
                        coords.append([point.longitude, point.latitude])
                h = home
                if home_by_weekday is not None:
                    h = home_by_weekday.get(day.weekday, home)
                if h is not None and coords:
                    coords = [[h[1], h[0]]] + coords + [[h[1], h[0]]]
                line = coords
            if line is not None and len(line) >= 2:
                features.append(
                    {
                        "type": "Feature",
                        "properties": {
                            "employee": result.trade_rep_code,
                            "date": day.date.isoformat(),
                            "weekday": day.weekday,
                            "week": (day.date.day - 1) // 7 + 1,
                        },
                        "geometry": {"type": "LineString", "coordinates": line},
                    }
                )

    # Точки — по одному маркеру на уникальную точку (независимо от числа визитов).
    for point in points_by_id.values():
        if not point.has_coords:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "code": point.id,
                    "address": _compact_address(point),
                    "employee": point.trade_rep_code,
                    "score": point.score,
                    "result": point.result,
                    "score_text": _display(point, "Оценка"),
                    "result_text": _display(point, "Результат"),
                    "priority": round(priority_by_id.get(point.id, 0.0), 3),
                },
                "geometry": {"type": "Point", "coordinates": [point.longitude, point.latitude]},
            }
        )

    return {"type": "FeatureCollection", "features": features}
