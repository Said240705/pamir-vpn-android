#!/bin/bash
# Кабинет Mognu через Яндекс CDN: https://yacdn.pamirlink.ru открывает тот же сайт, вход, API и скачивание APK,
# что и mognu.app. Нужен при «белых списках» у мобильных операторов: Cloudflare (mognu.app) и GitHub тогда закрыты,
# а CDN Яндекса открыт — так же работает «LTE Обход». Адрес на .ru, поэтому и с включённым VPN приложение ходит туда
# напрямую, и это тоже работает.
#
# Что делает: в /etc/nginx/sites-enabled/yacdn.pamirlink.ru заменяет страницу-заглушку («location /») на кабинет;
# путь VPN /api/sync/ не трогает (у nginx побеждает более длинный префикс, так что /api/ его не перехватит).
# Копия файла рядом (.bak-cabinet); при ошибке nginx -t всё возвращается.
#     bash setup_cdn_cabinet.sh          применить
#     bash setup_cdn_cabinet.sh --undo   вернуть заглушку
set -euo pipefail
F=/etc/nginx/sites-enabled/yacdn.pamirlink.ru
[ -L "$F" ] && F=$(readlink -f "$F")
WEB=/var/www/mognu/frontend
OLD_FRONT=/var/www/pamir-miniapp/frontend

if [ "${1:-}" = "--undo" ]; then
  [ -f "$F.bak-cabinet" ] || { echo "Нет копии $F.bak-cabinet"; exit 1; }
  cp "$F.bak-cabinet" "$F" && nginx -t && systemctl reload nginx && echo "Вернул заглушку."
  exit 0
fi
grep -q "Mognu cabinet via CDN" "$F" && { echo "Уже настроено."; exit 0; }
grep -q "location /api/sync/" "$F" || { echo "В $F нет /api/sync/ — это не тот файл, ничего не меняю."; exit 1; }

cp "$F" "$F.bak-cabinet"
python3 - "$F" "$WEB" "$OLD_FRONT" <<'PY'
import re, sys
path, web, old = sys.argv[1:4]
src = open(path, encoding='utf-8').read()
stub = re.search(r"\n    location / \{\n        default_type text/html;\n        return 200 [^\n]*\n    \}\n", src)
if not stub:
    sys.exit("Не нашёл заглушку «location /» — файл менялся, пришли его Claude.")
new = f"""
    # Mognu cabinet via CDN (setup_cdn_cabinet.sh): the same site, API and APK as mognu.app
    location ^~ /download/ {{
        root {old};
        types {{ application/vnd.android.package-archive apk; application/json json; }}
        add_header Cache-Control "no-cache" always;
        add_header X-Robots-Tag "noindex, nofollow" always;
        try_files $uri =404;
    }}
    location /api/ {{
        client_max_body_size 20m;
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $mognu_cdn_client_ip;
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
    }}
    location / {{
        root {web};
        index welcome.html index.html;
        try_files $uri $uri/ =404;
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
        add_header X-Robots-Tag "noindex, nofollow" always;
        expires -1;
    }}
"""
# the visitor's own IP for the backend's rate limits: through the CDN every request comes from Yandex edges,
# the visitor is the first address in X-Forwarded-For (map lives at http level, so it goes above the server block)
ip_map = """# Mognu cabinet via CDN: the visitor's IP from X-Forwarded-For (setup_cdn_cabinet.sh)
map $http_x_forwarded_for $mognu_cdn_client_ip {
    default $remote_addr;
    "~^(?P<first>[0-9a-fA-F.:]+)" $first;
}
"""
out = src[:stub.start()] + new + src[stub.end():]
first_server = out.index("server {")
open(path, 'w', encoding='utf-8').write(out[:first_server] + ip_map + out[first_server:])
PY
if ! nginx -t; then
  echo "!! nginx -t не прошёл — возвращаю как было"
  cp "$F.bak-cabinet" "$F"; nginx -t && systemctl reload nginx; exit 1
fi
systemctl reload nginx

echo "== проверка на этом сервере (в обход CDN)"
for p in /welcome.html /api/topup/public/server-status /hosts.json /download/android.json; do
  code=$(curl -sk --max-time 10 --resolve yacdn.pamirlink.ru:443:127.0.0.1 -o /dev/null -w "%{http_code}" "https://yacdn.pamirlink.ru$p" || true)
  echo "   $p → $code"
done
echo "== проверка через CDN Яндекса (как у человека)"
for p in /welcome.html /api/topup/public/server-status; do
  code=$(curl -s --max-time 15 -o /dev/null -w "%{http_code}" "https://yacdn.pamirlink.ru$p" || true)
  echo "   $p → $code"
done
echo "Готово: https://yacdn.pamirlink.ru/  (откат: bash setup_cdn_cabinet.sh --undo)"
