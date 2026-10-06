"""Pydantic-схемы API (контракт из docs/architecture.md §7)."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel


class OptimizeRequest(BaseModel):
    planning_file_id: str
    route_template_file_id: str | None = None
    period_start: date
    period_end: date
    work_on_weekends: bool = False
    home_address: str | None = None
    # Переопределение дома по дням недели (0=Пн..6=Вс): {"1": "адрес для вторника"}.
    home_address_overrides: dict[int, str] = {}
    # Акцент маршрута: экономия (по умолчанию) | проблемные | лучшие.
    focus: Literal["economy", "fix_problems", "top_performers"] = "economy"
    # Кол-во точек в день: по умолчанию и по дням недели (0=Пн..6=Вс).
    points_per_day: int | None = None
    points_per_day_overrides: dict[int, int] = {}
    # Подтверждение после предупреждения о расхождении лимитов с реальным
    # числом визитов (см. /api/optimize → needs_confirmation).
    confirm: bool = False
    # Подтверждение после предупреждения о точках без полного адреса
    # (см. /api/optimize → needs_address_confirmation). При true такие точки
    # идут в «неопределённые» и не маршрутизируются.
    confirm_address: bool = False
    # Мягкие целевые ограничения (R3); ядро MVP балансирует к вычисленной цели.
    min_points_per_day: int | None = None
    max_points_per_day: int | None = None
