import unittest
from datetime import date

from optimizer.calendar import working_days
from optimizer.models import Point
from optimizer.pipeline import build_route
from optimizer.regenerate import recluster_day


def _days_of(result, pid):
    return [
        i for i, ds in enumerate(result.days)
        if any(v.rsplit("#", 1)[0] == pid for v in ds.ordered_visits)
    ]


class TestReclusterGap(unittest.TestCase):
    def _build(self):
        pts = []
        # 6 точек с частотой 2 в одном районе — их повторный визит не должен
        # попадать в ту же неделю, что и покрытие.
        for i in range(6):
            pts.append(Point(
                id=f"F{i}", trade_rep_code="TP1", frequency=2,
                locality="Москва", street="Ленина", house=str(i + 1),
                metro="Сходненская (ТКЛ)",
                latitude=55.855 + i * 0.001, longitude=37.44,
            ))
        # Заполнитель — чтобы дни покрытия выходили полными.
        for i in range(40):
            pts.append(Point(
                id=f"P{i}", trade_rep_code="TP1", frequency=1,
                locality="Москва", street="Ул", house=str(i + 1),
                metro=f"М{i} (ЗМЛ)",
                latitude=55.80 + (i % 10) * 0.005, longitude=37.60 + (i // 10) * 0.005,
            ))
        days = working_days(date(2026, 11, 2), date(2026, 11, 30), False)
        total = sum(p.frequency for p in pts)
        caps = []
        rem = total
        for _ in days:
            c = min(17, rem)
            caps.append(c)
            rem -= c
        result = build_route(pts, date(2026, 11, 2), date(2026, 11, 30),
                             home=(55.855, 37.44), caps=caps)
        return pts, result

    def test_recluster_keeps_repeat_out_of_coverage_week(self):
        pts, result = self._build()
        f0 = _days_of(result, "F0")
        self.assertEqual(len(f0), 2, f"F0 должна стоять в 2 днях, нашлось {f0}")
        coverage_day = f0[0]
        locked = {result.days[coverage_day].date.isoformat()}

        # Переделать ВСЕ остальные незафиксированные дни (как «оптимизировать отмеченные»).
        for i in range(len(result.days)):
            if i == coverage_day or not result.days[i].ordered_visits:
                continue
            recluster_day(result, i, 0, points=pts, home=(55.855, 37.44),
                          home_by_weekday=None, road_matrix=None,
                          focus="economy", work_on_weekends=False,
                          locked_dates=locked)

        # Инвариант: ни одна точка не стоит в двух днях ближе, чем через 5 раб. дней.
        pid_days = {}
        for i, ds in enumerate(result.days):
            for v in ds.ordered_visits:
                pid_days.setdefault(v.rsplit("#", 1)[0], []).append(i)
        bad = []
        for pid, dd in pid_days.items():
            dd = sorted(dd)
            for a, b in zip(dd, dd[1:]):
                if b - a < 5:
                    bad.append((pid, dd))
        self.assertEqual(bad, [], f"Точки в одну неделю после переделки: {bad}")


if __name__ == "__main__":
    unittest.main()
