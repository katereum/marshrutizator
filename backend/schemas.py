"""Pydantic-схемы API (контракт из docs/architecture.md §7)."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel


class OptimizeRequest(BaseModel):
    planning_file_id: str
    route_template_file_id: str
    period_start: date
    period_end: date
    work_on_weekends: bool = False
    home_address: str | None = None
    # Акцент маршрута: экономия (по умолчанию) | проблемные | лучшие.
    focus: Literal["economy", "fix_problems", "top_performers"] = "economy"
    # Мягкие целевые ограничения (R3); ядро MVP балансирует к вычисленной цели.
    min_points_per_day: int | None = None
    max_points_per_day: int | None = None
