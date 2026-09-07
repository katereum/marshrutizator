import unittest

from fastapi.testclient import TestClient

from backend.app import app, store


class TestFrontend(unittest.TestCase):
    def setUp(self):
        store._lock.acquire()
        try:
            store._files.clear()
            store._jobs.clear()
        finally:
            store._lock.release()
        self.client = TestClient(app)

    def test_index_served(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Маршрутизатор", r.text)
        self.assertIn("Упорядочь хаос", r.text)

    def test_static_assets_served(self):
        for path in ("/static/styles.css", "/static/app.js",
                     "/static/leaflet/leaflet.js", "/static/leaflet/leaflet.css"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
