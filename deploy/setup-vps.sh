#!/usr/bin/env bash
# Развёртывание «Маршрутизатора» на чистом VPS (Ubuntu/Debian).
# Запуск: sudo bash setup-vps.sh  (сервер должен иметь доступ в интернет)
set -euo pipefail

APP_DIR="/opt/marshrutizator"
REPO="https://github.com/katereum/marshrutizator.git"
# Вставь сюда ключ Яндекс.Геокодера (или оставь пустым и впиши позже в systemd).
YANDEX_KEY="${YANDEX_GEOCODER_API_KEY:-}"

echo "==> Устанавливаю системные пакеты…"
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git

echo "==> Клонирую репозиторий…"
if [ -d "$APP_DIR/.git" ]; then
  cd "$APP_DIR" && git fetch origin && git reset --hard origin/main
else
  git clone "$REPO" "$APP_DIR"
fi
cd "$APP_DIR"

echo "==> Ставлю зависимости…"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt

echo "==> Создаю systemd-сервис…"
cat > /etc/systemd/system/marshrutizator.service <<EOF
[Unit]
Description=Маршрутизатор (FastAPI)
After=network.target

[Service]
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port 80
Environment=YANDEX_GEOCODER_API_KEY=$YANDEX_KEY
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now marshrutizator

echo ""
echo "Готово. Приложение доступно по адресу http://<IP-сервера>/"
echo "Статус:  systemctl status marshrutizator"
echo "Логи:    journalctl -u marshrutizator -f"
echo ""
echo "Если не задал ключ Яндекса — отредактируй его:"
echo "  sudo nano /etc/systemd/system/marshrutizator.service"
echo "  (строка Environment=YANDEX_GEOCODER_API_KEY=...)"
echo "  sudo systemctl daemon-reload && sudo systemctl restart marshrutizator"
