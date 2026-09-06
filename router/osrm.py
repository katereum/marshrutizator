"""Дорожные расстояния через self-hosted OSRM (без ключа, без внешних лимитов).

OSRM Table API: GET {base_url}/table/v1/driving/{lon},{lat};...?annotations=distance
Возвращает матрицу в метрах. `base_url` задаётся через OSRM_BASE_URL
(например, http://localhost:5000).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from .base import RoadDistanceProvider

logger = logging.getLogger(__name__)


class OsrmRoadDistance(RoadDistanceProvider):
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or os.environ.get("OSRM_BASE_URL", "")).rstrip("/")

    def matrix(self, points: list[tuple[float, float]]) -> Optional[list[list[float]]]:
        if not self.base_url or len(points) < 2:
            return None

        coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
        url = f"{self.base_url}/table/v1/driving/{coords}"

        try:
            resp = httpx.get(url, params={"annotations": "distance"}, timeout=20.0)
        except Exception as exc:
            logger.warning("OSRM matrix request failed: %s", exc)
            return None

        try:
            resp.raise_for_status()
        except Exception:
            logger.warning("OSRM matrix HTTP %s: %s", resp.status_code, resp.text[:200])
            return None

        try:
            data = resp.json()
        except Exception:
            logger.warning("OSRM matrix response is not JSON")
            return None

        if data.get("code") != "Ok":
            logger.warning("OSRM matrix code=%s", data.get("code"))
            return None

        distances = data.get("distances") or []
        n = len(points)
        if len(distances) != n:
            logger.warning("OSRM matrix rows mismatch (%s != %s)", len(distances), n)
            return None

        matrix = [[0.0] * n for _ in range(n)]
        for i, row in enumerate(distances):
            if len(row) != n:
                logger.warning("OSRM matrix incomplete row %s", i)
                return None
            for j, value in enumerate(row):
                if value is None:
                    logger.warning("OSRM matrix missing distance at (%s, %s)", i, j)
                    return None
                matrix[i][j] = float(value) / 1000.0
        return matrix
