# Согласование и переделка дней маршрута — план реализации

> **For Hermes:** использовать этот план по шагам; TDD (сначала падающий тест, потом код), коммит после каждого шага.

**Цель:** после построения маршрута пользователь видит список дней и может по каждому дню нажать «Согласовать» (зафиксировать) или «Переделать» (получить другой вариант этого дня), повторяя переделку до устраивающего результата. В конце скачивается именно тот маршрут, который он собрал руками.

**Архитектура:** маршрут становится редактируемым «черновиком» в JobStore. Добавляются endpoint'ы lock/unlock/regenerate. Ядро переделки — повторный вызов уже существующей `order_day` (чистая функция) с параметром варианта (seed), поэтому порядок точек внутри дня меняется без нарушения лимитов и цикличности. На втором этапе — обмен точками с пулом «Не запланировано» и соседними незафиксированными днями.

**Технологии:** FastAPI + vanilla JS (уже в проекте), in-memory JobStore, Python-оптимизатор.

---

## Текущее состояние (контекст)

- `/api/optimize` строит маршрут сразу целиком: `results: list[RouteResult]` (по одному на торгового представителя), `xlsx_files`, `geojson` — всё кладётся в `store.update(job_id, ...)`.
- `RouteResult.days: list[DaySchedule]`, каждый `DaySchedule(date, weekday, ordered_visits: list[str])`; `ordered_visits[i]` = `"point_id#slot"`.
- `/api/result/{id}` отдаёт только сводку (stats), без по-дневной разбивки.
- `/api/result/{id}/geojson` — карта; на ней уже есть фильтр по дням (выпадающий список дат).
- `/api/download/{id}` отдаёт заранее собранные `xlsx_files` — то есть скачивание НЕ зависит от будущих правок (нужно переделать на пересборку).
- `optimizer/routing.order_day(visit_ids, points_by_visit, home, dist, home_dist, end_home_dist, priority, priority_weight)` — чистая функция порядка точек внутри дня; `_nn_2opt` внутри неё сейчас стартует от `min(home_dist)` (ближайшая к старту точка).
- Тесты: `.venv/bin/python -m unittest discover -s tests -t .` (сейчас 118 зелёных).

---

## Предлагаемый подход

### Состояние «черновика» в JobStore

При завершении optimize дополнительно сохранять в job всё, что нужно для переделки и пересборки скачивания:

- `points_by_id: dict[str, Point]` — уже есть в переменной `points_by_id`.
- `incomplete_points: list[Point]` — для листа «Неопределённые точки».
- `template: bytes | None` — шаблон (или None).
- `home`, `home_by_weekday` — для пересборки геометрии карты.
- `locked: set[str]` — ключи вида `"{trade_rep_code}|{date.isoformat()}"` (изначально пусто).

Эти объекты уже живут в памяти во время `/api/optimize` — нужно только не выкидывать их, а сохранить в `store.update(...)`.

### Переделка дня

**Этап 1 (ядро, MVP) — перестановка порядка точек дня.**

Функция `order_day` получает параметр `variant: int`. Каждый `variant` даёт другой жадный старт (другую начальную точку для ближайшего соседа), а 2-opt дальше собирает компактный маршрут от этой точки. Итог: один и тот же набор точек дня, но другой порядок объезда. Нажатие «Переделать» = увеличить `variant` и пересчитать.

- Не трогает набор точек → лимиты и цикличность нарушены быть не могут.
- Зафиксированные (locked) дни не меняются вообще.
- Чисто и быстро (пересчёт одного дня — доли секунды).

**Этап 2 (расширение) — обмен точками.**

Помимо порядка, разрешить менять СОСТАВ дня: забрать точку из пула «Не запланировано» (или из соседнего незафиксированного дня) и/или выкинуть текущую точку в пул. Реализуется как «локальная переоптимизация» с зафиксированными днями в роли якорей. Это рискованнее (затрагивает цикличность и кучность) — делается после Этапа 1 и отдельно тестируется.

### Скачивание

`/api/download/{id}` переделать на пересборку из ТЕКУЩИХ `results` (а не из заранее собранных `xlsx_files`): вызвать `export_route(template_io, r, points_by_id, inc)` для текущих результатов. Тогда скачивание всегда отражает последнюю версию черновика.

---

## Шаги (по задачам)

### Задача 1. Сохранять входы черновика в JobStore

**Файлы:**
- Modify: `backend/app.py:468-480` (блок после `build_routes`).

**Шаг 1 — написать падающий тест** (см. Задачу 6 за точным местом; здесь просто фиксируем поведение): после optimize в job есть `points_by_id`, `locked == set()`.

**Шаг 2 — код:** в `store.update(job_id, status="COMPLETED", results=results, ...)` добавить:
```python
store.update(
    job_id,
    status="COMPLETED",
    results=results,
    xlsx_files=files,
    geojson=geojson,
    points_by_id=points_by_id,
    incomplete_points=incomplete_points,
    template=template,
    home=home,
    home_by_weekday=home_by_weekday,
    locked=set(),
)
```

**Шаг 3 — прогнать тесты**, ожидание: существующие 118 зелёные.

**Шаг 4 — коммит:** `git add backend/app.py && git commit -m "feat: сохранять входы черновика в JobStore"`.

---

### Задача 2. Endpoint по-дневной разбивки

**Файлы:**
- Modify: `backend/app.py` (новый route после `/api/result/{job_id}`).

**Код:** `GET /api/result/{job_id}/days` — вернуть для каждого результата список дней:
```python
@app.get("/api/result/{job_id}/days")
def result_days(job_id: str):
    job = store.get(job_id)
    if job is None or job.get("results") is None:
        raise HTTPException(status_code=404, detail="Результат не найден")
    locked = job.get("locked") or set()
    routes = []
    for r in job["results"]:
        days = []
        for ds in r.days:
            key = f"{r.trade_rep_code}|{ds.date.isoformat()}"
            days.append({
                "date": ds.date.isoformat(),
                "weekday": ds.weekday,
                "count": len(ds.ordered_visits),
                "locked": key in locked,
                "visits": ds.ordered_visits,
            })
        routes.append({"employee": r.trade_rep_code, "days": days, "total_km": round(r.stats.total_km, 1)})
    return {"routes": routes}
```
Примечание: `visits` — это `point_id#slot`; для красивого отображения фронтенд возьмёт адреса/коды из GeoJSON (или добавим позже `GET .../days?with_points=1`, отдающий код+адрес+метро из `points_by_id`).

**Тест:** в `tests/test_api.py` — создать фейковый job с одним RouteResult, дёрнуть `/api/result/{id}/days`, проверить структуру.

**Коммит:** `feat: endpoint по-дневной разбивки маршрута`.

---

### Задача 3. Endpoint'ы lock / unlock

**Файлы:**
- Create: `backend/schemas.py` — добавить `class DayAction(BaseModel): employee: str; date: date`.
- Modify: `backend/app.py` — `POST /api/result/{job_id}/lock` и `/unlock`.

**Код (lock; unlock симметрично):**
```python
@app.post("/api/result/{job_id}/lock")
def lock_day(job_id: str, body: DayAction):
    job = store.get(job_id)
    if job is None or job.get("results") is None:
        raise HTTPException(status_code=404, detail="Результат не найден")
    locked = job.get("locked") or set()
    locked.add(f"{body.employee}|{body.date.isoformat()}")
    store.update(job_id, locked=locked)
    return {"locked": sorted(locked)}
```

**Тест:** зафиксировать день → проверить, что `locked` содержит ключ и что `/days` отдаёт `locked: true`.

**Коммит:** `feat: зафиксировать/разблокировать день`.

---

### Задача 4. Параметр variant в order_day (ядро переделки)

**Файлы:**
- Modify: `optimizer/routing.py:13-56` — `order_day` и `_nn_2opt` получают `variant: int = 0`.

**Логика разнообразия (жадный старт):**
```python
# в _nn_2opt, вместо фиксированного start = min(remaining, key=home_dist):
if variant == 0:
    start = min(remaining, key=home_dist)          # ближайшая к старту (как сейчас)
elif variant == 1:
    start = max(remaining, key=home_dist)          # дальняя — обратный проход
else:
    # seeded-ротация: k-я ближайшая точка как старт (k = variant % len)
    ordered_by_home = sorted(remaining, key=home_dist)
    k = variant % len(ordered_by_home)
    start = ordered_by_home[k]
```
Дальше жадный ближайший сосед и 2-opt работают как раньше. `variant` меняется через `order_day(...)` и пробрасывается в `_nn_2opt`.

**Тест (TDD):** в `tests/test_routing.py` — для набора точек с известными координатами проверить, что `order_day(..., variant=0)` и `variant=1` дают РАЗНЫЕ порядки (и оба валидны: тот же набор id).

**Коммит:** `feat: варианты порядка точек внутри дня (seed-старт)`.

---

### Задача 5. Endpoint regenerate

**Файлы:**
- Modify: `backend/app.py` — `POST /api/result/{job_id}/regenerate`.
- Modify: `backend/schemas.py` — `class RegenerateRequest(BaseModel): employee: str; date: date; variant: int = 0`.

**Логика:**
1. Найти нужный `RouteResult` (по `trade_rep_code == body.employee`) и индекс дня (по `date`).
2. Если день зафиксирован (`key in locked`) — вернуть 409 «День зафиксирован — разблокируйте, чтобы переделать».
3. Пересобрать для этого дня: `points_by_visit` (из `points_by_id`), `home_dist`/`end_home_dist` (как в pipeline, с учётом `home` и `home_by_weekday`), `priority` (из `result.priority` + `focus`).
4. `new_order = order_day(ds.ordered_visits, points_by_visit, home=..., home_dist=..., end_home_dist=..., priority=..., priority_weight=..., variant=body.variant)`.
5. `ds.ordered_visits = new_order`; пересчитать `r.stats.total_km` (переиспользовать `_total_km` из pipeline) и `r.stats` при необходимости.
6. Пересобрать `geojson` из обновлённых `results` (`build_geojson` + `_build_route_geometries`), обновить `store.update(job_id, results=..., geojson=...)`.
7. Вернуть обновлённый день (date, count, visits, total_km).

**Тест:** на фейковом job — regenerate меняет `ordered_visits` дня; regenerate зафиксированного дня → 409; после regenerate `/days` отдаёт новый порядок.

**Коммит:** `feat: переделать день (новый порядок) без нарушения лимитов`.

---

### Задача 6. Скачивание пересобирается из текущего черновика

**Файлы:**
- Modify: `backend/app.py` — `/api/download/{job_id}`.

**Логика:** вместо `job["xlsx_files"]` — пересобрать:
```python
files = []
for r in job["results"]:
    inc = [p for p in job["incomplete_points"] if p.trade_rep_code == r.trade_rep_code]
    files.append((f"{r.trade_rep_code or 'route'}.xlsx", export_route(template_io, r, job["points_by_id"], inc)))
```
(`template_io = io.BytesIO(job["template"]) if job["template"] else None`.)

**Тест:** после regenerate скачанный файл содержит обновлённый порядок (сравнить `ordered_visits` в результате и в экспорте).

**Коммит:** `feat: скачивание отражает отредактированный маршрут`.

---

### Задача 7. Фронтенд: список дней + кнопки

**Файлы:**
- Modify: `frontend/index.html` — контейнер `<div id="days-panel">` под результатом.
- Modify: `frontend/styles.css` — стили списка (строки дней, состояния locked/unlocked).
- Modify: `frontend/app.js` — после `renderMap(job_id)` вызвать `renderDays(job_id)`.

**UI (по-русски):**
- Заголовок «Дни маршрута» + список строк: `«2 ноя, пн — 17 точек»` + кнопки `✓ Согласовать` и `⟳ Переделать`.
- Зафиксированный день: зелёная подсветка, `✓` меняется на `🔒 Согласовано` (клик разблокирует), кнопка `⟳` скрыта.
- «Переделать» вызывает regenerate с `variant = dayVariant[date]++` (счётчик по дню), затем обновляет строку, карту и километраж.
- После каждого действия обновлять `result-meta` (километраж) и кнопку скачивания (href без изменений — скачивание теперь динамическое).

**Тест:** `node --check frontend/app.js` проходит.

**Коммит:** `feat: интерфейс согласования/переделки дней`.

---

### Задача 8 (расширение, после MVP). Обмен точками с пулом/соседями

**Файлы:**
- Create: `optimizer/regenerate.py` — `swap_day(result, day_idx, locked, points_by_id, caps, home, ...)`.

**Логика (эскиз):**
1. Собрать кандидатов: точки текущего дня + точки `r.unplanned` + точки соседних незафиксированных дней.
2. Жадный локальный обмен: заменить точки дня на кандидатов, сохраняя `len == cap`, не трогая зафиксированные дни, не нарушая `_min_gap` для повторов.
3. Пересобрать порядок через `order_day`.
4. Точки, ушедшие из дня, — в `r.unplanned`; точки, пришедшие, — удаляются из старого дня/пула.

**Тест:** после swap лимит не превышен, зафиксированные дни не тронуты, состав дня изменился.

**Коммит:** `feat: обмен точками при переделке дня`.

---

## Файлы, которые изменятся

- `backend/app.py` — сохранение входов, 4 новых endpoint'а, динамическое скачивание.
- `backend/schemas.py` — `DayAction`, `RegenerateRequest`.
- `optimizer/routing.py` — `variant` в `order_day`/`_nn_2opt`.
- `optimizer/regenerate.py` — (Этап 2) обмен точками.
- `frontend/index.html`, `frontend/styles.css`, `frontend/app.js` — список дней и кнопки.
- `tests/test_api.py`, `tests/test_routing.py` (+ возможно `tests/test_regenerate.py`) — тесты.

## Тесты / проверка

- `.venv/bin/python -m unittest discover -s tests -t .` — все зелёные на каждом шаге.
- `node --check frontend/app.js`.
- Ручная проверка на `0001ABC (30).xlsx`: построить → согласовать день → переделать соседний (порядок меняется, согласованный не трогается) → скачать и убедиться, что в файле новый порядок.

## Риски и открытые вопросы

1. **Что именно значит «другой вариант»?** Этап 1 меняет только ПОРЯДОК (тот же набор точек). Если пользователь хочет менять и СОСТАВ (другие точки) — это Этап 2, он дороже и рискованнее по цикличности/кучности. Уточнить у пользователя, достаточен ли порядок на первом шаге.
2. **Несколько ТП.** Файл может содержать несколько торговых представителей; ключ блокировки `(employee, date)` это учитывает, но UI надо решить — показывать дни по одному ТП с переключателем или все подряд. Для MVP — первый ТП (или переключатель, если их несколько).
3. **Пересборка километража.** `total_km` пересчитывается через `_total_km`; при недоступной дорожной матрице — haversine. Держать цифру честной (пересчитывать после каждой правки).
4. **Пул «Не запланировано».** На Этапе 1 пул не трогается; на Этапе 2 точки можно «доставать» из пула. Учесть, что пул тоже должен быть виден в UI (иначе пользователь не поймёт, откуда взялась точка).
5. **Состояние в памяти.** JobStore in-memory — переделка живёт до перезапуска сервера. Для VPS это ок (одна сессия upload→optimize→edit→download), но после рестарта черновик пропадает.
