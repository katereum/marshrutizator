# Архитектура «Маршрутизатор 3.0»

> Документ Этапа 2. Описывает компоненты, связи, поток данных, модель данных,
> API и технологический стек. Решения R1–R7 согласованы (§10); архитектура
> готова к реализации (Этап 4+).

## 1. Принципы

- **Ядро — алгоритм, не интерфейс.** Оптимизатор — отдельный пакет без
  зависимостей от веб-слоя, тестируемый в изоляции (требование Этапа 4).
- **Две независимые задачи** (раздел 9 ТЗ): распределение точек по дням
  (Stage A) и порядок внутри дня (Stage B). Каждая решается отдельным
  компонентом и заменяется независимо.
- **Несмешиваемые слои данных** (раздел 33): исходные → нормализованные →
  географические → визиты → расписание → маршрут.
- **Заменяемость:** геокодер, метрика стоимости, кластеризатор и солвер
  порядка за интерфейсами (Protocol), а не зашиты в коде.

## 2. Общая схема

```
Frontend (React SPA)
   │  multipart upload / JSON
   ▼
Backend API (FastAPI)
   │
   ├─ Upload / Job controller ──► JobStore (in-memory + filesystem)
   │
   └─ Optimization pipeline (синхронно или воркером):
        FileValidator ──► ExcelParser ──► DataNormalizer
                                              │
                                              ▼
                                        Geocoder (pluggable)
                                              │
                                              ▼
                                     Optimizer (Stage A)
                                              │
                                              ▼
                                     ScheduleBuilder (Stage B)
                                              │
                                              ▼
                                        ResultValidator
                                              │
                                              ▼
                                        ExcelExporter ──► RouteResult (.xlsx)
```

## 3. Компоненты и ответственность

| Компонент | Ответственность | Вход → Выход |
|---|---|---|
| `FileValidator` | Проверка расширения, наличия файла, обязательных колонок, типов | файлы → `{ok \| ValidationError[]}` |
| `ExcelParser` | Чтение `.xlsx`, извлечение строк в сырые записи | файл → `list[RawPoint]` |
| `DataNormalizer` | Приведение адресов к единому виду, проверка уникальности `Единый код`, нормализация цикличности | `RawPoint` → `NormalizedPoint` |
| `Geocoder` (protocol) | `address → (lat, lon)` | адрес → координаты |
| `Clusterer` | Разбиение точек на географические кластеры | `Point[]` → `cluster_id[]` |
| `Optimizer` (Stage A) | Распределение визитов по рабочим дням (цикличность + баланс + география) | `Visit[]`, дни → `DayAssignment[]` |
| `ScheduleBuilder` (Stage B) | Порядок точек внутри дня (TSP-эвристика) | `DayAssignment[]` → `DaySchedule[]` |
| `ResultValidator` | Автопроверка инвариантов результата (раздел 23) | `RouteResult` → `{ok \| Violation[]}` |
| `ExcelExporter` | Заполнение шаблона маршрутного листа | `RouteResult` + шаблон → `.xlsx` |
| `JobStore` | Состояние задач, хранение файлов и результатов | — |

## 4. Технологический стек

| Слой | Выбор | Обоснование |
|---|---|---|
| Язык | Python 3.12 | Лучшая экосистема для Excel (`openpyxl`), гео (`geopy`, haversine), кластеризации (`scikit-learn`), оптимизации (`scipy`, в перспективе `ortools`). Ядро — вычисления. |
| Backend | FastAPI + Pydantic v2 | Типизация на границе, авто-OpenAPI, асинхронная загрузка файлов, простая интеграция с Python-ядром. |
| Frontend | React 18 + TypeScript + Vite | Типизированный минимальный SPA; стилизация — CSS/Tailwind под заданный градиент. |
| Excel | `openpyxl` | Чтение и запись `.xlsx` с сохранением шаблона/стилей заголовка (заполняем существующий лист). |
| Кластеризация | DBSCAN (sklearn) с метрикой Haversine | Не требует заданного числа кластеров, устойчив к выбросам. Fallback — строковая кластеризация по нормализованному адресу. |
| Порядок внутри дня | Greedy nearest-neighbor + 2-opt | Достаточно для MVP; за интерфейсом `RouteSolver`, заменяемо на OR-Tools. |
| Геокодер | Интерфейс `Geocoder`; провайдеры: `OfflineGeocoder` (fallback), `NominatimGeocoder`, `YandexGeocoder`/`DaDataGeocoder` (по env) | Требование раздела 14: замена геокодера без переписывания приложения. |
| Хранение | In-memory `JobStore` + файлы на диске (tmp) | MVP без БД (раздел 37). Интерфейс позволяет позже подставить SQLite/Redis. |
| Тесты | pytest + hypothesis | Инварианты алгоритма (раздел 38). |

Альтернативы и причины отказа (ADR-кратко):
- **Node/TypeScript full-stack** — откл.: экосистема Excel/гео/оптимизации слабее, ядро важнее единого языка.
- **k-means вместо DBSCAN** — откл.: требует число кластеров, чувствителен к форме и выбросам.
- **OR-Tools сразу** — откл. для MVP: усложняет деплой; интерфейс сохранён для замены.
- **pandas** — опционален; для MVP достаточно `openpyxl` (меньше зависимостей).

## 5. Модель данных

Разделение слоёв (раздел 33 ТЗ). Каждый слой — неизменяемый value-объект.

База разбивается по `Код торгового представителя` на сущность `Employee`
(один сотрудник = один независимый маршрутный лист, R2). Один код — один
сотрудник; несколько кодов — маршрут строится для каждого.

```python
# Слой 1 — OriginalData (данные из Excel, без изменений)
RawPoint = dict  # все 17 колонок базы планирования как есть

# Слой 2 — NormalizedData
class Point:
    id: str                    # Единый код (уникальный ключ)
    old_code: str
    status: str
    locality: str
    street: str                # нормализованная улица
    house: str
    building: str | None
    block: str | None
    metro: str | None
    extra_desc: str | None
    partner: str
    subdealer: str
    subchannel: str
    supervisor_code: str
    trade_rep_code: str
    frequency: int             # цикличность, 1..N
    original: RawPoint         # неизменный исходник для экспорта
    normalized_address: str

# Слой 3 — GeoData
class Geopoint(Point):
    latitude: float | None
    longitude: float | None
    cluster_id: int | None

# Слой 4 — VisitData (размножение по цикличности)
class Visit:
    visit_id: str              # f"{point_id}#{slot}"
    point_id: str
    slot_index: int            # 0..frequency-1, для равномерной раскладки
    cluster_id: int | None

# Слой 5 — ScheduleData (распределение по дням)
class DayAssignment:
    date: date
    weekday: int
    visits: list[str]          # visit_id

# Слой 6 — RouteData (порядок внутри дня)
class DaySchedule:
    date: date
    weekday: int
    ordered_visits: list[str]  # в порядке посещения
    distance_estimate: float | None

class RouteResult:
    job_id: str
    period_start: date
    period_end: date
    days: list[DaySchedule]
    stats: RouteStats          # счётчики, нагрузка по дням, score
    warnings: list[str]

class RouteStats:
    total_points: int
    total_visits: int
    per_day_load: list[int]
    score: float               # раздел 35 ТЗ
    violations: list[str]      # пусто, если валидно
```

## 6. Поток данных

```
1. Загрузка      planning.xlsx + template.xlsx
2. Валидация     FileValidator → понятные ошибки пользователю
3. Парсинг       ExcelParser → RawPoint[]
4. Нормализация  DataNormalizer → Point[] (уникальность кода, адрес, цикличность)
5. Геокодирование Geocoder → Geopoint[] (или cluster по адресу без координат)
6. Кластеризация Clusterer → cluster_id
7. Размножение   Point → Visit[] (frequency копий)
8. Stage A       Optimizer → DayAssignment[] (баланс + цикличность + география)
9. Stage B       ScheduleBuilder → DaySchedule[] (порядок внутри дня)
10. Проверка     ResultValidator → ok или повторная оптимизация
11. Экспорт      ExcelExporter → заполненный шаблон
12. Скачивание   GET /api/download/{job_id}
```

Конвейер выполняется независимо для каждого `Employee` (R2); карта (R7)
строится из `RouteResult.to_geojson()`.

## 7. API

REST. Один формат ошибок на все эндпоинты:

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Отсутствует обязательный столбец: Цикличность", "details": { "column": "Цикличность" } } }
```

Коды ошибок: `FILE_ERROR`, `VALIDATION_ERROR`, `NOT_FOUND`, `OPTIMIZATION_ERROR`, `CONFLICT`.

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| POST | `/api/upload/planning` | multipart `file` | `201 {file_id, filename, row_count, columns}` |
| POST | `/api/upload/route-template` | multipart `file` | `201 {file_id, filename}` |
| POST | `/api/optimize` | JSON (ниже) | `202 {job_id}` |
| GET | `/api/result/{job_id}` | — | `{job_id, status, stats, validation_errors?}` |
| GET | `/api/result/{job_id}/geojson` | — | `200 GeoJSON` (маршруты по дням, R7) |
| GET | `/api/download/{job_id}` | — | `200 .xlsx` (или `404`) |

```jsonc
// POST /api/optimize
{
  "planning_file_id": "uuid",
  "route_template_file_id": "uuid",
  "period_start": "2026-09-01",
  "period_end": "2026-09-30",
  "min_points_per_day": 15,       // необязательно, дефолт 15
  "max_points_per_day": 25,       // необязательно, дефолт 25
  "work_on_weekends": false       // необязательно, дефолт false
}
```

Жизненный цикл задачи (`status`): `PENDING → VALIDATING → PARSING →
NORMALIZING → GEOCODING → OPTIMIZING → VERIFYING → EXPORTING → COMPLETED | FAILED`.
Frontend показывает состояния по этому же списку (раздел 28 ТЗ).

## 8. Структура проекта

```
marshrutizator-3.0/
├── docs/            # plan.md, architecture.md, specification.md, algorithm.md
├── backend/         # FastAPI: роуты, контроллеры задач, DI
├── optimizer/       # ядро: Stage A (assignment) + Stage B (routing) — без веб-зависимостей
├── parser/          # ExcelParser, FileValidator
├── normalizer/      # DataNormalizer
├── geocoder/        # Geocoder protocol + провайдеры
├── clusterer/       # DBSCAN / address-based
├── exporter/        # ExcelExporter
├── validator/       # ResultValidator
├── templates/       # эталонный шаблон маршрутного листа
├── tests/           # pytest + hypothesis
├── sample-data/     # тестовые Excel (Тест №1–8 из раздела 38)
├── .env.example
└── README.md
```

`optimizer/` импортируется `backend/`-ом как библиотека и отдельно прогоняется
тестами — это удовлетворяет требованию Этапа 4 «ядро отдельно от интерфейса».

## 9. Точки расширения (маппинг на будущие функции, раздел 42)

| Будущая функция | Точка расширения |
|---|---|
| Стартовая/конечная точка | вход Stage B (`start_id`, `end_id`) |
| Мин/макс точек, рабочее время, время на точку | уже параметры `Optimizer`; время → `RouteCost` |
| Пробки, реальное время в пути, виды транспорта | интерфейс `RouteCost` / `TravelTimeProvider` |
| Карты, визуализация | `RouteResult.to_geojson()` + Leaflet-карта frontend (первый релиз, R7) |
| Несколько сотрудников/территорий, закрепление точек | сущность `Employee` (разбиение по `trade_rep_code`/территории, R2) |
| Индивидуальные графики, праздники | `CalendarProvider` (сейчас `WeekdayCalendar`) |
| Ручная корректировка, повторная оптимизация | `ScheduleData` становится редактируемой + блокировки назначений |
| Настраиваемые веса факторов | `RouteScore` с весами (раздел 34–35) |

## 10. Согласованные решения (R) и прочие допущения (A)

**Решения (ответы на O1–O7):**
- **R1 (O1).** Геокодер — Яндекс: `GEOCODER_PROVIDER=yandex`, ключ в `.env`.
  Провайдер заменяем через интерфейс `Geocoder`; fallback без сети —
  кластеризация по адресу.
- **R2 (O2, O7).** Поддерживаются оба режима: база разбивается по
  `Код торгового представителя`. Один код → один маршрут; несколько кодов →
  маршрут на каждого сотрудника. Выбор сотрудника на загрузке не нужен.
- **R3 (O3).** `min/max точек в день` — мягкое целевое; при конфликте с
  цикличностью приоритет у цикличности.
- **R4 (O4).** Работа в выходные запрещена (Сб/Вс нерабочие).
- **R5 (O5).** При `цикличность > рабочих дней` визиты укладываются «сколько
  влезает» с предупреждением пользователю.
- **R6 (O6).** Экспорт сохраняет и стили/форматирование шаблона, и значения.
- **R7 (новая фича).** По итогу показывать на карте маршруты по дням:
  `GET /api/result/{job_id}/geojson` + Leaflet-карта в frontend.

**Прочие допущения (остаются в силе):**
- **A1.** Стек — Python/FastAPI + React/TS.
- **A5.** Период — обязательный вход; дефолт в UI — следующий календарный месяц.
- **A8.** `Единый код` уникален; дубликаты → ошибка валидации.
- **A9.** Исходные данные не изменяются в выходном Excel (нормализация — только внутри).
- **A10.** Хранение — in-memory + файлы на диске, без БД.
- **A11.** Кластеризация — DBSCAN (Haversine); fallback — по адресу.
- **A12.** Порядок внутри дня — greedy NN + 2-opt.

Архитектура согласована — можно переходить к Этапу 4.
