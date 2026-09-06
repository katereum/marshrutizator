import io
import re
import unittest
from datetime import date

from openpyxl import load_workbook, Workbook

from exporter.exporter import export_route
from optimizer.models import Point
from optimizer.pipeline import build_route
from parser.columns import RESULT_COLUMNS


def template_bytes():
    wb = Workbook()
    ws = wb.active
    ws.append(RESULT_COLUMNS)
    ws.append(["" for _ in RESULT_COLUMNS])  # строка-образец формата
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestExporter(unittest.TestCase):
    def test_export_preserves_header_and_fills_values(self):
        points = [
            Point(
                id="A001",
                trade_rep_code="TP1",
                frequency=1,
                locality="Москва",
                street="ул ленина",
                house="1",
                original={
                    "Единый код": "A001",
                    "Старый код": "1001",
                    "Населенный пункт": "Москва",
                    "Тип улицы": "ул.",
                    "Название улицы": "Ленина",
                    "Номер дома": "1",
                    "Код торгового представителя": "TP1",
                },
            )
        ]
        result = build_route(points, date(2026, 9, 1), date(2026, 9, 30))
        data = export_route(io.BytesIO(template_bytes()), result, {p.id: p for p in points})

        wb = load_workbook(io.BytesIO(data))
        ws = wb.active
        headers = [ws.cell(row=1, column=c).value for c in range(1, len(RESULT_COLUMNS) + 1)]
        self.assertEqual(headers, RESULT_COLUMNS)

        found = None
        for r in range(2, ws.max_row + 1):
            if ws.cell(row=r, column=4).value == "A001":  # колонка «Единый код»
                found = r
                break
        self.assertIsNotNone(found)
        self.assertEqual(ws.cell(row=found, column=1).value, 1)  # «№ п/п»
        self.assertRegex(str(ws.cell(row=found, column=2).value), r"\d{2}\.\d{2}\.\d{4}")
        self.assertIn(ws.cell(row=found, column=3).value, [
            "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье",
        ])
        self.assertEqual(ws.cell(row=found, column=4).value, "A001")


if __name__ == "__main__":
    unittest.main()
