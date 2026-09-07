import unittest
from unittest.mock import Mock, patch

import httpx

from router.chain import ChainRoadDistance
from router.geometry import OsrmRouteGeometry
from router.graphhopper import GraphHopperRoadDistance
from router.openrouteservice import OpenRouteServiceRoadDistance
from router.osrm import OsrmRoadDistance
from router.yandex import YandexRoadDistance


class _FakeProvider:
    def __init__(self, result):
        self.result = result

    def matrix(self, origins, destinations):
        return self.result


POINTS = [(55.75, 37.62), (55.82, 37.64)]
POINTS_A = [(55.75, 37.62)]
POINTS_B = [(55.82, 37.64)]


class TestChainRoadDistance(unittest.TestCase):
    def test_uses_first_success(self):
        matrix = [[0.0, 1.0], [1.0, 0.0]]
        chain = ChainRoadDistance([_FakeProvider(None), _FakeProvider(matrix)])
        self.assertEqual(chain.matrix(POINTS, POINTS), matrix)

    def test_all_fail_returns_none(self):
        chain = ChainRoadDistance([_FakeProvider(None), _FakeProvider(None)])
        self.assertIsNone(chain.matrix(POINTS, POINTS))


class TestOsrmRoadDistance(unittest.TestCase):
    def test_parses_square_matrix(self):
        osrm = OsrmRoadDistance("http://localhost:5000")
        resp = Mock()
        resp.status_code = 200
        resp.text = ""
        resp.json.return_value = {
            "code": "Ok",
            "distances": [[0.0, 2511.5], [2511.5, 0.0]],
        }
        with patch("router.osrm.httpx.get", return_value=resp) as get:
            matrix = osrm.matrix(POINTS, POINTS)

        self.assertEqual(matrix, [[0.0, 2.5115], [2.5115, 0.0]])
        url = get.call_args[0][0]
        self.assertIn("/table/v1/driving/", url)
        params = get.call_args[1]["params"]
        self.assertEqual(params["annotations"], "distance")
        self.assertIn("sources", params)
        self.assertIn("destinations", params)

    def test_parses_rectangular_matrix(self):
        osrm = OsrmRoadDistance("http://localhost:5000")
        resp = Mock()
        resp.status_code = 200
        resp.text = ""
        resp.json.return_value = {"code": "Ok", "distances": [[1234.0]]}
        with patch("router.osrm.httpx.get", return_value=resp):
            matrix = osrm.matrix(POINTS_A, POINTS_B)
        self.assertEqual(matrix, [[1.234]])

    def test_no_base_url_returns_none(self):
        osrm = OsrmRoadDistance("")
        self.assertIsNone(osrm.matrix(POINTS, POINTS))

    def test_falls_back_to_second_url(self):
        osrm = OsrmRoadDistance("http://localhost:5000,http://localhost:5001")
        ok = Mock()
        ok.status_code = 200
        ok.text = ""
        ok.json.return_value = {"code": "Ok", "distances": [[0.0, 2511.5], [2511.5, 0.0]]}
        with patch("router.osrm.httpx.get", side_effect=[httpx.ConnectError("refused"), ok]) as get:
            matrix = osrm.matrix(POINTS, POINTS)

        self.assertEqual(matrix, [[0.0, 2.5115], [2.5115, 0.0]])
        self.assertEqual(get.call_count, 2)
        self.assertIn("localhost:5001", get.call_args[0][0])


class TestYandexRoadDistance(unittest.TestCase):
    def test_parses_matrix(self):
        ya = YandexRoadDistance("key")
        resp = Mock()
        resp.status_code = 200
        resp.text = ""
        resp.json.return_value = {
            "rows": [
                {"elements": [{"distance": {"value": 0}}, {"distance": {"value": 2511}}]},
                {"elements": [{"distance": {"value": 2511}}, {"distance": {"value": 0}}]},
            ]
        }
        with patch("router.yandex.httpx.post", return_value=resp) as post:
            matrix = ya.matrix(POINTS, POINTS)

        self.assertEqual(matrix, [[0.0, 2.511], [2.511, 0.0]])
        self.assertEqual(post.call_args[1]["headers"], {"Authorization": "key"})

    def test_http_error_returns_none_without_apikey_retry(self):
        ya = YandexRoadDistance("key")
        resp = Mock()
        resp.status_code = 403
        resp.text = ""
        resp.raise_for_status.side_effect = httpx.HTTPStatusError("forbidden", request=Mock(), response=resp)
        with patch("router.yandex.httpx.post", return_value=resp) as post:
            self.assertIsNone(ya.matrix(POINTS, POINTS))

        # Один запрос с Authorization; не делаем сломанный ретрай через apikey.
        self.assertEqual(post.call_count, 1)
        self.assertIn("403", ya.last_error)


class TestGraphHopperRoadDistance(unittest.TestCase):
    def test_parses_matrix(self):
        gh = GraphHopperRoadDistance("key")
        resp = Mock()
        resp.status_code = 200
        resp.text = ""
        resp.json.return_value = {"distances": [[0.0, 3000.0], [3000.0, 0.0]]}
        with patch("router.graphhopper.httpx.post", return_value=resp) as post:
            matrix = gh.matrix(POINTS, POINTS)

        self.assertEqual(matrix, [[0.0, 3.0], [3.0, 0.0]])
        self.assertEqual(post.call_args[1]["params"], {"key": "key"})
        body = post.call_args[1]["json"]
        self.assertEqual(body["points"][0], [37.62, 55.75])
        self.assertIn("distances", body["out_arrays"])

    def test_rectangular_matrix(self):
        gh = GraphHopperRoadDistance("key")
        resp = Mock()
        resp.status_code = 200
        resp.text = ""
        resp.json.return_value = {"distances": [[4000.0]]}
        with patch("router.graphhopper.httpx.post", return_value=resp) as post:
            matrix = gh.matrix(POINTS_A, POINTS_B)

        self.assertEqual(matrix, [[4.0]])
        body = post.call_args[1]["json"]
        self.assertEqual(body["from_points"], [0])
        self.assertEqual(body["to_points"], [1])


class TestOpenRouteServiceRoadDistance(unittest.TestCase):
    def test_parses_matrix(self):
        ors = OpenRouteServiceRoadDistance("key")
        resp = Mock()
        resp.status_code = 200
        resp.text = ""
        resp.json.return_value = {"distances": [[0.0, 4000.0], [4000.0, 0.0]]}
        with patch("router.openrouteservice.httpx.post", return_value=resp) as post:
            matrix = ors.matrix(POINTS, POINTS)

        self.assertEqual(matrix, [[0.0, 4.0], [4.0, 0.0]])
        self.assertEqual(post.call_args[1]["headers"], {"Authorization": "key"})
        body = post.call_args[1]["json"]
        self.assertEqual(body["locations"][0], [37.62, 55.75])

    def test_rectangular_matrix(self):
        ors = OpenRouteServiceRoadDistance("key")
        resp = Mock()
        resp.status_code = 200
        resp.text = ""
        resp.json.return_value = {"distances": [[5000.0]]}
        with patch("router.openrouteservice.httpx.post", return_value=resp) as post:
            matrix = ors.matrix(POINTS_A, POINTS_B)

        self.assertEqual(matrix, [[5.0]])
        body = post.call_args[1]["json"]
        self.assertEqual(body["sources"], [0])
        self.assertEqual(body["destinations"], [1])


class TestOsrmRouteGeometry(unittest.TestCase):
    def test_returns_geojson_coordinates(self):
        geo = OsrmRouteGeometry("http://localhost:5000")
        resp = Mock()
        resp.status_code = 200
        resp.text = ""
        resp.json.return_value = {
            "code": "Ok",
            "routes": [
                {"geometry": {"type": "LineString", "coordinates": [[37.62, 55.75], [37.63, 55.76]]}}
            ],
        }
        with patch("router.geometry.httpx.get", return_value=resp) as get:
            line = geo.route(POINTS)

        self.assertEqual(line, [[37.62, 55.75], [37.63, 55.76]])
        url = get.call_args[0][0]
        self.assertIn("/route/v1/driving/", url)
        self.assertEqual(
            get.call_args[1]["params"],
            {"overview": "full", "geometries": "geojson"},
        )

    def test_no_base_url_returns_none(self):
        geo = OsrmRouteGeometry("")
        self.assertIsNone(geo.route(POINTS))
        self.assertIsNotNone(geo.last_error)

    def test_bad_code_returns_none(self):
        geo = OsrmRouteGeometry("http://localhost:5000")
        resp = Mock()
        resp.status_code = 200
        resp.text = ""
        resp.json.return_value = {"code": "NoRoute", "message": "no route"}
        with patch("router.geometry.httpx.get", return_value=resp):
            self.assertIsNone(geo.route(POINTS))
        self.assertIn("NoRoute", geo.last_error)


if __name__ == "__main__":
    unittest.main()
