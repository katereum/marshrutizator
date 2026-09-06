"""Проверка структуры Excel-файлов (раздел 12 ТЗ)."""
from __future__ import annotations

from .columns import PLANNING_COLUMNS, RESULT_COLUMNS
from .errors import FileError, ValidationError


def require_extension(filename: str) -> None:
    if not filename.lower().endswith(".xlsx"):
        raise FileError("Поддерживается только формат .xlsx", {"filename": filename})


def missing_columns(header: list, required: list[str]) -> list[str]:
    present = {str(h).strip() for h in header if h is not None and str(h).strip()}
    return [c for c in required if c not in present]


def validate_planning_header(header: list) -> None:
    missing = missing_columns(header, PLANNING_COLUMNS)
    if missing:
        raise ValidationError(
            f"Отсутствует обязательный столбец: {missing[0]}",
            {"columns": missing},
        )


def validate_template_header(header: list) -> None:
    missing = missing_columns(header, RESULT_COLUMNS)
    if missing:
        raise ValidationError(
            f"В шаблоне отсутствует столбец: {missing[0]}",
            {"columns": missing},
        )
