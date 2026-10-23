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

    def test_different_metro_lines_do_not_merge_across_river(self):
        # Станции РАЗНЫХ линий метро (по разные стороны реки/канала) НЕ сливаются
        # в один район, даже если по прямой они рядом (≤2.5 км). Иначе куст
        # перелезает через водохранилище и день делает круг вокруг реки.
        # Регрессия: Сходненская (запад, ТКЛ) vs Беломорская (восток, Замоскв.).
        pts = [
            mk("west1", 55.86, 37.44, metro="Сходненская (Таганско-Краснопресненская)"),
            mk("west2", 55.87, 37.44, metro="Планерная (Таганско-Краснопресненская)"),
            mk("east1", 55.86, 37.47, metro="Беломорская (Замоскворецкая)"),
        ]
        c = cluster_points(pts, eps_km=5.0)
        self.assertEqual(c["west1"], c["west2"])      # одна линия — вместе
        self.assertNotEqual(c["west1"], c["east1"])   # другая линия — отдельно


if __name__ == "__main__":
    unittest.main()
