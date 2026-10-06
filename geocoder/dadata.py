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
