"""Дорожные расстояния через OpenRouteService Matrix API (hosted, нужен ключ).

POST https://api.openrouteservice.org/v2/matrix/driving-car
Ключ передаётся в заголовке Authorization.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from .base import RoadDistanceProvider, distances_to_km

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.openrouteservice.org/v2/matrix/driving-car"


class OpenRouteServiceRoadDistance(RoadDistanceProvider):
    def __init__(self, api_key: str | None = None):
        if api_key is None:
            api_key = os.environ.get("OPENROUTESERVICE_API_KEY", "")
        self.api_key = api_key
        self.last_error: str | None = None

    def matrix(
        self,
        origins: list[tuple[float, float]],
        destinations: list[tuple[float, float]],
    ) -> Optional[list[list[float]]]:
        self.last_error = None
        if not self.api_key or not origins or not destinations:
            self.last_error = "нет ключа" if not self.api_key else None
            return None

        same = origins == destinations
        points = origins if same else list(origins) + list(destinations)
        m = len(origins)
        k = len(destinations)

        body = {
            "locations": [[lon, lat] for lat, lon in points],
            "metrics": ["distance"],
        }
        if not same:
            body["sources"] = list(range(m))
            body["destinations"] = list(range(m, m + k))

        try:
            resp = httpx.post(
                _BASE_URL,
                headers={"Authorization": self.api_key},
                json=body,
                timeout=20.0,
            )
        except Exception as exc:
            self.last_error = f"network: {exc}"
            logger.warning("OpenRouteService matrix request failed: %s", exc)
            return None

        try:
            resp.raise_for_status()
        except Exception:
            self.last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            logger.warning(
                "OpenRouteService matrix HTTP %s: %s",
                resp.status_code,
                resp.text[:200],
            )
            return None

        try:
            data = resp.json()
        except Exception:
            self.last_error = "response is not JSON"
            logger.warning("OpenRouteService matrix response is not JSON")
            return None

        matrix = distances_to_km(data.get("distances"), m, k)
        if matrix is None:
            self.last_error = "incomplete matrix"
            logger.warning("OpenRouteService matrix incomplete")
        return matrix
