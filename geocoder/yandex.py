"""Геокодер Яндекса (R1). Ключ — из .env или аргумента конструктора.

Особенности:
- кэширует результат по нормализованному адресу (одинаковый адрес → одинаковые
  координаты и один запрос к API, а не по запросу на точку);
- кэш сохраняется на диск, чтобы повторные прогоны той же базы не жгли лимит;
- короткий ретрай при 429/5xx (лимит/сбой Яндекса).
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Optional

import httpx

from .base import Geocoder

_BASE_URL = "https://geocode-maps.yandex.ru/1.x/"
_RETRIABLE = {429, 500, 502, 503, 504}
_CACHE_FILE = Path(os.environ.get("GEOCODER_CACHE_FILE", ".cache/geocoder.json"))


def _normalize(address: str) -> str:
    return re.sub(r"\s+", " ", address.strip().lower())


class YandexGeocoder(Geocoder):
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("YANDEX_GEOCODER_API_KEY", "")
        self._cache: dict[str, Optional[tuple[float, float]]] = self._load_disk()
        self.last_error: str | None = None

    def _load_disk(self) -> dict[str, Optional[tuple[float, float]]]:
        try:
            if _CACHE_FILE.exists():
                data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
                return {k: (tuple(v) if v else None) for k, v in data.items()}
        except Exception:
            pass
        return {}

    def _save_disk(self) -> None:
        try:
            _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = {k: (list(v) if v else None) for k, v in self._cache.items()}
            _CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def geocode(self, address: str) -> Optional[tuple[float, float]]:
        if not address:
            return None
        key = _normalize(address)
        if key in self._cache:
            return self._cache[key]
        if not self.api_key:
            self.last_error = "нет YANDEX_GEOCODER_API_KEY"
            self._cache[key] = None
            self._save_disk()
            return None

        self.last_error = None
        for attempt in range(3):
            try:
                resp = httpx.get(
                    _BASE_URL,
                    params={
                        "apikey": self.api_key,
                        "geocode": address,
                        "format": "json",
                        "results": "1",
                    },
                    timeout=10.0,
                )
            except Exception as exc:
                self.last_error = f"network: {exc}"
                time.sleep(0.4 * (attempt + 1))
                continue

            if resp.status_code in _RETRIABLE:
                self.last_error = f"HTTP {resp.status_code} (лимит/сбой), попытка {attempt + 1}"
                time.sleep(0.5 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                self.last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                self._cache[key] = None
                self._save_disk()
                return None

            try:
                members = resp.json()["response"]["GeoObjectCollection"]["featureMember"]
            except Exception as exc:
                self.last_error = f"не JSON: {exc}"
                self._cache[key] = None
                self._save_disk()
                return None

            if not members:
                self.last_error = "адрес не найден"
                self._cache[key] = None
                self._save_disk()
                return None

            lon, lat = members[0]["GeoObject"]["Point"]["pos"].split(" ")
            result = (float(lat), float(lon))
            self._cache[key] = result
            self._save_disk()
            return result

        self.last_error = f"{self.last_error or 'не удалось'} (после ретраев)"
        self._cache[key] = None
        self._save_disk()
        return None
