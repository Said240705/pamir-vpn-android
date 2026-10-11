#!/bin/bash
# Mognu: сайт на mognu.app (через Cloudflare) — новый сайт из ветки mognu, /api — тот же бэкенд, что у app.pamirlink.ru.
#
# Что делает:
#   1. копия всей /etc/nginx → /root/nginx-backup-mognu-<время>.tgz
#   2. выкладывает ветку mognu сайта в /var/www/mognu/frontend (через /opt/pamir-site, живой сайт не трогает)
#   3. порт 80 для mognu.app → получает сертификат Let's Encrypt (certbot, webroot)
#   4. HTTPS-блок mognu.app на 127.0.0.1:8443 (как у app.pamirlink.ru) + две строки в маршрутизаторе 443
#   5. nginx -t; при ошибке возвращает прежние файлы и ничего не применяет
# Пока бренд не объявлен, поисковикам отдаётся noindex. Старый сайт, бот и VPN не меняются.
# Повторный запуск: только обновляет файлы сайта (настройки nginx уже есть).
set -euo pipefail
DOMAIN=mognu.app
WEB=/var/www/mognu/frontend
ACME=/var/www/mognu/acme
SITE=/etc/nginx/sites-available/$DOMAIN
LINK=/etc/nginx/sites-enabled/$DOMAIN
OLD_FRONT=/var/www/pamir-miniapp/frontend

echo "== 1. копия настроек nginx"
BK=/root/nginx-backup-mognu-$(date +%Y%m%d-%H%M%S).tgz
tar -czf "$BK" -C / etc/nginx
echo "   $BK"

echo "== 2. файлы сайта из ветки mognu"
cd /opt/pamir-site
timeout 120 git fetch -q origin mognu
mkdir -p "$WEB" "$ACME"
git archive FETCH_HEAD | tar -x -C "$WEB"
echo "   $(ls "$WEB" | wc -l) файлов в $WEB"

if [ -f "$SITE" ] && grep -q "listen 127.0.0.1:8443 ssl" "$SITE"; then
  nginx -t && systemctl reload nginx
  echo "Готово: настройки уже были, обновлены только файлы сайта. https://$DOMAIN/"
  exit 0
fi

ROUTER=$(grep -rl "pamir-443-router" /etc/nginx --include=*.conf 2>/dev/null | head -1 || true)
[ -n "$ROUTER" ] || ROUTER=$(grep -rl "pamir-443-router" /etc/nginx 2>/dev/null | head -1 || true)
[ -n "$ROUTER" ] || { echo "Не нашёл маршрутизатор 443 (pamir-443-router) — ничего не меняю."; exit 1; }
echo "   маршрутизатор: $ROUTER"

restore() {
  echo "!! Ошибка — возвращаю прежние настройки nginx"
  rm -f "$LINK" "$SITE"
  tar -xzf "$BK" -C /
  nginx -t && systemctl reload nginx || true
  exit 1
}

echo "== 3. порт 80 и сертификат"
cat > "$SITE" <<EOF
# Mognu (setup_mognu_domain.sh)
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;
    location /.well-known/acme-challenge/ { root $ACME; try_files \$uri =404; }
    location / { return 301 https://$DOMAIN\$request_uri; }
}
EOF
ln -sf "$SITE" "$LINK"
nginx -t || restore
systemctl reload nginx
certbot certonly --webroot -w "$ACME" -d "$DOMAIN" -d "www.$DOMAIN" --non-interactive --agree-tos --keep-until-expiring \
  || { echo "!! Сертификат не выдан: проверьте записи DNS в Cloudflare (A @ и CNAME www) и что прошло пару минут."; restore; }

echo "== 4. HTTPS и маршрутизатор"
cat >> "$SITE" <<EOF

server {
    listen 127.0.0.1:8443 ssl;
    server_name www.$DOMAIN;
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    return 301 https://$DOMAIN\$request_uri;
}

server {
    listen 127.0.0.1:8443 ssl;
    server_name $DOMAIN;
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    absolute_redirect off;
    # пока бренд не объявлен — не индексировать (убрать при запуске Mognu)
    add_header X-Robots-Tag "noindex, nofollow" always;

    # APK и android.json — те же файлы, что у app.pamirlink.ru
    location ^~ /download/ {
        root $OLD_FRONT;
        types { application/vnd.android.package-archive apk; application/json json; }
        add_header Cache-Control "no-cache";
        add_header X-Robots-Tag "noindex, nofollow" always;
        try_files \$uri =404;
    }

    location /api/ {
        client_max_body_size 20m;
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location / {
        root $WEB;
        index welcome.html index.html;
        try_files \$uri \$uri/ =404;
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
        add_header X-Robots-Tag "noindex, nofollow" always;
        expires -1;
    }
}
EOF
if ! grep -qE "^\s*$DOMAIN\s" "$ROUTER"; then
  sed -i "s/^\(\s*\)app\.pamirlink\.ru\(\s\+\)pamir_web;/&\n\1$DOMAIN\2pamir_web;\n\1www.$DOMAIN pamir_web;/" "$ROUTER"
fi
grep -qE "^\s*$DOMAIN\s" "$ROUTER" || { echo "!! Не смог добавить $DOMAIN в маршрутизатор"; restore; }
nginx -t || restore
systemctl reload nginx

echo "== 5. проверка"
code=$(curl -sk --max-time 10 --resolve $DOMAIN:443:127.0.0.1 -o /dev/null -w "%{http_code}" "https://$DOMAIN/welcome.html" || true)
api=$(curl -sk --max-time 10 --resolve $DOMAIN:443:127.0.0.1 -o /dev/null -w "%{http_code}" "https://$DOMAIN/api/topup/public/server-status" || true)
old=$(curl -sk --max-time 10 --resolve app.pamirlink.ru:443:127.0.0.1 -o /dev/null -w "%{http_code}" "https://app.pamirlink.ru/" || true)
echo "   mognu.app: сайт $code, api $api; старый app.pamirlink.ru: $old"
echo "Готово: https://$DOMAIN/  (откат: tar -xzf $BK -C / && rm -f $LINK && systemctl reload nginx)"
