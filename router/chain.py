"""Цепочка провайдеров дорожных расстояний: первый успешный ответ побеждает."""
from __future__ import annotations

import logging
from typing import Optional

from .base import RoadDistanceProvider

logger = logging.getLogger(__name__)


class ChainRoadDistance(RoadDistanceProvider):
    def __init__(self, providers: list[RoadDistanceProvider]):
        self.providers = list(providers)

    def matrix(self, points: list[tuple[float, float]]) -> Optional[list[list[float]]]:
        for provider in self.providers:
            matrix = provider.matrix(points)
            if matrix is not None:
                return matrix
        logger.warning("All road distance providers failed; falling back to haversine")
        return None
