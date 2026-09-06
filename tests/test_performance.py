import time
import unittest
from datetime import date

from optimizer.models import Point
from optimizer.pipeline import build_route


class TestPerformance(unittest.TestCase):
    def test_large_base(self):
        """Тест №5 (раздел 38 ТЗ): большая база — 300 точек, цикличность 1..4."""
        freqs = [1, 2, 3, 4]
        pts = []
        for i in range(300):
            pts.append(
                Point(
                    id=f"p{i}",
                    trade_rep_code="T",
                    frequency=freqs[i % 4],
                    latitude=55.70 + (i % 50) * 0.001,
                    longitude=37.60 + (i % 40) * 0.001,
                )
            )
        start = time.perf_counter()
        r = build_route(pts, date(2026, 9, 1), date(2026, 9, 30))
        elapsed = time.perf_counter() - start

        expected = sum(freqs[i % 4] for i in range(300))
        self.assertEqual(r.stats.total_visits, expected)
        self.assertEqual(r.stats.violations, [])
        # Без учёта геокодирования — должно быть секунды, не десятки секунд.
        self.assertLess(elapsed, 5.0, f"слишком долго: {elapsed:.2f}s")


if __name__ == "__main__":
    unittest.main()
