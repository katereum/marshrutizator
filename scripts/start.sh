#!/usr/bin/env bash
#
# Запуск приложения одной командой: локальный OSRM (если граф собран) + backend.
# При выходе из backend (Ctrl+C) OSRM гасится автоматически.
#
# Использование:
#   ./scripts/start.sh
#
# Переменные окружения:
#   OSRM_PORT    порт OSRM (по умолчанию 5000)
#   APP_PORT     порт backend (по умолчанию 8000)
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${OSRM_DATA_DIR:-$ROOT/.osrm}"
OSRM_PORT="${OSRM_PORT:-5000}"
APP_PORT="${APP_PORT:-8000}"
BASE="moscow"

HEALTH_URL="http://localhost:$OSRM_PORT/route/v1/driving/37.62,55.75;37.63,55.76?overview=false"

osrm_alive() {
  curl -s -o /dev/null -m 1 "$HEALTH_URL" 2>/dev/null
}

OSRM_PID=""
if [ -f "$DATA_DIR/$BASE.osrm.mldgr" ]; then
  if osrm_alive; then
    echo "[start] OSRM уже работает на :$OSRM_PORT"
  else
    echo "[start] Поднимаю локальный OSRM на :$OSRM_PORT"
    (cd "$DATA_DIR" && exec osrm-routed --algorithm mld --port "$OSRM_PORT" "$BASE") &
    OSRM_PID=$!
    for _ in $(seq 1 60); do
      osrm_alive && break
      sleep 1
    done
    if osrm_alive; then
      echo "[start] OSRM готов"
    else
      echo "[start] Внимание: OSRM не ответил — проверьте .osrm/ и лог osrm-routed"
    fi
  fi
else
  echo "[start] Граф OSRM не найден. Запустите: ./scripts/setup_osrm.sh build"
  echo "[start] Пока маршруты пойдут через резервные провайдеры из OSRM_BASE_URL."
fi

trap 'if [ -n "$OSRM_PID" ]; then kill "$OSRM_PID" 2>/dev/null || true; fi' EXIT

echo "[start] Backend: http://localhost:$APP_PORT"
exec "$ROOT/.venv/bin/uvicorn" backend.app:app --reload --port "$APP_PORT" --app-dir "$ROOT"
