import unittest
from datetime import date

from exporter.geojson import build_geojson
from optimizer.models import DaySchedule, Point, RouteResult


def line_features(gj):
    return [f for f in gj["features"] if f["geometry"]["type"] == "LineString"]


def point_features(gj):
    return [f for f in gj["features"] if f["geometry"]["type"] == "Point"]


def make_result(days):
    return RouteResult(
        job_id="j", trade_rep_code="T",
        period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
        days=days,
    )


class TestGeojson(unittest.TestCase):
    def test_linestring_for_day_with_coords(self):
        points = {
            "a": Point(id="a", trade_rep_code="T", frequency=1, latitude=55.7, longitude=37.6),
            "b": Point(id="b", trade_rep_code="T", frequency=1, latitude=55.71, longitude=37.61),
        }
        result = make_result([DaySchedule(date=date(2026, 9, 1), weekday=1, ordered_visits=["a#0", "b#0"])])
        gj = build_geojson([result], points)
        self.assertEqual(gj["type"], "FeatureCollection")
        lines = line_features(gj)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["geometry"]["coordinates"], [[37.6, 55.7], [37.61, 55.71]])

    def test_week_is_week_of_month(self):
        points = {
            "a": Point(id="a", trade_rep_code="T", frequency=1, latitude=55.7, longitude=37.6),
            "b": Point(id="b", trade_rep_code="T", frequency=1, latitude=55.71, longitude=37.61),
        }
        result = make_result([DaySchedule(date=date(2026, 9, 8), weekday=1, ordered_visits=["a#0", "b#0"])])
        gj = build_geojson([result], points)
        lines = line_features(gj)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["properties"]["week"], 2)

    def test_point_markers_with_code_and_address(self):
        points = {
            "a": Point(
                id="A001", trade_rep_code="T", frequency=1, latitude=55.7, longitude=37.6,
                original={
                    "Населенный пункт": "Москва", "Тип улицы": "ул.",
                    "Название улицы": "Ленина", "Номер дома": "1",
                },
            ),
        }
        result = make_result([DaySchedule(date=date(2026, 9, 1), weekday=1, ordered_visits=["a#0"])])
        gj = build_geojson([result], points)
        pts = point_features(gj)
        self.assertEqual(len(pts), 1)
        self.assertEqual(pts[0]["properties"]["code"], "A001")
        self.assertEqual(pts[0]["properties"]["address"], "Москва, ул. Ленина, 1")
        self.assertEqual(pts[0]["geometry"]["coordinates"], [37.6, 55.7])

    def test_no_coords_no_features(self):
        points = {"a": Point(id="a", trade_rep_code="T", frequency=1)}
        result = make_result([DaySchedule(date=date(2026, 9, 1), weekday=1, ordered_visits=["a#0"])])
        gj = build_geojson([result], points)
        self.assertEqual(gj["features"], [])

    def test_uses_road_geometry_when_provided(self):
        points = {
            "a": Point(id="a", trade_rep_code="T", frequency=1, latitude=55.7, longitude=37.6),
            "b": Point(id="b", trade_rep_code="T", frequency=1, latitude=55.71, longitude=37.61),
        }
        result = make_result([DaySchedule(date=date(2026, 9, 1), weekday=1, ordered_visits=["a#0", "b#0"])])
        road_line = [[37.6, 55.7], [37.605, 55.705], [37.61, 55.71]]
        gj = build_geojson([result], points, geometries={("T", "2026-09-01"): road_line})
        self.assertEqual(line_features(gj)[0]["geometry"]["coordinates"], road_line)

    def test_falls_back_to_straight_line_without_geometry(self):
        points = {
            "a": Point(id="a", trade_rep_code="T", frequency=1, latitude=55.7, longitude=37.6),
            "b": Point(id="b", trade_rep_code="T", frequency=1, latitude=55.71, longitude=37.61),
        }
        result = make_result([DaySchedule(date=date(2026, 9, 1), weekday=1, ordered_visits=["a#0", "b#0"])])
        gj = build_geojson([result], points)
        self.assertEqual(line_features(gj)[0]["geometry"]["coordinates"], [[37.6, 55.7], [37.61, 55.71]])


if __name__ == "__main__":
    unittest.main()
