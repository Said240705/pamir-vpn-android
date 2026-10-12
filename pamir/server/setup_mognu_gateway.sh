#!/bin/bash
# Mognu через Яндекс (без VPN на мобильном интернете): готовит сервер к схеме
#   mognu.app      → Yandex API Gateway → origin.mognu.app (этот сервер): сайт и API, POST работает
#   dl.mognu.app   → Yandex Cloud CDN   → этот сервер: APK (CDN Яндекса не пропускает POST, а шлюз — ответы больше 2,5 МБ)
#
# До запуска в Cloudflare: A-записи origin и dl → 78.17.158.230, облачко серое (DNS only).
#
#   bash setup_mognu_gateway.sh          настроить (копия nginx, откат при любой ошибке)
#   bash setup_mognu_gateway.sh check    только проверка
#
# Что делает:
#   1. копия всей /etc/nginx → /root/nginx-backup-gateway-<время>.tgz
#   2. origin.mognu.app и dl.mognu.app — те же сайт и API, что mognu.app (имена в nginx и в маршрутизаторе 443)
#   3. API получает Host: mognu.app, как бы ни пришёл запрос (ссылки в ответах — на mognu.app)
#   4. /.well-known/acme-challenge/ отвечает и по HTTPS — продление сертификата пройдёт через шлюз и CDN
#   5. новый сертификат mognu.app (+ www, origin, dl) с НОВЫМ ключом — его загрузить в Certificate Manager
set -euo pipefail
MODE=${1:-setup}
SITE=/etc/nginx/sites-available/mognu.app
ACME=/var/www/mognu/acme
LIVE=/etc/letsencrypt/live/mognu.app
EXTRA=(origin.mognu.app dl.mognu.app)

check() {
  for d in mognu.app "${EXTRA[@]}"; do
    w=$(curl -sk --max-time 10 --resolve $d:443:127.0.0.1 -o /dev/null -w '%{http_code}' https://$d/welcome.html || true)
    p=$(curl -sk --max-time 10 --resolve $d:443:127.0.0.1 -X POST -H 'Content-Type: application/json' -d '{}' \
        https://$d/api/topup/public/server-status || true)
    echo "  $d: сайт $w, POST api: ${p:0:40}"
  done
  echo "  сертификат: $(openssl x509 -in $LIVE/cert.pem -noout -enddate 2>/dev/null) ;" \
       "$(openssl x509 -in $LIVE/cert.pem -noout -ext subjectAltName 2>/dev/null | tail -1 | xargs)"
}
[ "$MODE" = check ] && { check; exit 0; }

[ -f "$SITE" ] || { echo "Нет $SITE — сначала setup_mognu_domain.sh"; exit 1; }
for d in "${EXTRA[@]}"; do
  ip=$(dig +short "$d" A | tail -1)
  [ "$ip" = "78.17.158.230" ] || { echo "$d → '${ip}', нужно 78.17.158.230 (A-запись в Cloudflare, серое облачко). Ничего не меняю."; exit 1; }
done
ROUTER=$(grep -rl "pamir-443-router" /etc/nginx 2>/dev/null | head -1 || true)
[ -n "$ROUTER" ] || { echo "Не нашёл маршрутизатор 443 — ничего не меняю."; exit 1; }

BK=/root/nginx-backup-gateway-$(date +%Y%m%d-%H%M%S).tgz
tar -czf "$BK" -C / etc/nginx
echo "== копия nginx: $BK"
restore() { echo "!! Ошибка — возвращаю nginx из копии"; tar -xzf "$BK" -C /; nginx -t && systemctl reload nginx || true; exit 1; }
trap restore ERR

echo "== имена origin и dl"
python3 - "$SITE" <<'PY'
import re, sys
p = sys.argv[1]; s = open(p, encoding='utf-8').read()
extra = 'origin.mognu.app dl.mognu.app'
s = s.replace('server_name mognu.app www.mognu.app;', f'server_name mognu.app www.mognu.app {extra};')  # port 80
s = re.sub(r'server_name mognu\.app;', f'server_name mognu.app {extra};', s)                            # HTTPS
s = s.replace('proxy_set_header Host $host;', 'proxy_set_header Host mognu.app;')
acme = '    location ^~ /.well-known/acme-challenge/ { root /var/www/mognu/acme; try_files $uri =404; }\n'
if acme not in s:
    s = s.replace('    location ^~ /download/ {', acme + '\n    location ^~ /download/ {', 1)
if s.count(extra) < 2 or acme not in s:
    sys.exit('не тот формат файла')
open(p, 'w', encoding='utf-8').write(s)
PY
for d in "${EXTRA[@]}"; do
  if ! grep -qE "^\s*${d//./\\.}\s" "$ROUTER"; then
    sed -i "s/^\(\s*\)mognu\.app\(\s\+\)pamir_web;/&\n\1$d\2pamir_web;/" "$ROUTER"
  fi
  grep -qE "^\s*${d//./\\.}\s" "$ROUTER"
done
nginx -t
systemctl reload nginx

echo "== сертификат с новым ключом"
certbot certonly --webroot -w "$ACME" --cert-name mognu.app -d mognu.app -d www.mognu.app \
  -d origin.mognu.app -d dl.mognu.app --expand --force-renewal --non-interactive --agree-tos
systemctl reload nginx
trap - ERR

echo "== проверка"
check
cat <<EOF

Готово. Для Certificate Manager (сертификат mognu-app-own → «Обновить»), файлы на сервере:
  сертификат:  $LIVE/cert.pem
  цепочка:     $LIVE/chain.pem
  ключ:        $LIVE/privkey.pem   (не показывать никому и не вставлять в чат)
Откат nginx: tar -xzf $BK -C / && systemctl reload nginx
EOF
