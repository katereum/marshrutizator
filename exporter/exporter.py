"""Заполнение шаблона маршрутного листа (раздел 24 ТЗ, R6: стили + значения)."""
from __future__ import annotations

import io
from copy import copy
from typing import BinaryIO

from openpyxl import load_workbook

from optimizer.models import Point, RouteResult

WEEKDAYS_RU = [
    "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье",
]


def _find_header(ws) -> tuple[int, dict[str, int]] | None:
    for r in range(1, min(ws.max_row, 10) + 1):
        vals = [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]
        names = {str(v).strip(): c for c, v in enumerate(vals, start=1) if v is not None and str(v).strip()}
        if "Единый код" in names and "Дата визита" in names:
            return r, names
    return None


def _copy_style(dst, src) -> None:
    dst.font = copy(src.font)
    dst.border = copy(src.border)
    dst.fill = copy(src.fill)
    dst.alignment = copy(src.alignment)
    dst.number_format = src.number_format
    dst.protection = copy(src.protection)


def export_route(template: BinaryIO, result: RouteResult, points_by_id: dict[str, Point]) -> bytes:
    """Заполняет шаблон и возвращает .xlsx в виде bytes."""
    wb = load_workbook(template)
    ws = wb.active

    found = _find_header(ws)
    if found is None:
        raise ValueError("В шаблоне не найдена строка заголовка (Единый код + Дата визита)")
    header_row, col_index = found

    sample_row = header_row + 1
    has_sample = ws.cell(row=sample_row, column=col_index["Единый код"]).value not in (None, "")

    write_row = sample_row if has_sample else header_row + 1

    num = 1
    for day in result.days:
        for vid in day.ordered_visits:
            point = points_by_id.get(vid.rsplit("#", 1)[0])
            if point is None:
                continue
            orig = point.original
            values = {
                "№ п/п": num,
                "Дата визита": day.date.strftime("%d.%m.%Y"),
                "День недели": WEEKDAYS_RU[day.weekday],
                "Единый код": orig.get("Единый код", point.id),
                "Старый код": orig.get("Старый код", ""),
                "Статус": orig.get("Статус", ""),
                "Населенный пункт": orig.get("Населенный пункт", ""),
                "Тип улицы": orig.get("Тип улицы", ""),
                "Название улицы": orig.get("Название улицы", ""),
                "Номер дома": orig.get("Номер дома", ""),
                "Номер строения": orig.get("Номер строения", ""),
                "Номер корпуса": orig.get("Номер корпуса", ""),
                "Станция метро": orig.get("Станция метро", ""),
                "Дополнительное описание месторасположения точки": orig.get(
                    "Дополнительное описание месторасположения точки", ""
                ),
                "Партнер": orig.get("Партнер", ""),
                "Субдилер": orig.get("Субдилер", ""),
                "Субканал": orig.get("Субканал", ""),
                "Код Супервайзера": orig.get("Код Супервайзера", ""),
                "Код торгового представителя": orig.get("Код торгового представителя", ""),
                "Сколько раз посещаем в месяц": point.frequency,
            }
            for name, column in col_index.items():
                if name in values:
                    cell = ws.cell(row=write_row, column=column, value=values[name])
                    if has_sample:
                        _copy_style(cell, ws.cell(row=sample_row, column=column))
            num += 1
            write_row += 1

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
