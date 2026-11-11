#!/usr/bin/env bash
# LTE Обход 2 (CDNvideo): источник o-bee.pamirlink.ru на основном сервере — по образцу Яндекса (yacdn / o-ya).
#
# 1) сертификат для o-bee (webroot /var/www/html, как у o-ya; порт 80 сюда пересылает Финляндия);
# 2) сайт nginx o-bee: копия yacdn.pamirlink.ru с другим именем, сертификатом и путём LTE
#    /api/sync/ → 2056  ⇒  /api/cv/ → 2057 (сайт, /api/ и /download/ — как у зеркала Яндекса).
# Порт 443 уже ведёт o-bee на nginx (stream map в nginx.conf). Сам вход 2057 — отдельным шагом.
#
#   bash setup_lte2_origin.sh          сделать (повторный запуск ничего не ломает)
set -euo pipefail
NAME=o-bee.pamirlink.ru
SRC=/etc/nginx/sites-enabled/yacdn.pamirlink.ru
DST=/etc/nginx/sites-available/$NAME
PATH_LTE=/api/cv/
PORT_LTE=2057

[ -f "$SRC" ] || { echo "Нет $SRC — не по чему делать копию"; exit 1; }
[ "$(getent ahostsv4 $NAME | awk 'NR==1{print $1}')" = "31.77.6.71" ] || { echo "DNS $NAME не указывает на 31.77.6.71 — сначала запись в Cloudflare"; exit 1; }

if [ ! -s /etc/letsencrypt/live/$NAME/fullchain.pem ]; then
  echo "Выпускаю сертификат для $NAME…"
  certbot certonly --webroot -w /var/www/html -d $NAME --non-interactive --agree-tos --keep-until-expiring -q
fi
echo "сертификат: $(openssl x509 -enddate -noout -in /etc/letsencrypt/live/$NAME/fullchain.pem)"

sed -e "s#server_name [^;]*;#server_name $NAME;#" \
    -e "s#/etc/letsencrypt/live/o-ya.pamirlink.ru/#/etc/letsencrypt/live/$NAME/#g" \
    -e "s#location /api/sync/ {#location $PATH_LTE {#" \
    -e "s#proxy_pass http://127.0.0.1:2056;#proxy_pass http://127.0.0.1:$PORT_LTE;#" \
    "$SRC" > "$DST.new"
grep -q "server_name $NAME;" "$DST.new" && grep -q "location $PATH_LTE" "$DST.new" && grep -q "127.0.0.1:$PORT_LTE" "$DST.new" \
  || { rm -f "$DST.new"; echo "Шаблон yacdn не похож на ожидаемый — ничего не меняю"; exit 1; }
[ "$(grep -c 'server_name' "$DST.new")" = 1 ] || echo "внимание: в шаблоне несколько server-блоков — проверьте $DST"
mv "$DST.new" "$DST"
ln -sf "$DST" /etc/nginx/sites-enabled/$NAME
if ! nginx -t 2>/tmp/ngx.err; then
  rm -f /etc/nginx/sites-enabled/$NAME
  grep -E "emerg|error" /tmp/ngx.err | head -5
  echo "nginx -t не прошёл — сайт $NAME выключен, остальное не тронуто"; exit 1
fi
systemctl reload nginx
echo "nginx: сайт $NAME включён ($PATH_LTE → 127.0.0.1:$PORT_LTE)"
curl -so /dev/null -m 6 -w "проверка https://$NAME/hosts.json: %{http_code}\n" https://$NAME/hosts.json || true
