"""Нормализация адресов (раздел 13 ТЗ).

Нормализация применяется только внутри алгоритма: исходные значения не
изменяются, а приводятся к каноническому виду для сравнения и группировки.
"""
from __future__ import annotations

import re
from dataclasses import replace

from .models import Point

# Сокращения типов улиц -> канонический токен.
_STREET_ABBR = {
    "улица": "ул",
    "ул.": "ул",
    "ул": "ул",
    "проспект": "пр-т",
    "пр.": "пр-т",
    "пр-т": "пр-т",
    "пр": "пр-т",
    "переулок": "пер",
    "пер.": "пер",
    "пер": "пер",
    "проезд": "пр-д",
    "пр-д.": "пр-д",
    "пр-д": "пр-д",
    "бульвар": "б-р",
    "б-р.": "б-р",
    "б-р": "б-р",
    "площадь": "пл",
    "пл.": "пл",
    "пл": "пл",
    "шоссе": "ш",
    "ш.": "ш",
    "ш": "ш",
    "набережная": "наб",
    "наб.": "наб",
    "наб": "наб",
}


def normalize_token(value: str | None) -> str:
    """Нижний регистр, без точек/кавычек, схлопывание пробелов."""
    if value is None:
        return ""
    v = str(value).strip().lower()
    v = re.sub(r'[."\']', "", v)
    v = re.sub(r"\s+", " ", v)
    return v.strip()


def normalize_street(value: str | None) -> str:
    """Канонический вид названия улицы (сокращения -> токен)."""
    tokens = normalize_token(value).split()
    return " ".join(_STREET_ABBR.get(t, t) for t in tokens)


def canonical_address(locality: str, metro: str, street: str, house: str) -> str:
    """Канонический ключ адреса для сравнения/группировки."""
    parts = [
        normalize_token(locality),
        normalize_token(metro),
        normalize_street(street),
        normalize_token(house),
    ]
    return "|".join(p for p in parts if p)


def normalize_point(point: Point) -> Point:
    """Возвращает копию Point с нормализованной улицей и каноническим адресом."""
    street = normalize_street(point.street)
    address = canonical_address(point.locality, point.metro, street, point.house)
    return replace(point, street=street, normalized_address=address)
