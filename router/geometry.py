"""Дорожная геометрия маршрута (полилиния по улицам) через OSRM route API.

В отличие от таблицы расстояний (matrix), route API возвращает саму ломаную
по дорогам, поэтому линия на карте идёт по улицам, а не по прямой.

OSRM_BASE_URL может содержать несколько адресов через запятую — они
перебираются по порядку (например, локальный сервер + публичное демо).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from .osrm import _split_urls

logger = logging.getLogger(__name__)


class OsrmRouteGeometry:
    def __init__(self, base_url: str | None = None):
        self.base_urls = _split_urls(base_url)
        self.last_error: str | None = None

    def route(self, coords: list[tuple[float, float]]) -> Optional[list[list[float]]]:
        """Возвращает [[lon, lat], ...] вдоль дорог или None при ошибке.

        `coords` — упорядоченные точки маршрута в формате (lat, lon).
        """
        self.last_error = None
        if not self.base_urls or len(coords) < 2:
            self.last_error = "нет OSRM_BASE_URL" if not self.base_urls else "нужно >= 2 точек"
            return None

        errors = []
        for base_url in self.base_urls:
            line = self._route_once(base_url, coords)
            if line is not None:
                return line
            errors.append(self.last_error)
        self.last_error = "; ".join(e for e in errors if e)
        return None

    def _route_once(
        self,
        base_url: str,
        coords: list[tuple[float, float]],
    ) -> Optional[list[list[float]]]:
        path = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in coords)
        url = f"{base_url}/route/v1/driving/{path}"

        try:
            resp = httpx.get(
                url,
                params={"overview": "full", "geometries": "geojson"},
                timeout=30.0,
            )
        except Exception as exc:
            self.last_error = f"{base_url}: network: {exc}"
            logger.warning("OSRM route request failed (%s): %s", base_url, exc)
            return None

        try:
            resp.raise_for_status()
        except Exception:
            self.last_error = f"{base_url}: HTTP {resp.status_code}: {resp.text[:200]}"
            logger.warning("OSRM route HTTP %s: %s", resp.status_code, resp.text[:200])
            return None

        try:
            data = resp.json()
        except Exception:
            self.last_error = f"{base_url}: response is not JSON"
            logger.warning("OSRM route response is not JSON")
            return None

        if data.get("code") != "Ok":
            self.last_error = f"{base_url}: code={data.get('code')}: {str(data.get('message', ''))[:100]}"
            logger.warning("OSRM route code=%s", data.get("code"))
            return None

        routes = data.get("routes") or []
        if not routes:
            self.last_error = f"{base_url}: нет маршрутов в ответе"
            return None

        geometry = routes[0].get("geometry") or {}
        line = geometry.get("coordinates")
        if not line or len(line) < 2:
            self.last_error = f"{base_url}: пустая геометрия маршрута"
            return None
        return line
