"""Value-объекты ядра оптимизации.

Слои данных разделены (раздел 33 ТЗ): оригинальные данные остаются в слое
парсера; ядро работает с нормализованными Point + гео-координатами, затем с
Visit -> DaySchedule -> RouteResult.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class Point:
    """Нормализованная торговая точка + опциональные координаты (слои 2–3)."""

    id: str                       # Единый код (уникальный ключ)
    trade_rep_code: str           # Код торгового представителя
    frequency: int                # цикличность, >= 1
    locality: str = ""            # населённый пункт
    street: str = ""              # нормализованная улица
    house: str = ""
    metro: str = ""
    normalized_address: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    score: Optional[float] = None       # «Оценка» 0..5; None = не оценено
    result: Optional[float] = None      # «Результат»; произвольные единицы, больше = лучше
    original: dict = field(default_factory=dict)  # исходная строка Excel (для экспорта без искажений)

    @property
    def has_coords(self) -> bool:
        return self.latitude is not None and self.longitude is not None


HOME_ID = "__home__"


@dataclass(frozen=True)
class Visit:
    """Один требуемый визит точки (слой 4)."""

    point_id: str
    slot_index: int               # 0..frequency-1, для равномерной раскладки
    cluster_id: int = -1

    @property
    def visit_id(self) -> str:
        return f"{self.point_id}#{self.slot_index}"


@dataclass
class DaySchedule:
    """Порядок посещения внутри одного дня (слой 6)."""

    date: date
    weekday: int
    ordered_visits: list[str] = field(default_factory=list)


@dataclass
class RouteStats:
    total_points: int = 0
    total_visits: int = 0
    per_day_load: list[int] = field(default_factory=list)
    score: float = 0.0
    violations: list[str] = field(default_factory=list)
    total_km: float = 0.0


@dataclass
class RouteResult:
    job_id: str
    trade_rep_code: str
    period_start: date
    period_end: date
    days: list[DaySchedule] = field(default_factory=list)
    stats: RouteStats = field(default_factory=RouteStats)
    warnings: list[str] = field(default_factory=list)
    focus: str = "economy"                       # акцент маршрута
    priority: dict = field(default_factory=dict)  # point_id -> приоритет 0..1
