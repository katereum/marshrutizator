import unittest

from optimizer.clusterer import cluster_points
from optimizer.models import Point


def mk(pid, lat=None, lon=None, locality="", metro=""):
    return Point(id=pid, trade_rep_code="T", frequency=1,
                 locality=locality, metro=metro, latitude=lat, longitude=lon)


class TestClusterer(unittest.TestCase):
    def test_close_points_same_cluster(self):
        c = cluster_points([mk("a", 55.75, 37.61), mk("b", 55.751, 37.611)], eps_km=5.0)
        self.assertEqual(c["a"], c["b"])

    def test_far_points_different_cluster(self):
        c = cluster_points([mk("a", 55.75, 37.61), mk("b", 55.0, 30.0)], eps_km=5.0)
        self.assertNotEqual(c["a"], c["b"])

    def test_address_fallback(self):
        pts = [mk("a", locality="Москва", metro="Тверская"),
               mk("b", locality="москва", metro="Тверская"),
               mk("c", locality="Питер", metro="")]
        c = cluster_points(pts)
        self.assertEqual(c["a"], c["b"])
        self.assertNotEqual(c["a"], c["c"])

    def test_empty(self):
        self.assertEqual(cluster_points([]), {})


if __name__ == "__main__":
    unittest.main()
