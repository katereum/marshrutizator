"""Интерфейс геокодера (заменяем без переписывания приложения, раздел 14 ТЗ)."""
from __future__ import annotations

from typing import Optional, Protocol


class Geocoder(Protocol):
    def geocode(self, address: str) -> Optional[tuple[float, float]]:
        """Возвращает (lat, lon) или None, если адрес не найден."""
        ...
