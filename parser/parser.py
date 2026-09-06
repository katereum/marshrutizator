"""Чтение базы планирования из .xlsx в нормализованные Point (раздел 4, 10 ТЗ)."""
from __future__ import annotations

from openpyxl import load_workbook

from optimizer.models import Point
from optimizer.normalizer import canonical_address, normalize_street

from .columns import CRITICAL_PLANNING_COLUMNS
from .errors import ValidationError
from .validator import validate_planning_header


def _read_header_and_rows(fileobj):
    wb = load_workbook(fileobj, read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    header = next(rows, None)
    return header, rows


def parse_planning(fileobj) -> list[Point]:
    """Парсит базу планирования. Первая строка — заголовок.

    Поднимает ValidationError с понятным сообщением при структурных ошибках.
    """
    header, rows = _read_header_and_rows(fileobj)
    if header is None:
        raise ValidationError("Файл пуст")
    header = [str(c).strip() if c is not None else "" for c in header]
    validate_planning_header(header)

    points: list[Point] = []
    seen_codes: set[str] = set()

    for row_num, row in enumerate(rows, start=2):
        if row is None or all(c is None or str(c).strip() == "" for c in row):
            continue
        raw = {
            header[i]: (row[i] if i < len(row) and row[i] is not None else "")
            for i in range(len(header))
        }

        for col in CRITICAL_PLANNING_COLUMNS:
            if str(raw.get(col, "")).strip() == "":
                raise ValidationError(f"Пустое обязательное поле «{col}» в строке {row_num}")

        code = str(raw["Единый код"]).strip()
        if code in seen_codes:
            raise ValidationError(f"Дублирующийся Единый код: {code}")
        seen_codes.add(code)

        try:
            frequency = int(float(str(raw["Цикличность"]).strip()))
        except ValueError:
            raise ValidationError(
                f"Некорректная цикличность в строке {row_num}: «{raw['Цикличность']}»"
            )
        if frequency < 1:
            raise ValidationError(f"Цикличность должна быть >= 1 (строка {row_num})")

        locality = str(raw["Населенный пункт"]).strip()
        metro = str(raw["Станция метро"]).strip()
        house = str(raw["Номер дома"]).strip()
        street = normalize_street(f"{raw['Тип улицы']} {raw['Название улицы']}".strip())
        address = canonical_address(locality, metro, street, house)

        points.append(
            Point(
                id=code,
                trade_rep_code=str(raw["Код торгового представителя"]).strip(),
                frequency=frequency,
                locality=locality,
                street=street,
                house=house,
                metro=metro,
                normalized_address=address,
                original={k: (v if v is not None else "") for k, v in raw.items()},
            )
        )

    if not points:
        raise ValidationError("База не содержит точек")
    return points


def read_template_header(fileobj) -> list[str]:
    """Возвращает столбцы шаблона маршрутного листа (первая строка)."""
    header, _ = _read_header_and_rows(fileobj)
    if header is None:
        raise ValidationError("Шаблон пуст")
    return [str(c).strip() if c is not None else "" for c in header]
