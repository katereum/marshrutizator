#!/usr/bin/env bash
# Включает HTTPS (Let's Encrypt) для «Маршрутизатора» через Caddy.
# Бесплатный домен: <публичный-IP>.nip.io (вариант А, без покупки домена).
# Запуск на сервере: sudo bash setup-https.sh
set -euo pipefail

APP_DIR="/opt/marshrutizator"

echo "==> Определяю публичный IP…"
IP="$(curl -s https://api.ipify.org)"
DOMAIN="${IP}.nip.io"
echo "    Домен: ${DOMAIN}"

echo "==> Устанавливаю Caddy…"
apt-get update -y
apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update -y
apt-get install -y caddy

echo "==> Настраиваю Caddy (reverse-proxy на приложение)…"
cat > /etc/caddy/Caddyfile <<EOF
${DOMAIN} {
    reverse_proxy 127.0.0.1:8000
    encode gzip
}
EOF

echo "==> Переношу приложение на внутренний порт 8000 (наружу только через Caddy)…"
sed -i 's/--host 0.0.0.0/--host 127.0.0.1/' /etc/systemd/system/marshrutizator.service
sed -i 's/--port 80/--port 8000/' /etc/systemd/system/marshrutizator.service
systemctl daemon-reload
systemctl restart marshrutizator

echo "==> Удаляю старый кэш геокодера (адреса не храним)…"
rm -rf "${APP_DIR}/.cache" || true

echo "==> Запускаю Caddy…"
systemctl enable --now caddy
systemctl restart caddy

echo ""
echo "Готово. Сайт теперь по адресу:"
echo "  https://${DOMAIN}"
echo ""
echo "Старый http://<IP>/ перестанет открываться напрямую — это нормально,"
echo "заходим только по HTTPS-адресу выше."
echo ""
echo "Проверка (должен вернуть HTTP/2 200 или 301):"
echo "  curl -I https://${DOMAIN}"
echo ""
echo "Если сертификат не выпустился — смотри логи Caddy:"
echo "  journalctl -u caddy -n 50 --no-pager"
echo "  (частая причина — лимит Let's Encrypt на общий домен .nip.io;"
echo "   тогда напиши мне — есть запасной бесплатный вариант DuckDNS)."
