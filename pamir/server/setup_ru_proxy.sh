#!/bin/bash
# Mognu без VPN на мобильном интернете: российский VPS — посредник для mognu.app.
#   люди → mognu.app (этот VPS, Россия) → origin.mognu.app (основной сервер) — сайт, вход, оплата, API и APK.
# Запускать на ЧИСТОМ VPS (Ubuntu/Debian) от root, ПОСЛЕ того как в Cloudflare запись mognu.app (и www)
# переведена на IP этого VPS с серым облачком:
#
#   bash setup_ru_proxy.sh            настроить (nginx + сертификат Let's Encrypt, продлевается сам)
#   bash setup_ru_proxy.sh check      проверка
#
# Продление сертификата основного сервера (на нём mognu.app тоже есть в сертификате) проходит через этот VPS:
# неизвестные ему /.well-known/acme-challenge/ он отправляет дальше на основной сервер.
set -euo pipefail
DOMAIN=mognu.app
ORIGIN=origin.mognu.app
ACME=/var/www/acme
CONF=/etc/nginx/sites-available/mognu-proxy
MODE=${1:-setup}

check() {
  echo "  DNS $DOMAIN → $(getent ahostsv4 $DOMAIN | awk 'NR==1{print $1}'), этот VPS: $(curl -s4 --max-time 8 https://ifconfig.me || echo '?')"
  for u in /welcome.html /api/topup/public/server-status; do
    echo "  GET $u → $(curl -s -o /dev/null -w '%{http_code}' --max-time 15 --resolve $DOMAIN:443:127.0.0.1 https://$DOMAIN$u)"
  done
  echo "  POST api → $(curl -s -X POST -H 'Content-Type: application/json' -d '{}' --max-time 15 --resolve $DOMAIN:443:127.0.0.1 https://$DOMAIN/api/topup/public/server-status | head -c 60)"
  echo "  APK → $(curl -s -o /dev/null -w '%{http_code} %{size_download}' -r 0-1023 --max-time 15 --resolve $DOMAIN:443:127.0.0.1 https://$DOMAIN/download/pamir-vpn-universal.apk)"
}
[ "$MODE" = check ] && { check; exit 0; }

me=$(curl -s4 --max-time 8 https://ifconfig.me || true)
dns=$(getent ahostsv4 $DOMAIN | awk 'NR==1{print $1}' || true)
[ -n "$me" ] && [ "$dns" = "$me" ] || { echo "Сначала в Cloudflare: A-запись $DOMAIN → $me (серое облачко). Сейчас $DOMAIN → '${dns}'. Ничего не меняю."; exit 1; }
getent ahostsv4 $ORIGIN >/dev/null || { echo "$ORIGIN не находится в DNS — проверь A-запись origin в Cloudflare."; exit 1; }

echo "== пакеты"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq nginx certbot >/dev/null
mkdir -p "$ACME"

proxy_common='
        proxy_pass https://'$ORIGIN';
        proxy_ssl_server_name on;
        proxy_ssl_name '$ORIGIN';
        proxy_http_version 1.1;
        proxy_set_header Host '$DOMAIN';
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 120s;'

write_conf() {  # $1 = with_tls (0/1)
  {
    echo '# Mognu: RU proxy for mognu.app (setup_ru_proxy.sh)'
    echo 'map $http_upgrade $connection_upgrade { default upgrade; "" close; }'
    echo 'server {'
    echo "    listen 80; listen [::]:80;"
    echo "    server_name $DOMAIN www.$DOMAIN;"
    echo "    location ^~ /.well-known/acme-challenge/ { root $ACME; try_files \$uri @origin_acme; }"
    echo "    location @origin_acme { proxy_pass http://$ORIGIN; proxy_set_header Host \$host; }"
    echo "    location / { return 301 https://$DOMAIN\$request_uri; }"
    echo '}'
    if [ "$1" = 1 ]; then
      echo 'server {'
      echo "    listen 443 ssl http2; listen [::]:443 ssl http2;"
      echo "    server_name $DOMAIN www.$DOMAIN;"
      echo "    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;"
      echo "    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;"
      echo "    client_max_body_size 25m;"
      echo "    if (\$host = www.$DOMAIN) { return 301 https://$DOMAIN\$request_uri; }"
      echo "    location ^~ /.well-known/acme-challenge/ { root $ACME; try_files \$uri @origin_acme; }"
      echo "    location @origin_acme { proxy_pass http://$ORIGIN; proxy_set_header Host \$host; }"
      echo "    location / {$proxy_common"
      echo '    }'
      echo '}'
    fi
  } > "$CONF"
  ln -sf "$CONF" /etc/nginx/sites-enabled/mognu-proxy
  rm -f /etc/nginx/sites-enabled/default
  nginx -t && systemctl reload nginx
}

echo "== порт 80 и сертификат"
write_conf 0
certbot certonly --webroot -w "$ACME" -d $DOMAIN -d www.$DOMAIN --non-interactive --agree-tos \
  --register-unsafely-without-email --keep-until-expiring --deploy-hook "systemctl reload nginx"
echo "== HTTPS"
write_conf 1
echo "== проверка"
check
cat <<EOF

Готово. Сертификат продлевается сам (certbot.timer). На основном сервере осталось одно:
показать бэкенду настоящие IP людей вместо IP этого VPS — команду пришлёт Claude (нужен IP: $me).
EOF
