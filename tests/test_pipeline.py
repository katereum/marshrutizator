import unittest
from collections import Counter
from datetime import date

from optimizer.models import Point
from optimizer.pipeline import build_route, build_routes


class TestPipeline(unittest.TestCase):
    def test_10_points_freq1(self):
        pts = [Point(id=f"p{i}", trade_rep_code="T", frequency=1) for i in range(10)]
        r = build_route(pts, date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(r.stats.total_visits, 10)
        self.assertEqual(r.stats.violations, [])
        self.assertLessEqual(max(r.stats.per_day_load) - min(r.stats.per_day_load), 1)

    def test_freq_mix_counts(self):
        freqs = [1, 2, 3, 4, 1, 2, 3, 4, 1, 2]
        pts = [Point(id=f"p{i}", trade_rep_code="T", frequency=freqs[i]) for i in range(10)]
        r = build_route(pts, date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(r.stats.total_visits, sum(freqs))
        self.assertEqual(r.stats.violations, [])
        counts = Counter(vid.split("#")[0] for day in r.days for vid in day.ordered_visits)
        for i, f in enumerate(freqs):
            self.assertEqual(counts[f"p{i}"], f)

    def test_cap_and_warning(self):
        r = build_route([Point(id="a", trade_rep_code="T", frequency=30)],
                        date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(r.stats.total_visits, 22)
        self.assertTrue(any("учтено 22" in w for w in r.warnings))

    def test_multi_employee(self):
        pts = [Point(id="a", trade_rep_code="T1", frequency=1),
               Point(id="b", trade_rep_code="T2", frequency=2)]
        rs = build_routes(pts, date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(len(rs), 2)
        self.assertEqual({r.trade_rep_code: r.stats.total_visits for r in rs}, {"T1": 1, "T2": 2})

    def test_no_working_days_raises(self):
        with self.assertRaises(ValueError):
            build_route([Point(id="a", trade_rep_code="T", frequency=1)],
                        date(2026, 9, 5), date(2026, 9, 6))

    def test_road_matrix_drives_mileage(self):
        from optimizer.models import HOME_ID

        pts = [
            Point(id="p0", trade_rep_code="T", frequency=1, latitude=55.75, longitude=37.61),
            Point(id="p1", trade_rep_code="T", frequency=1, latitude=55.76, longitude=37.62),
        ]
        nodes = ["p0", "p1", HOME_ID]
        road = {}
        for a in nodes:
            for b in nodes:
                road[(a, b)] = 0.0 if a == b else 1.0

        r = build_route(
            pts,
            date(2026, 9, 1),
            date(2026, 9, 1),
            home=(55.75, 37.61),
            road_matrix=road,
        )
        # Один рабочий день: дом -> p0 -> p1 -> дом, каждое плечо по 1 км.
        self.assertEqual(r.stats.total_km, 3.0)

    def test_geographic_assignment_keeps_districts_on_same_day(self):
        from optimizer.models import HOME_ID

        # Два района: запад (близко к дому) и восток (далеко).
        pts = []
        for i in range(4):
            pts.append(Point(id=f"w{i}", trade_rep_code="T", frequency=1,
                             latitude=55.75, longitude=37.40 + i * 0.001))
        for i in range(4):
            pts.append(Point(id=f"e{i}", trade_rep_code="T", frequency=1,
                             latitude=55.75, longitude=37.90 + i * 0.001))

        nodes = [p.id for p in pts] + [HOME_ID]

        def road(a, b):
            if a == b:
                return 0.0
            aw, bw = a.startswith("w"), b.startswith("w")
            if HOME_ID in (a, b):
                other = a if b == HOME_ID else b
                return 1.0 if other.startswith("w") else 50.0
            return 1.0 if aw == bw else 50.0

        road_matrix = {(a, b): road(a, b) for a in nodes for b in nodes}
        r = build_route(
            pts,
            date(2026, 9, 1),
            date(2026, 9, 2),
            home=(55.75, 37.40),
            road_matrix=road_matrix,
        )

        # Два рабочих дня, 8 точек. Каждый день должен целиком лежать в одном районе.
        self.assertEqual(len(r.days), 2)
        for day in r.days:
            ids = {vid.rsplit("#", 1)[0] for vid in day.ordered_visits}
            self.assertTrue(
                all(x.startswith("w") for x in ids) or all(x.startswith("e") for x in ids),
                f"день смешал районы: {ids}",
            )

        # Итоговый пробег меньше, чем при смешанном распределении (запад+восток
        # в одном дне). Проверяем, что восток уехал в отдельный день с одной
        # дальней дорогой туда и одной обратно.
        self.assertLess(r.stats.total_km, 4 * 50.0 + 4 * 50.0)

    def test_focus_modes_produce_valid_routes(self):
        pts = [
            Point(id=f"p{i}", trade_rep_code="T", frequency=1,
                  latitude=55.75 + i * 0.001, longitude=37.61,
                  score=(i % 6), result=(i * 10))
            for i in range(6)
        ]
        for focus in ("economy", "fix_problems", "top_performers"):
            r = build_route(pts, date(2026, 9, 1), date(2026, 9, 30), focus=focus)
            self.assertEqual(r.stats.violations, [], focus)
            self.assertEqual(r.stats.total_visits, 6, focus)


if __name__ == "__main__":
    unittest.main()
