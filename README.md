# Маршрутизатор 3.0

Веб-приложение: загрузи базу планирования и шаблон маршрутного листа — получи
оптимальный месячный маршрут по торговым точкам (учёт цикличности, географии и
равномерной нагрузки). Ядро — алгоритм оптимизации; Excel — вход и выход.

## Быстрый старт

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # вписать YANDEX_GEOCODER_API_KEY и др.
```

## Команды

| Команда | Назначение |
|---|---|
| `.venv/bin/python -m unittest discover -s tests -t .` | запуск тестов |
| `.venv/bin/uvicorn backend.app:app --reload` | dev-сервер |
| `PYTHONPATH=. .venv/bin/python sample_data/make_samples.py` | демо-файлы Excel |

## Структура

- `docs/` — архитектура, спецификация, алгоритм, план
- `optimizer/` — ядро (Stage A/B, кластеризация, валидация) — без веб-зависимостей
- `parser/` — чтение/валидация Excel-базы планирования
- `geocoder/` — интерфейс + Яндекс/offline-провайдеры
- `exporter/` — заполнение шаблона + GeoJSON
- `backend/` — FastAPI API
- `tests/`, `sample_data/`

## API

- `POST /api/upload/planning`
- `POST /api/upload/route-template`
- `POST /api/optimize`
- `GET /api/result/{job_id}`
- `GET /api/result/{job_id}/geojson`
- `GET /api/download/{job_id}`

Детали — `docs/architecture.md`, `docs/specification.md`.
