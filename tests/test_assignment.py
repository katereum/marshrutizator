import unittest

from optimizer.assignment import assign_days
from optimizer.models import Visit


class TestAssignment(unittest.TestCase):
    def test_all_assigned_exactly_once(self):
        visits = [Visit("a", s, 0) for s in range(4)]
        day_visits, load = assign_days(visits, 20)
        flat = [v for d in day_visits for v in d]
        self.assertEqual(len(flat), 4)
        self.assertEqual(sorted(flat), ["a#0", "a#1", "a#2", "a#3"])
        self.assertEqual(sum(load), 4)

    def test_load_balanced(self):
        visits = [Visit(f"p{i}", 0, i % 3) for i in range(30)]
        day_visits, load = assign_days(visits, 10)
        self.assertEqual(sum(load), 30)
        self.assertLessEqual(max(load) - min(load), 1)

    def test_cyclic_spacing(self):
        visits = [Visit("a", s, 0) for s in range(4)]
        day_visits, _ = assign_days(visits, 20)
        days = sorted(d for d in range(20) if any(x.startswith("a#") for x in day_visits[d]))
        self.assertEqual(len(days), 4)
        self.assertTrue(all(b - a >= 2 for a, b in zip(days, days[1:])))

    def test_empty(self):
        day_visits, load = assign_days([], 5)
        self.assertEqual(load, [0, 0, 0, 0, 0])
        self.assertEqual(day_visits, [[] for _ in range(5)])

    def test_groups_nearby_points_by_road_distance(self):
        west = [f"w{i}" for i in range(5)]
        east = [f"e{i}" for i in range(5)]
        coords = {}
        for i in range(5):
            coords[f"w{i}"] = (55.75, 37.40 + i * 0.001)
            coords[f"e{i}"] = (55.75, 37.90 + i * 0.001)

        def dist(a, b):
            same_side = (a in west) == (b in west)
            return 1.0 if same_side else 50.0

        visits = [Visit(p, 0, 0) for p in west + east]
        day_visits, _ = assign_days(visits, 2, dist_fn=dist, coords=coords)

        d0 = {v.rsplit("#", 1)[0] for v in day_visits[0]}
        d1 = {v.rsplit("#", 1)[0] for v in day_visits[1]}
        # Каждый район целиком в одном дне — без смешивания восток+запад.
        self.assertTrue(d0 == set(west) or d0 == set(east))
        self.assertTrue(d1 == set(west) or d1 == set(east))
        self.assertNotEqual(d0, d1)

    def test_multi_frequency_keeps_districts_together(self):
        west = [f"w{i}" for i in range(4)]
        east = [f"e{i}" for i in range(4)]
        coords = {}
        for i in range(4):
            coords[f"w{i}"] = (55.75, 37.40 + i * 0.001)
            coords[f"e{i}"] = (55.75, 37.90 + i * 0.001)

        def dist(a, b):
            aw, bw = a.startswith("w"), b.startswith("w")
            return 1.0 if aw == bw else 50.0

        visits = []
        for pid in west:
            visits += [Visit(pid, s, 0) for s in range(2 if pid == "w0" else 1)]
        for pid in east:
            visits += [Visit(pid, s, 0) for s in range(2 if pid == "e0" else 1)]

        # 10 визитов, 4 дня → потолок 3.
        day_visits, load = assign_days(visits, 4, dist_fn=dist, coords=coords)
        self.assertLessEqual(max(load) - min(load), 1)

        # Каждый день однороден по району.
        for d in day_visits:
            ids = {v.rsplit("#", 1)[0] for v in d}
            if ids:
                self.assertTrue(
                    all(x.startswith("w") for x in ids) or all(x.startswith("e") for x in ids),
                    f"день смешал районы: {ids}",
                )

        # Частотность: w0 и e0 должны быть ровно на двух разных днях.
        for anchor in ("w0", "e0"):
            days = [d for d in range(4) if any(v.startswith(anchor + "#") for v in day_visits[d])]
            self.assertEqual(len(days), 2, anchor)

    def test_same_coordinates_share_day(self):
        coords = {
            "a": (55.75, 37.61), "b": (55.75, 37.61),
            "c": (55.75, 37.62), "d": (55.75, 37.63),
        }

        def dist(x, y):
            return 0.0 if coords[x] == coords[y] else 10.0

        visits = [Visit(p, 0, 0) for p in ("a", "b", "c", "d")]
        day_visits, _ = assign_days(visits, 2, dist_fn=dist, coords=coords)

        days = {
            p: {d for d in range(2) if any(v.startswith(p + "#") for v in day_visits[d])}
            for p in coords
        }
        # Одинаковый адрес (одинаковые координаты) → один и тот же день.
        self.assertEqual(days["a"], days["b"])

    def test_same_coordinates_mixed_frequency(self):
        coords = {"a": (55.75, 37.61), "b": (55.75, 37.61), "c": (55.75, 37.61)}

        def dist(x, y):
            return 0.0 if coords[x] == coords[y] else 10.0

        # a частота 2, b частота 2, c частота 1 — все в одном здании.
        visits = [
            Visit("a", 0, 0), Visit("a", 1, 0),
            Visit("b", 0, 0), Visit("b", 1, 0),
            Visit("c", 0, 0),
        ]
        day_visits, _ = assign_days(visits, 2, dist_fn=dist, coords=coords)

        days_a = {d for d in range(2) if any(v.startswith("a#") for v in day_visits[d])}
        days_b = {d for d in range(2) if any(v.startswith("b#") for v in day_visits[d])}
        days_c = {d for d in range(2) if any(v.startswith("c#") for v in day_visits[d])}
        # a и b делят одни и те же дни; c (частота 1) — в одном из этих дней.
        self.assertEqual(days_a, days_b)
        self.assertTrue(days_c <= days_a)

    def test_caps_respected(self):
        visits = [Visit(f"p{i}", 0, 0) for i in range(10)]
        day_visits, load = assign_days(visits, 3, caps=[5, 3, 2])
        self.assertEqual(sum(load), 10)
        self.assertTrue(all(l <= c for l, c in zip(load, [5, 3, 2])))

    def test_caps_infeasible_softens(self):
        visits = [Visit(f"p{i}", 0, 0) for i in range(10)]
        # Сумма лимитов 6 < 10 визитов — лимиты смягчаются, а не падаем.
        day_visits, load = assign_days(visits, 3, caps=[2, 2, 2])
        self.assertEqual(sum(load), 10)
        self.assertTrue(all(l <= 4 for l in load))  # потолок ceil(10/3)=4


if __name__ == "__main__":
    unittest.main()
