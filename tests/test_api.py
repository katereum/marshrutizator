import io
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.app import app, store
from parser.columns import PLANNING_COLUMNS, RESULT_COLUMNS

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def make_xlsx(header, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def planning_row(code, cycle=1):
    return [code, "1", "Актив", "Москва", "ул.", "Ленина", "1", "", "", "Тверская",
            "", "П", "С", "К", "SUP", "TP1", cycle]


class TestAPI(unittest.TestCase):
    def setUp(self):
        store._lock.acquire()
        try:
            store._files.clear()
            store._jobs.clear()
        finally:
            store._lock.release()
        self.client = TestClient(app)

    def test_end_to_end(self):
        planning = make_xlsx(
            PLANNING_COLUMNS,
            [planning_row("A001", 1), planning_row("A002", 1), planning_row("A003", 1)],
        )
        r = self.client.post(
            "/api/upload/planning",
            files={"file": ("planning.xlsx", planning, XLSX_MIME)},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["row_count"], 3)
        pid = r.json()["file_id"]

        template = make_xlsx(RESULT_COLUMNS, [["" for _ in RESULT_COLUMNS]])
        r = self.client.post(
            "/api/upload/route-template",
            files={"file": ("template.xlsx", template, XLSX_MIME)},
        )
        self.assertEqual(r.status_code, 200)
        tid = r.json()["file_id"]

        with patch("backend.app.geocoder") as mock_geo, patch("backend.app.road_distance") as mock_road:
            mock_geo.geocode.return_value = (55.75, 37.61)
            mock_road.matrix.return_value = [
                [0.0, 1.0, 1.0],
                [1.0, 0.0, 1.0],
                [1.0, 1.0, 0.0],
            ]
            r = self.client.post(
                "/api/optimize",
                json={
                    "planning_file_id": pid,
                    "route_template_file_id": tid,
                    "period_start": "2026-09-01",
                    "period_end": "2026-09-30",
                },
            )
        self.assertEqual(r.status_code, 202)
        jid = r.json()["job_id"]

        r = self.client.get(f"/api/result/{jid}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "COMPLETED")
        self.assertEqual(r.json()["stats"][0]["total_visits"], 3)
        self.assertEqual(r.json()["stats"][0]["violations"], [])

        r = self.client.get(f"/api/result/{jid}/geojson")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["type"], "FeatureCollection")

        r = self.client.get(f"/api/download/{jid}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], XLSX_MIME)

    def test_optimize_fails_without_road_matrix(self):
        planning = make_xlsx(
            PLANNING_COLUMNS,
            [planning_row("A001", 1), planning_row("A002", 1)],
        )
        r = self.client.post(
            "/api/upload/planning",
            files={"file": ("planning.xlsx", planning, XLSX_MIME)},
        )
        pid = r.json()["file_id"]

        template = make_xlsx(RESULT_COLUMNS, [["" for _ in RESULT_COLUMNS]])
        r = self.client.post(
            "/api/upload/route-template",
            files={"file": ("template.xlsx", template, XLSX_MIME)},
        )
        tid = r.json()["file_id"]

        with patch("backend.app.geocoder") as mock_geo, patch("backend.app.road_distance") as mock_road:
            mock_geo.geocode.return_value = (55.75, 37.61)
            mock_road.matrix.return_value = None
            r = self.client.post(
                "/api/optimize",
                json={
                    "planning_file_id": pid,
                    "route_template_file_id": tid,
                    "period_start": "2026-09-01",
                    "period_end": "2026-09-30",
                },
            )

        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["error"]["code"], "OPTIMIZATION_ERROR")

    def test_upload_missing_column_returns_error(self):
        header = [c for c in PLANNING_COLUMNS if c != "Цикличность"]
        rows = [["A001", "1", "Актив", "Москва", "ул.", "Ленина", "1", "", "", "Тверская",
                 "", "П", "С", "К", "SUP", "TP1"]]
        r = self.client.post(
            "/api/upload/planning",
            files={"file": ("p.xlsx", make_xlsx(header, rows), XLSX_MIME)},
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"]["code"], "VALIDATION_ERROR")

    def test_upload_wrong_extension(self):
        r = self.client.post(
            "/api/upload/planning",
            files={"file": ("p.csv", b"not excel", "text/csv")},
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"]["code"], "FILE_ERROR")


if __name__ == "__main__":
    unittest.main()
