import unittest

from optimizer.models import Point
from optimizer.routing import order_day


class TestRouting(unittest.TestCase):
    def test_order_no_coords_preserves_set(self):
        pts = {
            "a#0": Point(id="a", trade_rep_code="T", frequency=1, normalized_address="m|s|a"),
            "b#0": Point(id="b", trade_rep_code="T", frequency=1, normalized_address="m|s|b"),
            "c#0": Point(id="c", trade_rep_code="T", frequency=1, normalized_address="m|s|c"),
        }
        order = order_day(list(pts.keys()), pts)
        self.assertEqual(set(order), set(pts.keys()))
        self.assertEqual(len(order), 3)

    def test_order_with_coords_preserves_set(self):
        pts = {
            f"p{i}#0": Point(id=f"p{i}", trade_rep_code="T", frequency=1,
                             latitude=55.75 + i * 0.001, longitude=37.61)
            for i in range(5)
        }
        order = order_day(list(pts.keys()), pts)
        self.assertEqual(set(order), set(pts.keys()))
        self.assertEqual(len(order), 5)

    def test_order_small(self):
        self.assertEqual(order_day([], {}), [])
        pts = {"a#0": Point(id="a", trade_rep_code="T", frequency=1)}
        self.assertEqual(order_day(["a#0"], pts), ["a#0"])

    def test_order_with_home_depot_starts_near_home(self):
        pts = {
            f"p{i}#0": Point(id=f"p{i}", trade_rep_code="T", frequency=1,
                             latitude=55.75 + i * 0.01, longitude=37.61)
            for i in range(5)
        }
        home = (55.75, 37.61)  # ближе всего к p0
        order = order_day(list(pts.keys()), pts, home)
        self.assertEqual(set(order), set(pts.keys()))
        self.assertEqual(order[0], "p0#0")

    def test_order_uses_road_distance_not_haversine(self):
        # По воздуху p0 близко к p1, но по дорогам (например, из-за реки) — к p2.
        pts = {
            "p0#0": Point(id="p0", trade_rep_code="T", frequency=1, latitude=55.75, longitude=37.61),
            "p1#0": Point(id="p1", trade_rep_code="T", frequency=1, latitude=55.751, longitude=37.611),
            "p2#0": Point(id="p2", trade_rep_code="T", frequency=1, latitude=55.90, longitude=37.90),
        }

        def road(a: str, b: str) -> float:
            key = frozenset((a.rsplit("#", 1)[0], b.rsplit("#", 1)[0]))
            return {
                frozenset(("p0", "p2")): 0.5,   # по дороге близко
                frozenset(("p0", "p1")): 9.0,   # по дороге далеко
                frozenset(("p1", "p2")): 5.0,
            }.get(key, 0.0)

        order = order_day(list(pts.keys()), pts, dist=road)
        self.assertEqual(set(order), set(pts.keys()))
        # Ближайший к старту по дороге — p2, а не p1 (который ближе по воздуху).
        self.assertEqual(order[0], "p0#0")
        self.assertEqual(order[1], "p2#0")

    def test_order_priority_pulls_high_priority_earlier(self):
        pts = {
            "a#0": Point(id="a", trade_rep_code="T", frequency=1, latitude=55.75, longitude=37.61),
            "b#0": Point(id="b", trade_rep_code="T", frequency=1, latitude=55.76, longitude=37.62),
            "c#0": Point(id="c", trade_rep_code="T", frequency=1, latitude=55.77, longitude=37.63),
        }
        home = (55.75, 37.60)
        ids = list(pts.keys())

        without = order_day(ids, pts, home)
        self.assertEqual(without[0], "a#0")  # ближайшая к дому

        priority = {"a": 0.0, "b": 0.0, "c": 1.0}
        with_prio = order_day(ids, pts, home, priority=priority, priority_weight=10.0)
        self.assertEqual(with_prio[0], "c#0")  # приоритетная вышла вперёд


if __name__ == "__main__":
    unittest.main()
