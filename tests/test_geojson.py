import unittest
from datetime import date

from exporter.geojson import build_geojson
from optimizer.models import DaySchedule, Point, RouteResult


class TestGeojson(unittest.TestCase):
    def test_linestring_for_day_with_coords(self):
        points = {
            "a": Point(id="a", trade_rep_code="T", frequency=1, latitude=55.7, longitude=37.6),
            "b": Point(id="b", trade_rep_code="T", frequency=1, latitude=55.71, longitude=37.61),
        }
        result = RouteResult(
            job_id="j", trade_rep_code="T",
            period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
            days=[DaySchedule(date=date(2026, 9, 1), weekday=1, ordered_visits=["a#0", "b#0"])],
        )
        gj = build_geojson([result], points)
        self.assertEqual(gj["type"], "FeatureCollection")
        self.assertEqual(len(gj["features"]), 1)
        line = gj["features"][0]["geometry"]["coordinates"]
        self.assertEqual(line, [[37.6, 55.7], [37.61, 55.71]])

    def test_no_coords_no_features(self):
        points = {"a": Point(id="a", trade_rep_code="T", frequency=1)}
        result = RouteResult(
            job_id="j", trade_rep_code="T",
            period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
            days=[DaySchedule(date=date(2026, 9, 1), weekday=1, ordered_visits=["a#0"])],
        )
        gj = build_geojson([result], points)
        self.assertEqual(gj["features"], [])


if __name__ == "__main__":
    unittest.main()
