"""Интерфейс провайдера дорожных расстояний (заменяем без переписывания ядра)."""
from __future__ import annotations

from typing import Optional, Protocol


class RoadDistanceProvider(Protocol):
    def matrix(self, points: list[tuple[float, float]]) -> Optional[list[list[float]]]:
        """Возвращает матрицу расстояний в км (n x n) или None при ошибке."""
        ...


def distances_to_km(distances: list, n: int) -> Optional[list[list[float]]]:
    """Преобразует матрицу в метрах (список списков) в км.

    Возвращает None, если матрица неполная или содержит пропуски.
    """
    if not distances or len(distances) != n:
        return None
    matrix = [[0.0] * n for _ in range(n)]
    for i, row in enumerate(distances):
        if len(row) != n:
            return None
        for j, value in enumerate(row):
            if value is None:
                return None
            matrix[i][j] = float(value) / 1000.0
    return matrix
