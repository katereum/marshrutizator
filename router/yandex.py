"""Дорожные расстояния через Яндекс.Маршрутизация (matrix, режим driving).

Используется API v2: POST https://api.routing.yandex.net/v2/matrix
Ключ передаётся в заголовке Authorization. При 429/5xx делаем короткий ретрай;
если матрица всё равно не получена — возвращаем None (ядро откатывается на
haversine) и пишем предупреждение в лог.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

from .base import RoadDistanceProvider

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.routing.yandex.net/v2/matrix"
_RETRIABLE = {429, 500, 502, 503, 504}


class YandexRoadDistance(RoadDistanceProvider):
    def __init__(self, api_key: str | None = None):
        if api_key is None:
            api_key = (
                os.environ.get("YANDEX_ROUTING_API_KEY")
                or os.environ.get("YANDEX_GEOCODER_API_KEY", "")
            )
        self.api_key = api_key
        self.last_error: str | None = None

    def matrix(
        self,
        origins: list[tuple[float, float]],
        destinations: list[tuple[float, float]],
    ) -> Optional[list[list[float]]]:
        self.last_error = None
        if not self.api_key or not origins or not destinations:
            self.last_error = "нет ключа"
            return None

        body = {
            "origins": [{"latitude": lat, "longitude": lon} for lat, lon in origins],
            "destinations": [{"latitude": lat, "longitude": lon} for lat, lon in destinations],
            "mode": "driving",
        }

        data = None
        last_status = None
        for attempt in range(3):
            try:
                resp = httpx.post(
                    _BASE_URL,
                    headers={"Authorization": self.api_key},
                    json=body,
                    timeout=20.0,
                )
            except Exception as exc:
                self.last_error = f"network: {exc}"
                logger.warning("Yandex road matrix request failed: %s", exc)
                return None

            last_status = resp.status_code

            if resp.status_code in _RETRIABLE:
                time.sleep(0.5 * (attempt + 1))
                continue
            try:
                resp.raise_for_status()
            except Exception:
                self.last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.warning(
                    "Yandex road matrix HTTP %s: %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return None
            data = resp.json()
            break

        if data is None:
            self.last_error = f"HTTP {last_status} после ретраев"
            logger.warning(
                "Yandex road matrix unavailable after retries (last status %s)",
                last_status,
            )
            return None

        rows = data.get("rows") or []
        n_rows = len(origins)
        n_cols = len(destinations)
        if len(rows) != n_rows:
            self.last_error = f"rows mismatch ({len(rows)} != {n_rows})"
            return None

        matrix = [[0.0] * n_cols for _ in range(n_rows)]
        for i, row in enumerate(rows):
            elements = row.get("elements") or []
            if len(elements) != n_cols:
                self.last_error = f"incomplete row {i}"
                return None
            for j, element in enumerate(elements):
                value = (element.get("distance") or {}).get("value")
                if value is None:
                    self.last_error = f"missing distance at ({i}, {j})"
                    return None
                matrix[i][j] = float(value) / 1000.0
        return matrix
