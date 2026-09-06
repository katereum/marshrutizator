import unittest
from unittest.mock import Mock, patch

from router.chain import ChainRoadDistance
from router.graphhopper import GraphHopperRoadDistance
from router.openrouteservice import OpenRouteServiceRoadDistance
from router.osrm import OsrmRoadDistance


class _FakeProvider:
    def __init__(self, result):
        self.result = result

    def matrix(self, points):
        return self.result


class TestChainRoadDistance(unittest.TestCase):
    def test_uses_first_success(self):
        matrix = [[0.0, 1.0], [1.0, 0.0]]
        chain = ChainRoadDistance([_FakeProvider(None), _FakeProvider(matrix)])
        self.assertEqual(chain.matrix([(0, 0), (0, 0)]), matrix)

    def test_all_fail_returns_none(self):
        chain = ChainRoadDistance([_FakeProvider(None), _FakeProvider(None)])
        self.assertIsNone(chain.matrix([(0, 0), (0, 0)]))


class TestOsrmRoadDistance(unittest.TestCase):
    def test_parses_matrix_and_builds_url(self):
        osrm = OsrmRoadDistance("http://localhost:5000")
        resp = Mock()
        resp.status_code = 200
        resp.text = ""
        resp.json.return_value = {
            "code": "Ok",
            "distances": [[0.0, 2511.5], [2511.5, 0.0]],
        }
        with patch("router.osrm.httpx.get", return_value=resp) as get:
            matrix = osrm.matrix([(55.75, 37.62), (55.82, 37.64)])

        self.assertEqual(matrix, [[0.0, 2.5115], [2.5115, 0.0]])
        url = get.call_args[0][0]
        self.assertIn("/table/v1/driving/", url)
        self.assertEqual(get.call_args[1]["params"], {"annotations": "distance"})

    def test_no_base_url_returns_none(self):
        osrm = OsrmRoadDistance("")
        self.assertIsNone(osrm.matrix([(0, 0), (0, 0)]))


class TestGraphHopperRoadDistance(unittest.TestCase):
    def test_parses_matrix(self):
        gh = GraphHopperRoadDistance("key")
        resp = Mock()
        resp.status_code = 200
        resp.text = ""
        resp.json.return_value = {"distances": [[0.0, 3000.0], [3000.0, 0.0]]}
        with patch("router.graphhopper.httpx.post", return_value=resp) as post:
            matrix = gh.matrix([(55.75, 37.62), (55.82, 37.64)])

        self.assertEqual(matrix, [[0.0, 3.0], [3.0, 0.0]])
        self.assertEqual(post.call_args[1]["params"], {"key": "key"})
        body = post.call_args[1]["json"]
        self.assertEqual(body["points"][0], [37.62, 55.75])
        self.assertIn("distances", body["out_arrays"])


class TestOpenRouteServiceRoadDistance(unittest.TestCase):
    def test_parses_matrix(self):
        ors = OpenRouteServiceRoadDistance("key")
        resp = Mock()
        resp.status_code = 200
        resp.text = ""
        resp.json.return_value = {"distances": [[0.0, 4000.0], [4000.0, 0.0]]}
        with patch("router.openrouteservice.httpx.post", return_value=resp) as post:
            matrix = ors.matrix([(55.75, 37.62), (55.82, 37.64)])

        self.assertEqual(matrix, [[0.0, 4.0], [4.0, 0.0]])
        self.assertEqual(post.call_args[1]["headers"], {"Authorization": "key"})
        self.assertEqual(post.call_args[1]["json"]["locations"][0], [37.62, 55.75])


if __name__ == "__main__":
    unittest.main()
