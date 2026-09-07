"""Fallback-провайдер без сети: всегда None (ядро откатывается на haversine)."""
from __future__ import annotations

from typing import Optional

from .base import RoadDistanceProvider


class OfflineRoadDistance(RoadDistanceProvider):
    def matrix(
        self,
        origins: list[tuple[float, float]],
        destinations: list[tuple[float, float]],
    ) -> Optional[list[list[float]]]:
        return None
