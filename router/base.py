"""Интерфейс провайдера дорожных расстояний (заменяем без переписывания ядра)."""
from __future__ import annotations

from typing import Optional, Protocol


class RoadDistanceProvider(Protocol):
    def matrix(
        self,
        origins: list[tuple[float, float]],
        destinations: list[tuple[float, float]],
    ) -> Optional[list[list[float]]]:
        """Возвращает матрицу origins x destinations в км или None при ошибке."""
        ...


def distances_to_km(distances: list, rows: int, cols: int) -> Optional[list[list[float]]]:
    """Преобразует матрицу в метрах (список списков) в км.

    Возвращает None, если матрица неполная или содержит пропуски.
    """
    if not distances or len(distances) != rows:
        return None
    matrix = [[0.0] * cols for _ in range(rows)]
    for i, row in enumerate(distances):
        if len(row) != cols:
            return None
        for j, value in enumerate(row):
            if value is None:
                return None
            matrix[i][j] = float(value) / 1000.0
    return matrix
