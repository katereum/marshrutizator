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


if __name__ == "__main__":
    unittest.main()
