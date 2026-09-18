import unittest

from optimizer.models import Point
from optimizer.priority import FOCUS_ECONOMY, FOCUS_FIX, FOCUS_TOP, build_priority


def pt(pid, score=None, result=None):
    return Point(id=pid, trade_rep_code="T", frequency=1, score=score, result=result)


class TestPriority(unittest.TestCase):
    def test_economy_all_zero(self):
        pts = [pt("a", 1, 10), pt("b", 5, 100)]
        self.assertEqual(build_priority(pts, FOCUS_ECONOMY), {"a": 0.0, "b": 0.0})

    def test_fix_problems_prioritizes_low_and_ungraded(self):
        pts = [pt("good", 5, 100), pt("bad", 1, 10), pt("ungraded", None, 50)]
        pr = build_priority(pts, FOCUS_FIX)
        # bad: низкий результат + низкая оценка; ungraded: без оценки.
        self.assertGreater(pr["bad"], pr["good"])
        self.assertGreater(pr["ungraded"], pr["good"])

    def test_top_performers_prioritizes_high(self):
        pts = [pt("low", 1, 10), pt("high", 5, 100)]
        pr = build_priority(pts, FOCUS_TOP)
        self.assertGreater(pr["high"], pr["low"])

    def test_missing_columns_gives_neutral_priority(self):
        # Ни оценок, ни результатов -> приоритеты не вырождаются в крайности.
        pts = [pt("a"), pt("b")]
        pr = build_priority(pts, FOCUS_FIX)
        self.assertTrue(all(0.0 <= v <= 1.0 for v in pr.values()))


if __name__ == "__main__":
    unittest.main()
