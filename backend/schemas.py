"""Pydantic-схемы API (контракт из docs/architecture.md §7)."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class OptimizeRequest(BaseModel):
    planning_file_id: str
    route_template_file_id: str
    period_start: date
    period_end: date
    work_on_weekends: bool = False
    home_address: str | None = None
    # Мягкие целевые ограничения (R3); ядро MVP балансирует к вычисленной цели.
    min_points_per_day: int | None = None
    max_points_per_day: int | None = None
