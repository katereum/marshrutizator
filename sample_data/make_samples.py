"""Генерация демо-файлов sample_data/ (база планирования + шаблон)."""
from __future__ import annotations

from openpyxl import Workbook

from parser.columns import (
    OPTIONAL_PLANNING_COLUMNS,
    OPTIONAL_RESULT_COLUMNS,
    PLANNING_COLUMNS,
    RESULT_COLUMNS,
)

# код, старый, статус, нас.пункт, тип улицы, улица, дом, строение, корпус, метро,
# доп, партнёр, субдилер, субканал, супервайзер, ТП, цикличность, оценка, результат
PLANNING_ROWS = [
    ["A001", "1001", "Актив", "Москва", "ул.", "Ленина", "1", "", "", "Тверская", "", "П1", "С1", "К1", "SUP1", "TP1", 1, 5, 120],
    ["A002", "1002", "Актив", "Москва", "ул.", "Ленина", "2", "", "", "Тверская", "", "П1", "С1", "К1", "SUP1", "TP1", 2, 4, 80],
    ["A003", "1003", "Актив", "Москва", "пр.", "Мира", "10", "1", "", "Рижская", "", "П2", "С2", "К2", "SUP1", "TP1", 3, 2, 40],
    ["A004", "1004", "Актив", "Москва", "ул.", "Тверская", "5", "", "", "Тверская", "", "П2", "С2", "К2", "SUP1", "TP1", 4, "", 90],
    ["A005", "1005", "Актив", "Москва", "ул.", "Арбат", "7", "2", "1", "Арбатская", "", "П3", "С3", "К3", "SUP2", "TP2", 1, 3, 200],
    ["A006", "1006", "Актив", "Москва", "ул.", "Арбат", "9", "", "", "Арбатская", "", "П3", "С3", "К3", "SUP2", "TP2", 2, 1, 10],
    ["A007", "1007", "Актив", "Мытищи", "ул.", "Мира", "3", "", "", "", "", "П4", "С4", "К4", "SUP2", "TP2", 1, "", 0],
    ["A008", "1008", "Актив", "Мытищи", "ул.", "Мира", "5", "", "", "", "", "П4", "С4", "К4", "SUP2", "TP2", 1, 4, 60],
    ["A009", "1009", "Актив", "Химки", "ул.", "Ленина", "12", "", "", "", "", "П5", "С5", "К5", "SUP1", "TP1", 2, 2, 30],
    ["A010", "1010", "Актив", "Химки", "ул.", "Ленина", "14", "", "", "", "", "П5", "С5", "К5", "SUP1", "TP1", 3, 5, 150],
]


def make_planning(path: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(PLANNING_COLUMNS + OPTIONAL_PLANNING_COLUMNS)
    for row in PLANNING_ROWS:
        ws.append(row)
    wb.save(path)


def make_template(path: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(RESULT_COLUMNS + OPTIONAL_RESULT_COLUMNS)
    # Строка-образец форматирования (будет перезаписана данными).
    ws.append(["" for _ in RESULT_COLUMNS + OPTIONAL_RESULT_COLUMNS])
    wb.save(path)


if __name__ == "__main__":
    make_planning("sample_data/planning.xlsx")
    make_template("sample_data/route_template.xlsx")
    print("sample_data сгенерированы")
