"""Дорожные расстояния через self-hosted OSRM (без ключа, без внешних лимитов).

OSRM Table API:
GET {base_url}/table/v1/driving/{coords}?annotations=distance&sources=i;j&destinations=k;l
Возвращает матрицу в метрах. `base_url` задаётся через OSRM_BASE_URL
(например, http://localhost:5000).

OSRM_BASE_URL может содержать несколько адресов через запятую — они
перебираются по порядку (например, локальный сервер + публичное демо).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from .base import RoadDistanceProvider, distances_to_km

logger = logging.getLogger(__name__)


def _split_urls(base_url: str | None) -> list[str]:
    raw = base_url if base_url is not None else os.environ.get("OSRM_BASE_URL", "")
    return [u.strip().rstrip("/") for u in raw.split(",") if u.strip()]


class OsrmRoadDistance(RoadDistanceProvider):
    def __init__(self, base_url: str | None = None):
        self.base_urls = _split_urls(base_url)
        self.last_error: str | None = None

    def matrix(
        self,
        origins: list[tuple[float, float]],
        destinations: list[tuple[float, float]],
    ) -> Optional[list[list[float]]]:
        self.last_error = None
        if not self.base_urls or not origins or not destinations:
            self.last_error = "нет OSRM_BASE_URL" if not self.base_urls else None
            return None

        errors = []
        for base_url in self.base_urls:
            matrix = self._matrix_once(base_url, origins, destinations)
            if matrix is not None:
                return matrix
            errors.append(self.last_error)
        self.last_error = "; ".join(e for e in errors if e)
        return None

    def _matrix_once(
        self,
        base_url: str,
        origins: list[tuple[float, float]],
        destinations: list[tuple[float, float]],
    ) -> Optional[list[list[float]]]:
        same = origins == destinations
        points = origins if same else list(origins) + list(destinations)
        m = len(origins)
        k = len(destinations)
        sources = ";".join(str(i) for i in range(m))
        targets = ";".join(str(i) for i in range(m)) if same else ";".join(
            str(i) for i in range(m, m + k)
        )
        coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
        url = f"{base_url}/table/v1/driving/{coords}"

        try:
            resp = httpx.get(
                url,
                params={
                    "annotations": "distance",
                    "sources": sources,
                    "destinations": targets,
                },
                timeout=20.0,
            )
        except Exception as exc:
            self.last_error = f"{base_url}: network: {exc}"
            logger.warning("OSRM matrix request failed (%s): %s", base_url, exc)
            return None

        try:
            resp.raise_for_status()
        except Exception:
            self.last_error = f"{base_url}: HTTP {resp.status_code}: {resp.text[:200]}"
            logger.warning("OSRM matrix HTTP %s: %s", resp.status_code, resp.text[:200])
            return None

        try:
            data = resp.json()
        except Exception:
            self.last_error = f"{base_url}: response is not JSON"
            logger.warning("OSRM matrix response is not JSON")
            return None

        if data.get("code") != "Ok":
            self.last_error = f"{base_url}: code={data.get('code')}: {str(data.get('message', ''))[:100]}"
            logger.warning("OSRM matrix code=%s", data.get("code"))
            return None

        matrix = distances_to_km(data.get("distances"), m, k)
        if matrix is None:
            self.last_error = f"{base_url}: incomplete matrix"
            logger.warning("OSRM matrix incomplete")
        return matrix
