import unittest
from datetime import date

from optimizer.calendar import working_days


class TestCalendar(unittest.TestCase):
    def test_sept_2026_has_22_working_days(self):
        days = working_days(date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(len(days), 22)
        self.assertTrue(all(d.weekday() < 5 for d in days))
        self.assertEqual(days[0], date(2026, 9, 1))
        self.assertEqual(days[-1], date(2026, 9, 30))

    def test_weekends_excluded(self):
        days = working_days(date(2026, 9, 5), date(2026, 9, 6))  # сб + вс
        self.assertEqual(days, [])

    def test_reversed_period_raises(self):
        with self.assertRaises(ValueError):
            working_days(date(2026, 9, 30), date(2026, 9, 1))


if __name__ == "__main__":
    unittest.main()
