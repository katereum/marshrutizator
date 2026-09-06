"""Fallback-геокодер без сети: всегда None (кластеризация по адресу, R1)."""
from __future__ import annotations

from typing import Optional

from .base import Geocoder


class OfflineGeocoder(Geocoder):
    def geocode(self, address: str) -> Optional[tuple[float, float]]:
        return None
