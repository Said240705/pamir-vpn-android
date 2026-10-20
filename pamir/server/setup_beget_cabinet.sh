#!/bin/bash
# Кабинет Mognu через Beget CDN: тот же сайт, вход, API и скачивание APK, что и mognu.app, по адресу CDN Beget
# (тот же, через который работает «LTE Обход 3»). Нужен при «белых списках»: CDN Яндекса (yacdn) не пропускает
# POST, поэтому вход там не работает, а Beget пропускает — на POST держится и сам xhttp.
#
# Что делает: в /etc/nginx/sites-enabled/o-bg.pamirlink.ru заменяет страницу-заглушку («location /») на кабинет;
# путь VPN /api/stream/ не трогает (у nginx побеждает более длинный префикс). Копия — /root/o-bg.pamirlink.ru.bak-cabinet,
# при ошибке nginx -t всё возвращается. Потом через сам CDN проверяет страницу, API, POST и адрес с UUID
# (Beget режет UUID с дефисами — если путь с ним не пройдёт, это будет видно).
#     bash setup_beget_cabinet.sh            применить и проверить
#     bash setup_beget_cabinet.sh --check    только проверить через CDN
#     bash setup_beget_cabinet.sh --undo     вернуть заглушку
#
# ID платежа (UUID) Beget отбивает в адресе даже без дефисов, но пропускает в cookie: кабинет на адресе Beget кладёт
# его в cookie mq_order_id / mq_token (app.js, hideIdsForBeget), а здесь nginx возвращает его в строку запроса.
set -uo pipefail
F=/etc/nginx/sites-enabled/o-bg.pamirlink.ru
[ -L "$F" ] && F=$(readlink -f "$F")
WEB=/var/www/mognu/frontend
OLD_FRONT=/var/www/pamir-miniapp/frontend
BAK=/root/o-bg.pamirlink.ru.bak-cabinet

# адрес CDN — из «Hosts» входа 2058 в панели (как в mognu_beget_probe.py)
cdn_host() {
  python3 - <<'PY'
import json, sqlite3
db = sqlite3.connect('file:/etc/x-ui/x-ui.db?mode=ro', uri=True)
inb = db.execute("select id from inbounds where port=2058").fetchone()
row = inb and db.execute("select * from hosts where inbound_id=? order by id limit 1", (inb[0],)).fetchone()
vals = [v for v in (row or []) if isinstance(v, str)]
print(next((v for v in vals if '.' in v and '/' not in v and ' ' not in v and not v.startswith('[')), ''))
PY
}

check() {
  H=$(cdn_host)
  [ -n "$H" ] || { echo "!! не нашёл адрес CDN в настройках входа 2058 — пришли Claude скрин вкладки Hosts в панели для «LTE Обход 3»"; return 1; }
  echo "== через Beget CDN: https://$H"
  for p in /welcome.html /index.html /api/topup/public/server-status /download/android.json; do
    echo "   GET  $p → $(curl -s --max-time 15 -o /dev/null -w "%{http_code}" "https://$H$p")"
  done
  # POST на публичный адрес: наш сервер ответит 405 с JSON {"detail":...} — значит POST дошёл до нас
  b=$(curl -s --max-time 15 -X POST -H 'Content-Type: application/json' -d '{"probe":1}' -w " [%{http_code}]" "https://$H/api/topup/public/server-status")
  echo "   POST /api/... → ${b:0:160}"
  echo "$b" | grep -q '"detail"' && echo "   ✅ POST доходит до нашего сервера" || echo "   ❌ POST не дошёл (ответил не наш сервер)"
  u=$(cat /proc/sys/kernel/random/uuid)
  echo "   GET с UUID в адресе → $(curl -s --max-time 15 -o /dev/null -w "%{http_code}" "https://$H/api/topup/public/server-status?order=$u") (200 — UUID проходит)"
  echo "Кабинет для белых списков: https://$H/"
}

if [ "${1:-}" = "--check" ]; then check; exit 0; fi
if [ "${1:-}" = "--undo" ]; then
  [ -f "$BAK" ] || { echo "Нет копии $BAK"; exit 1; }
  cp "$BAK" "$F" && nginx -t && systemctl reload nginx && echo "Вернул заглушку."
  exit 0
fi
[ -f "$F" ] || { echo "Нет $F — сначала setup_beget_cdn.sh"; exit 1; }
# ID из cookie обратно в адрес: отдельный шаг, его можно доставить и на уже настроенный сервер
add_ids() {
  grep -q 'mq_order_id' "$F" && return 0
  cp "$F" "$BAK.ids"
  python3 - "$F" <<'PY2'
import sys
path = sys.argv[1]
src = open(path, encoding='utf-8').read()
maps = ""
for k in ("order_id", "token"):
    maps += (f"map $cookie_mq_{k} $mq_{k} {{\n    default \"\";\n"
             f"    \"~^([0-9a-f]{{8}})([0-9a-f]{{4}})([0-9a-f]{{4}})([0-9a-f]{{4}})([0-9a-f]{{12}})$\" \"$1-$2-$3-$4-$5\";\n}}\n")
anchor = "    location /api/ {\n        client_max_body_size 20m;\n"
assert anchor in src, "нет location /api/ кабинета"
ifs = ('        # Beget отбивает UUID в адресе: кабинет прислал его в cookie, возвращаем в строку запроса\n'
       '        if ($mq_order_id) { rewrite ^/api/(.*)$ /$1?order_id=$mq_order_id break; }\n'
       '        if ($mq_token) { rewrite ^/api/(.*)$ /$1?token=$mq_token break; }\n')
src = src.replace(anchor, anchor + ifs, 1)
i = src.index("server {")
open(path, 'w', encoding='utf-8').write("# Mognu cabinet via Beget CDN: IDs from cookies back into the query\n" + src[:i] + maps + src[i:])
PY2
  if [ $? -ne 0 ] || ! nginx -t 2>/dev/null; then echo "!! ID из cookie: не получилось — возвращаю как было"; cp "$BAK.ids" "$F"; return 1; fi
  systemctl reload nginx; sleep 1
  # опрос входа через Telegram без токена и с токеном из cookie: ответы должны отличаться — значит токен дошёл
  U=$(cat /proc/sys/kernel/random/uuid); X=${U//-/}; P="https://o-bg.pamirlink.ru/api/auth/telegram/poll"
  r1=$(curl -sk --max-time 10 --resolve o-bg.pamirlink.ru:443:127.0.0.1 "$P" -w ' [%{http_code}]')
  r2=$(curl -sk --max-time 10 --resolve o-bg.pamirlink.ru:443:127.0.0.1 -b "mq_token=$X" "$P" -w ' [%{http_code}]')
  echo "   без ID:        ${r1:0:120}"
  echo "   ID из cookie:  ${r2:0:120}"
  [ "$r1" != "$r2" ] && echo "   ✅ ID из cookie доходит до сервера" || echo "   ❌ ответы одинаковые — пришли вывод Claude"
}

if grep -q "Mognu cabinet via Beget CDN" "$F"; then echo "Уже настроено."; add_ids; check; exit 0; fi
grep -q "location /api/stream/" "$F" || { echo "В $F нет /api/stream/ — это не тот файл, ничего не меняю."; exit 1; }

cp "$F" "$BAK"
# адрес посетителя для лимитов бэкенда: map из setup_cdn_cabinet.sh (yacdn) общий на весь nginx — если его нет, добавим
HAVE_MAP=$(grep -rls 'mognu_cdn_client_ip' /etc/nginx/nginx.conf /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null | grep -v "^$F$" | head -1)
python3 - "$F" "$WEB" "$OLD_FRONT" "${HAVE_MAP:+1}" <<'PY'
import re, sys
path, web, old, have_map = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else ''
src = open(path, encoding='utf-8').read()
stub = re.search(r"\n    location / \{\n        default_type text/html;\n        return 200 [^\n]*\n    \}\n", src)
if not stub:
    sys.exit("Не нашёл заглушку «location /» — файл менялся, пришли его Claude.")
new = f"""
    # Mognu cabinet via Beget CDN (setup_beget_cabinet.sh): the same site, API and APK as mognu.app
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
out = src[:stub.start()] + new + src[stub.end():]
if not have_map:
    ip_map = """# Mognu cabinet via CDN: the visitor's IP from X-Forwarded-For
map $http_x_forwarded_for $mognu_cdn_client_ip {
    default $remote_addr;
    "~^(?P<first>[0-9a-fA-F.:]+)" $first;
}
"""
    i = out.index("server {")
    out = out[:i] + ip_map + out[i:]
open(path, 'w', encoding='utf-8').write(out)
PY
[ $? -eq 0 ] || { cp "$BAK" "$F"; exit 1; }
if ! nginx -t; then
  echo "!! nginx -t не прошёл — возвращаю как было"
  cp "$BAK" "$F"; nginx -t && systemctl reload nginx; exit 1
fi
systemctl reload nginx; sleep 2
add_ids
echo "== на этом сервере (в обход CDN)"
for p in /welcome.html /api/topup/public/server-status /download/android.json; do
  echo "   $p → $(curl -sk --max-time 10 --resolve o-bg.pamirlink.ru:443:127.0.0.1 -o /dev/null -w "%{http_code}" "https://o-bg.pamirlink.ru$p")"
done
check
echo "Откат: bash setup_beget_cabinet.sh --undo"
