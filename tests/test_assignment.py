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


if __name__ == "__main__":
    unittest.main()
