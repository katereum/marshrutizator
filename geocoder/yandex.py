"""Геокодер Яндекса (R1). Ключ — из .env или аргумента конструктора."""
from __future__ import annotations

import os
from typing import Optional

import httpx

from .base import Geocoder

_BASE_URL = "https://geocode-maps.yandex.ru/1.x/"


class YandexGeocoder(Geocoder):
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("YANDEX_GEOCODER_API_KEY", "")

    def geocode(self, address: str) -> Optional[tuple[float, float]]:
        if not self.api_key or not address:
            return None
        try:
            resp = httpx.get(
                _BASE_URL,
                params={"apikey": self.api_key, "geocode": address, "format": "json", "results": "1"},
                timeout=10.0,
            )
            resp.raise_for_status()
            members = resp.json()["response"]["GeoObjectCollection"]["featureMember"]
            if not members:
                return None
            lon, lat = members[0]["GeoObject"]["Point"]["pos"].split(" ")
            return float(lat), float(lon)
        except Exception:
            return None
