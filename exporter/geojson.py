"""GeoJSON маршрутов по дням (R7). Координаты — [lon, lat]."""
from __future__ import annotations

from optimizer.models import Point, RouteResult


def build_geojson(
    results: list[RouteResult],
    points_by_id: dict[str, Point],
    home: tuple[float, float] | None = None,
) -> dict:
    features = []
    for result in results:
        for day in result.days:
            coords = []
            for vid in day.ordered_visits:
                point = points_by_id.get(vid.rsplit("#", 1)[0])
                if point is not None and point.has_coords:
                    coords.append([point.longitude, point.latitude])
            if home is not None and coords:
                coords = [[home[1], home[0]]] + coords + [[home[1], home[0]]]
            if len(coords) >= 2:
                features.append(
                    {
                        "type": "Feature",
                        "properties": {
                            "employee": result.trade_rep_code,
                            "date": day.date.isoformat(),
                            "weekday": day.weekday,
                        },
                        "geometry": {"type": "LineString", "coordinates": coords},
                    }
                )
    return {"type": "FeatureCollection", "features": features}
