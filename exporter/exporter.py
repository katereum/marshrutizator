"""Заполнение шаблона маршрутного листа или генерация листа с нуля (раздел 24 ТЗ, R6).

Выгрузка строится ДИНАМИЧЕСКИ из колонок базы планирования: какие колонки есть
в базе (и в каком порядке) — те и попадают в маршрутный лист, плюс три
генерируемые в начале («№ п/п», «Дата визита», «День недели») и «Приоритет» в
конце. «Цикличность» из базы переименовывается в «Сколько раз посещаем в месяц».
"""
from __future__ import annotations

import io
from copy import copy
from typing import BinaryIO

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from optimizer.models import Point, RouteResult

WEEKDAYS_RU = [
    "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье",
]

FOCUS_LABELS = {
    "economy": "Экономия бензина",
    "fix_problems": "Сначала проблемные",
    "top_performers": "Сначала лучшие",
}

# Генерируемые колонки, которых нет в базе планирования.
GENERATED_PREFIX = ["№ п/п", "Дата визита", "День недели"]
GENERATED_SUFFIX = ["Приоритет"]


def _raw(point: Point, key: str):
    """Сырое значение из базы (сохраняет «%»), пустое -> прочерк. Без регистра."""
    o = point.original or {}
    for k, v in o.items():
        if str(k).strip().lower() == key.lower():
            if v is None:
                return "—"
            s = str(v).strip()
            return s if s != "" else "—"
    return "—"


def _result_display(point: Point) -> str:
    """Результат — как в исходной базе, без изменений.

    Вводные данные не преобразуем: процент уже восстановлен парсером по формату
    ячейки («0%» → «90%»), поэтому здесь просто возвращаем исходное значение.
    """
    return _raw(point, "Результат")


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


def _add_summary_sheet(wb, result: RouteResult, points_by_id: dict[str, Point]) -> None:
    """Добавляет лист «Сводка»: акцент, учёт Оценки/Результата и приоритеты."""
    ws = wb.create_sheet("Сводка")

    # Точки именно этого маршрута (в порядке появления), без дублей.
    ids: list[str] = []
    for day in result.days:
        for vid in day.ordered_visits:
            pid = vid.rsplit("#", 1)[0]
            if pid not in ids:
                ids.append(pid)
    points = [points_by_id[pid] for pid in ids if pid in points_by_id]

    n_score = sum(1 for p in points if p.score is not None)
    n_result = sum(1 for p in points if p.result is not None)

    ws["A1"] = "Акцент маршрута"
    ws["B1"] = FOCUS_LABELS.get(result.focus, result.focus)
    ws["A2"] = "Точек с Оценкой"
    ws["B2"] = f"{n_score} из {len(points)}"
    ws["A3"] = "Точек с Результатом"
    ws["B3"] = f"{n_result} из {len(points)}"

    # Предупреждения (если есть — например, откат на прямые расстояния).
    header_row = 5
    if result.warnings:
        ws.cell(row=header_row, column=1, value="Предупреждения")
        r = header_row
        for w in result.warnings:
            r += 1
            ws.cell(row=r, column=1, value="• " + w)
        header_row = r + 2

    ws.cell(row=header_row, column=1, value="Код")
    ws.cell(row=header_row, column=2, value="Оценка")
    ws.cell(row=header_row, column=3, value="Результат")
    ws.cell(row=header_row, column=4, value="Приоритет")

    ordered = sorted(points, key=lambda p: result.priority.get(p.id, 0.0), reverse=True)
    for i, p in enumerate(ordered):
        row = header_row + 1 + i
        ws.cell(row=row, column=1, value=p.id)
        ws.cell(row=row, column=2, value=_raw(p, "Оценка"))
        ws.cell(row=row, column=3, value=_result_display(p))
        ws.cell(row=row, column=4, value=round(result.priority.get(p.id, 0.0), 2))


def _output_columns(points) -> list[str]:
    """Колонки готового листа: генерируемые + колонки базы (в порядке базы) + «Приоритет».

    «Цикличность» из базы становится «Сколько раз посещаем в месяц». «Оценка» и
    «Результат» добавляются только если их нет в базе (иначе они уже среди колонок
    базы на своём месте). Пустые заголовки пропускаются.
    """
    base: list[str] = []
    for p in points:
        if p.original:
            base = list(p.original.keys())
            break

    cols: list[str] = list(GENERATED_PREFIX)
    for c in base:
        name = str(c).strip()
        if not name:
            continue
        if name.lower() == "цикличность":
            cols.append("Сколько раз посещаем в месяц")
        else:
            cols.append(name)

    have = {c.lower() for c in cols}
    for extra in ("Оценка", "Результат", *GENERATED_SUFFIX):
        if extra.lower() not in have:
            cols.append(extra)
    return cols


def _route_value(point: Point, day, num: int, result: RouteResult, name: str):
    """Значение для колонки выгрузки: сгенерированное или из базы (без учёта регистра)."""
    n = str(name).lower()
    if n == "№ п/п":
        return num
    if n == "дата визита":
        return day.date
    if n == "день недели":
        return WEEKDAYS_RU[day.weekday]
    if n == "сколько раз посещаем в месяц":
        return point.frequency
    if n == "оценка":
        return _raw(point, "Оценка")
    if n == "результат":
        return _result_display(point)
    if n == "приоритет":
        return "" if result.priority.get(point.id) is None else round(result.priority[point.id], 2)
    # Остальные колонки — как есть из базы (без учёта регистра).
    for k, v in (point.original or {}).items():
        if str(k).strip().lower() == n:
            return "" if v is None else v
    return point.id if n == "единый код" else ""


def _fill_route_rows(ws, col_index: dict, write_row: int, sample_row, result: RouteResult, points_by_id: dict) -> None:
    """Заполняет строки маршрута по колонкам col_index (имя -> индекс), в порядке колонок."""
    for day in result.days:
        num = 1  # нумерация «№ п/п» начинается заново каждый день
        for vid in day.ordered_visits:
            point = points_by_id.get(vid.rsplit("#", 1)[0])
            if point is None:
                continue
            for name, column in col_index.items():
                cell = ws.cell(row=write_row, column=column, value=_route_value(point, day, num, result, name))
                if sample_row is not None:
                    _copy_style(cell, ws.cell(row=sample_row, column=column))
                if str(name).lower() == "дата визита":
                    # Настоящая дата, всегда в формате ДД.ММ.ГГГГ (1 июля = 01.07).
                    cell.number_format = "DD.MM.YYYY"
            num += 1
            write_row += 1


def _add_incomplete_sheet(wb, incomplete_points) -> None:
    """Лист «Неопределенные точки»: точки без полного адреса (не маршрутизированы)."""
    if not incomplete_points:
        return
    ws = wb.create_sheet("Неопределенные точки")
    cols: list[str] = []
    for p in incomplete_points:
        if p.original:
            cols = [str(c).strip() for c in p.original.keys() if str(c).strip()]
            break
    header_row = 1
    for c, name in enumerate(cols, start=1):
        cell = ws.cell(row=header_row, column=c, value=name)
        cell.font = Font(bold=True)
    for i, p in enumerate(incomplete_points):
        row = header_row + 1 + i
        orig = p.original or {}
        for c, name in enumerate(cols, start=1):
            value = ""
            for k, v in orig.items():
                if str(k).strip().lower() == name.lower():
                    value = "" if v is None else v
                    break
            ws.cell(row=row, column=c, value=value)


def _export_route_from_scratch(result: RouteResult, points_by_id: dict[str, Point], incomplete_points=None) -> bytes:
    """Создаёт маршрутный лист с нуля: колонки — из базы планирования, а не фиксированные."""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Маршрут"
    header_row = 1
    col_index = {}
    for c, name in enumerate(_output_columns(points_by_id.values()), start=1):
        cell = ws.cell(row=header_row, column=c, value=name)
        cell.font = Font(bold=True)
        col_index[name] = c
    _fill_route_rows(ws, col_index, header_row + 1, None, result, points_by_id)
    _add_summary_sheet(wb, result, points_by_id)
    _add_incomplete_sheet(wb, incomplete_points)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def export_route(template: BinaryIO | None, result: RouteResult, points_by_id: dict[str, Point], incomplete_points=None) -> bytes:
    """Заполняет шаблон (или создаёт лист с нуля) и возвращает .xlsx в виде bytes."""
    if template is None:
        return _export_route_from_scratch(result, points_by_id, incomplete_points)

    wb = load_workbook(template)
    ws = wb.active

    found = _find_header(ws)
    if found is None:
        raise ValueError("В шаблоне не найдена строка заголовка (Единый код + Дата визита)")
    header_row, col_index = found

    # Автодобавляем опциональные колонки, если их нет в шаблоне (без регистра):
    # так Оценка/Результат из базы всегда попадают в выгрузку без правки шаблона.
    next_col = ws.max_column + 1
    existing = {str(k).strip().lower() for k in col_index}
    for name in ("Оценка", "Результат", "Приоритет"):
        if name.lower() not in existing:
            col_index[name] = next_col
            ws.cell(row=header_row, column=next_col, value=name)
            next_col += 1

    sample_row = header_row + 1
    has_sample = ws.cell(row=sample_row, column=col_index["Единый код"]).value not in (None, "")

    write_row = sample_row if has_sample else header_row + 1
    _fill_route_rows(ws, col_index, write_row, sample_row if has_sample else None, result, points_by_id)

    _add_summary_sheet(wb, result, points_by_id)
    _add_incomplete_sheet(wb, incomplete_points)

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
