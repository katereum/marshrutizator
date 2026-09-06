"""Дорожные расстояния через GraphHopper Matrix API (hosted, нужен ключ).

POST https://graphhopper.com/api/1/matrix?key=KEY
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from .base import RoadDistanceProvider, distances_to_km

logger = logging.getLogger(__name__)

_BASE_URL = "https://graphhopper.com/api/1/matrix"


class GraphHopperRoadDistance(RoadDistanceProvider):
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GRAPHOPPER_API_KEY", "")

    def matrix(self, points: list[tuple[float, float]]) -> Optional[list[list[float]]]:
        if not self.api_key or len(points) < 2:
            return None

        locations = [[lon, lat] for lat, lon in points]
        body = {
            "points": locations,
            "out_arrays": ["distances"],
            "vehicle": "car",
        }

        try:
            resp = httpx.post(
                _BASE_URL,
                params={"key": self.api_key},
                json=body,
                timeout=20.0,
            )
        except Exception as exc:
            logger.warning("GraphHopper matrix request failed: %s", exc)
            return None

        try:
            resp.raise_for_status()
        except Exception:
            logger.warning(
                "GraphHopper matrix HTTP %s: %s", resp.status_code, resp.text[:200]
            )
            return None

        try:
            data = resp.json()
        except Exception:
            logger.warning("GraphHopper matrix response is not JSON")
            return None

        matrix = distances_to_km(data.get("distances"), len(points))
        if matrix is None:
            logger.warning("GraphHopper matrix incomplete")
        return matrix
