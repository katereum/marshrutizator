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
        self.api_key = (
            api_key
            or os.environ.get("YANDEX_ROUTING_API_KEY")
            or os.environ.get("YANDEX_GEOCODER_API_KEY", "")
        )

    def matrix(self, points: list[tuple[float, float]]) -> Optional[list[list[float]]]:
        if not self.api_key:
            logger.warning(
                "Yandex road matrix skipped: нет YANDEX_ROUTING_API_KEY / YANDEX_GEOCODER_API_KEY"
            )
            return None
        if len(points) < 2:
            return None

        origins = [{"latitude": lat, "longitude": lon} for lat, lon in points]
        body = {"origins": origins, "destinations": origins, "mode": "driving"}

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
            except Exception as exc:  # сетевые ошибки
                logger.warning("Yandex road matrix request failed: %s", exc)
                return None

            last_status = resp.status_code
            if resp.status_code in _RETRIABLE:
                time.sleep(0.5 * (attempt + 1))
                continue
            try:
                resp.raise_for_status()
            except Exception:
                logger.warning(
                    "Yandex road matrix HTTP %s: %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return None
            data = resp.json()
            break

        if data is None:
            logger.warning(
                "Yandex road matrix unavailable after retries (last status %s)",
                last_status,
            )
            return None

        rows = data.get("rows") or []
        n = len(rows)
        if n != len(points):
            logger.warning("Yandex road matrix rows mismatch (%s != %s)", n, len(points))
            return None

        matrix = [[0.0] * n for _ in range(n)]
        for i, row in enumerate(rows):
            elements = row.get("elements") or []
            if len(elements) != n:
                logger.warning("Yandex road matrix incomplete row %s", i)
                return None
            for j, element in enumerate(elements):
                value = (element.get("distance") or {}).get("value")
                if value is None:
                    logger.warning(
                        "Yandex road matrix missing distance at (%s, %s); fallback to haversine",
                        i,
                        j,
                    )
                    return None
                matrix[i][j] = float(value) / 1000.0
        return matrix
