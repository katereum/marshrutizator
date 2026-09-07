#!/usr/bin/env bash
#
# Настройка локального OSRM для «Маршрутизатора 3.0».
#
# Поднимает self-hosted сервер дорожной маршрутизации (матрица + геометрия),
# чтобы не зависеть от Яндекс.Маршрутизации и публичного демо OSRM.
#
# Использование:
#   ./scripts/setup_osrm.sh install   # установить osrm-backend и osmium (brew)
#   ./scripts/setup_osrm.sh build     # скачать данные, вырезать Москву, построить граф
#   ./scripts/setup_osrm.sh start     # запустить osrm-routed на порту 5000
#
# Переменные окружения (необязательно):
#   OSRM_DATA_DIR   каталог данных (по умолчанию .osrm в корне проекта)
#   OSRM_PORT       порт сервера (по умолчанию 5000)
#   MOSCOW_BBOX     ббокс вырезки (по умолчанию Москва + область)
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${OSRM_DATA_DIR:-$ROOT/.osrm}"
PORT="${OSRM_PORT:-5000}"
CF_URL="https://download.geofabrik.de/russia/central-fed-district-latest.osm.pbf"
CF_PBF="$DATA_DIR/central-fed-district-latest.osm.pbf"
MOSCOW_PBF="$DATA_DIR/moscow.osm.pbf"
BASE="moscow"          # базовое имя графа (файлы: moscow.osrm.*)
BBOX="${MOSCOW_BBOX:-35.5,54.8,39.5,56.5}"

log() { printf '\033[1;35m[osrm]\033[0m %s\n' "$*"; }

require_osrm() {
  if ! command -v osrm-routed >/dev/null 2>&1; then
    log "osrm-backend не найден. Запустите: $0 install"
    exit 1
  fi
}

find_profile() {
  local prefix
  prefix="$(brew --prefix 2>/dev/null || echo /usr/local)"
  find "$prefix" -name car.lua -path '*osrm*' 2>/dev/null | head -1
}

cmd_install() {
  brew install osrm-backend osmium-tool
}

cmd_download() {
  mkdir -p "$DATA_DIR"
  if [ ! -f "$MOSCOW_PBF" ]; then
    if [ ! -f "$CF_PBF" ]; then
      log "Скачиваю ЦФО (~835 МБ, с докачкой)…"
      curl -L --fail --retry 5 --retry-all-errors -C - -o "$CF_PBF" "$CF_URL"
    else
      log "Экстракт ЦФО уже есть: $CF_PBF"
    fi
    log "Вырезаю Москву + область (bbox $BBOX)…"
    osmium extract -b "$BBOX" -s smart -o "$MOSCOW_PBF" "$CF_PBF"
  else
    log "Экстракт Москвы уже есть: $MOSCOW_PBF"
  fi
}

cmd_build() {
  require_osrm
  cmd_download

  local profile
  profile="$(find_profile)"
  if [ -z "$profile" ] || [ ! -f "$profile" ]; then
    log "ОШИБКА: не найден car.lua. Укажите OSRM_PROFILE=<путь> и повторите."
    exit 1
  fi
  log "Профиль: $profile"

  # OSRM-утилиты работают с базовым именем графа относительно каталога данных.
  cd "$DATA_DIR"
  if [ -f "$BASE.osrm.mldgr" ]; then
    log "Граф уже построен: $DATA_DIR/$BASE"
  else
    [ -f "$BASE.osrm.ebg" ] || { log "osrm-extract …"; osrm-extract -p "$profile" "$(basename "$MOSCOW_PBF")"; }
    [ -f "$BASE.osrm.partition" ] || { log "osrm-partition …"; osrm-partition "$BASE"; }
    log "osrm-customize …"
    osrm-customize "$BASE"
  fi

  log "Граф готов: $DATA_DIR/$BASE"
  log "Запустите: $0 start  (и укажите OSRM_BASE_URL=http://localhost:$PORT)"
}

cmd_start() {
  require_osrm
  cd "$DATA_DIR"
  if [ ! -f "$BASE.osrm.mldgr" ]; then
    log "Граф не найден. Запустите: $0 build"
    exit 1
  fi
  log "Запускаю osrm-routed на http://localhost:$PORT (Ctrl+C — остановить)"
  exec osrm-routed --algorithm mld --port "$PORT" "$BASE"
}

cmd="${1:-}"
case "$cmd" in
  install)  cmd_install ;;
  download) cmd_download ;;
  build)    cmd_build ;;
  start)    cmd_start ;;
  *)
    echo "Использование: $0 {install|download|build|start}"
    echo "  install  — установить osrm-backend и osmium-tool (brew)"
    echo "  download — скачать данные и вырезать Москву"
    echo "  build    — download + построить граф"
    echo "  start    — запустить сервер на порту $PORT"
    exit 2
    ;;
esac
