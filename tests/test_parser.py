import io
import unittest

from openpyxl import Workbook

from parser import ValidationError, parse_planning
from parser.columns import PLANNING_COLUMNS


def xlsx_with(header, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def row(**overrides):
    base = {c: "" for c in PLANNING_COLUMNS}
    base.update(
        {
            "Единый код": "A001",
            "Населенный пункт": "Москва",
            "Тип улицы": "ул.",
            "Название улицы": "Ленина",
            "Номер дома": "1",
            "Цикличность": 1,
            "Код торгового представителя": "TP1",
        }
    )
    base.update(overrides)
    return [base[c] for c in PLANNING_COLUMNS]


class TestParser(unittest.TestCase):
    def test_parse_valid(self):
        rows = [row(), row(**{"Единый код": "A002", "Цикличность": 2})]
        points = parse_planning(xlsx_with(PLANNING_COLUMNS, rows))
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0].id, "A001")
        self.assertEqual(points[1].frequency, 2)
        self.assertEqual(points[0].trade_rep_code, "TP1")
        self.assertIn("Единый код", points[0].original)

    def test_missing_column(self):  # Тест №6
        header = [c for c in PLANNING_COLUMNS if c != "Цикличность"]
        with self.assertRaises(ValidationError) as cm:
            parse_planning(xlsx_with(header, []))
        self.assertIn("Цикличность", str(cm.exception))

    def test_empty_required_field(self):  # Тест №7
        with self.assertRaises(ValidationError):
            parse_planning(xlsx_with(PLANNING_COLUMNS, [row(**{"Название улицы": ""})]))

    def test_duplicate_code(self):  # Тест №8
        with self.assertRaises(ValidationError) as cm:
            parse_planning(xlsx_with(PLANNING_COLUMNS, [row(), row()]))
        self.assertIn("Дублирующийся", str(cm.exception))

    def test_invalid_frequency(self):
        with self.assertRaises(ValidationError):
            parse_planning(xlsx_with(PLANNING_COLUMNS, [row(**{"Цикличность": "abc"})]))

    def test_empty_base(self):
        with self.assertRaises(ValidationError):
            parse_planning(xlsx_with(PLANNING_COLUMNS, []))

    def test_sample_data_parses(self):
        with open("sample_data/planning.xlsx", "rb") as f:
            points = parse_planning(f)
        self.assertEqual(len(points), 10)

    def test_optional_score_and_result(self):
        header = PLANNING_COLUMNS + ["Оценка", "Результат"]

        def opt_row(code, house, score, result):
            d = {c: "" for c in header}
            d.update({
                "Единый код": code, "Населенный пункт": "Москва", "Тип улицы": "ул.",
                "Название улицы": "Ленина", "Номер дома": house, "Цикличность": 1,
                "Код торгового представителя": "TP1", "Оценка": score, "Результат": result,
            })
            return [d[c] for c in header]

        points = parse_planning(xlsx_with(header, [
            opt_row("A001", "1", 4, "80%"),
            opt_row("A002", "2", "", 120),
        ]))
        self.assertEqual(points[0].score, 4.0)
        self.assertEqual(points[0].result, 80.0)
        self.assertIsNone(points[1].score)  # пустая оценка -> не оценено
        self.assertEqual(points[1].result, 120.0)

    def test_no_optional_columns_defaults_none(self):
        points = parse_planning(xlsx_with(PLANNING_COLUMNS, [row()]))
        self.assertIsNone(points[0].score)
        self.assertIsNone(points[0].result)


if __name__ == "__main__":
    unittest.main()
