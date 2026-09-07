#!/usr/bin/env bash
# Проверка локального OSRM: стартует osrm-routed, ждёт готовности,
# дёргает table + route, печатает результат и гасит сервер.
set -uo pipefail

cd "$(dirname "$0")/../.osrm" || exit 1

osrm-routed --algorithm mld --port 5000 moscow >/tmp/osrm-routed.log 2>&1 &
SRV=$!
trap 'kill "$SRV" 2>/dev/null' EXIT

# Ждём готовности (health endpoint).
for _ in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 2 "http://localhost:5000/route/v1/driving/37.62,55.75;37.63,55.76?overview=false" 2>/dev/null || true)
  [ "$code" = "200" ] && break
  sleep 1
done

echo "=== table ==="
curl -sS -m 20 "http://localhost:5000/table/v1/driving/37.62,55.75;37.63,55.76;37.61,55.74?annotations=distance" \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);print("code=",d.get("code"));print("distances=",d.get("distances"))'

echo "=== route (geometry) ==="
curl -sS -m 20 "http://localhost:5000/route/v1/driving/37.62,55.75;37.63,55.76?overview=full&geometries=geojson" \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);r=(d.get("routes") or [{}])[0];g=r.get("geometry") or {};print("code=",d.get("code"),"| coords=",len(g.get("coordinates") or []))'

echo "=== server log tail ==="
tail -5 /tmp/osrm-routed.log
