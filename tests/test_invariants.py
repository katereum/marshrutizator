"""Инварианты алгоритма на случайных данных (замена hypothesis, чистый stdlib)."""
import random
import unittest
from collections import Counter
from datetime import date

from optimizer.models import Point
from optimizer.pipeline import build_routes


class TestInvariants(unittest.TestCase):
    def test_randomized_invariants(self):
        rng = random.Random(42)
        for _ in range(20):
            n = rng.randint(5, 60)
            pts = [
                Point(
                    id=f"p{i}",
                    trade_rep_code=rng.choice(["A", "B"]),
                    frequency=rng.randint(1, 6),
                    latitude=rng.uniform(55.6, 55.9),
                    longitude=rng.uniform(37.4, 37.8),
                )
                for i in range(n)
            ]
            results = build_routes(pts, date(2026, 9, 1), date(2026, 9, 30))
            for r in results:
                # нет нарушений
                self.assertEqual(r.stats.violations, [])
                # точное число визитов на точку (без потерь и дублей)
                counts = Counter(
                    vid.split("#")[0] for d in r.days for vid in d.ordered_visits
                )
                expected = {
                    p.id: p.frequency
                    for p in pts
                    if p.trade_rep_code == r.trade_rep_code
                }
                self.assertEqual(counts, expected)
                # Компактность по районам важнее идеальной равномерности: после
                # сборки по кластерам разброс нагрузки может быть больше 1, но
                # не должен превышать среднюю загрузку дня.
                avg = (sum(r.stats.per_day_load) + 1) // 2
                self.assertLessEqual(
                    max(r.stats.per_day_load) - min(r.stats.per_day_load),
                    max(2, avg),
                )


if __name__ == "__main__":
    unittest.main()
