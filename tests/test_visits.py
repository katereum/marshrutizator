import unittest

from optimizer.models import Point
from optimizer.visits import expand_visits


def mk(pid: str, freq: int) -> Point:
    return Point(id=pid, trade_rep_code="T", frequency=freq)


class TestVisits(unittest.TestCase):
    def test_expansion_counts(self):
        visits, warnings = expand_visits([mk("a", 1), mk("b", 2), mk("c", 3)], 20)
        self.assertEqual(len(visits), 6)
        self.assertEqual(warnings, [])
        slots = {}
        for v in visits:
            slots.setdefault(v.point_id, []).append(v.slot_index)
        self.assertEqual(slots["a"], [0])
        self.assertEqual(slots["b"], [0, 1])
        self.assertEqual(slots["c"], [0, 1, 2])

    def test_cap_and_warning(self):
        visits, warnings = expand_visits([mk("a", 5)], 3)
        self.assertEqual(len(visits), 3)
        self.assertEqual(len(warnings), 1)
        self.assertIn("a", warnings[0])

    def test_no_working_days_raises(self):
        with self.assertRaises(ValueError):
            expand_visits([mk("a", 1)], 0)


if __name__ == "__main__":
    unittest.main()
