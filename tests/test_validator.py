import unittest
from datetime import date

from optimizer.models import DaySchedule, RouteResult
from optimizer.validator import validate_route


def mk_result(days, start, end):
    r = RouteResult(job_id="j", trade_rep_code="T", period_start=start, period_end=end)
    for d, wd, visits in days:
        r.days.append(DaySchedule(date=d, weekday=wd, ordered_visits=visits))
    return r


class TestValidator(unittest.TestCase):
    def test_valid_result(self):
        start, end = date(2026, 9, 1), date(2026, 9, 30)
        r = mk_result([(date(2026, 9, 1), 1, ["a#0"]), (date(2026, 9, 2), 2, ["b#0", "b#1"])], start, end)
        self.assertEqual(validate_route(r, {"a": 1, "b": 2}), [])

    def test_missing_visit(self):
        start, end = date(2026, 9, 1), date(2026, 9, 30)
        r = mk_result([(date(2026, 9, 1), 1, ["a#0"])], start, end)
        self.assertTrue(any("потеряно" in x for x in validate_route(r, {"a": 2})))

    def test_duplicate_visit_id(self):
        start, end = date(2026, 9, 1), date(2026, 9, 30)
        r = mk_result([(date(2026, 9, 1), 1, ["a#0", "a#0"])], start, end)
        self.assertTrue(any("дубликаты" in x.lower() for x in validate_route(r, {"a": 1})))

    def test_weekend_violation(self):
        start, end = date(2026, 9, 1), date(2026, 9, 30)
        r = mk_result([(date(2026, 9, 5), 5, ["a#0"])], start, end)  # суббота
        self.assertTrue(any("выходной" in x for x in validate_route(r, {"a": 1})))


if __name__ == "__main__":
    unittest.main()
