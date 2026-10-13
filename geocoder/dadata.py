"""Подсказки адресов (автодополнение) через DaData Suggestions API.

Требует DADATA_API_KEY в окружении. По фрагменту («ленина 15») возвращает список
полных адресов («г Москва, ул Ленина, д 15») для подстановки в поле ввода.
Без ключа или при ошибке сети возвращает пустой список — автодополнение просто
молча не работает, не мешая ручному вводу.
"""
from __future__ import annotations

import os

import httpx

_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address"


def suggest_addresses(query: str, count: int = 8) -> list[str]:
    key = os.environ.get("DADATA_API_KEY", "")
    q = (query or "").strip()
    if not key or len(q) < 3:
        return []
    try:
        resp = httpx.post(
            _URL,
            headers={
                "Authorization": f"Token {key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json={"query": q, "count": count},
            timeout=8.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    out: list[str] = []
    for s in data.get("suggestions", []):
        v = s.get("value") or s.get("unrestricted_value")
        if v:
            out.append(str(v))
    return out


class DadataGeocoder:
    """Геокодер через DaData Suggestions API (возвращает координаты адреса).

    Используется как запасной, когда ключ Яндекса недействителен/исчерпан.
    Кэш — только в памяти (адреса на диск не пишем, как и у Яндекса).
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("DADATA_API_KEY", "")
        self._cache: dict[str, tuple[float, float] | None] = {}
        self.last_error: str | None = None

    def geocode(self, address: str) -> tuple[float, float] | None:
        if not address:
            return None
        key = address.strip().lower()
        if key in self._cache:
            return self._cache[key]
        if not self.api_key:
            self.last_error = "нет DADATA_API_KEY"
            self._cache[key] = None
            return None

        self.last_error = None
        try:
            resp = httpx.post(
                _URL,
                headers={
                    "Authorization": f"Token {self.api_key}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json={"query": address, "count": 1},
                timeout=8.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            self.last_error = f"network: {exc}"
            self._cache[key] = None
            return None

        suggestions = data.get("suggestions", [])
        if not suggestions:
            self.last_error = "адрес не найден"
            self._cache[key] = None
            return None
        geo = suggestions[0].get("data", {})
        lat = geo.get("geo_lat")
        lon = geo.get("geo_lon")
        if lat is None or lon is None:
            self.last_error = "нет координат"
            self._cache[key] = None
            return None
        result = (float(lat), float(lon))
        self._cache[key] = result
        return result
