#!/bin/bash
# WebSocket / HTTPUpgrade через Beget CDN: nginx для o-bg.pamirlink.ru начинает передавать Upgrade в Xray на /api/stream/.
# Beget выкидывает из запроса Upgrade и Connection, но оставляет Sec-WebSocket-Key — по нему nginx сам возвращает
# «Upgrade: websocket». Запросы без Upgrade и без ключа (xhttp) идут как раньше — Connection остаётся пустым.
# Другие сайты не трогает. Копии файла — в /root (не в sites-enabled: nginx читает там все файлы):
#   /root/o-bg.pamirlink.ru.bak-ws   — как было до всех правок (её возвращает --undo)
#   /root/o-bg.pamirlink.ru.bak-ws2  — как было перед добавлением правила про Sec-WebSocket-Key
#     bash setup_beget_ws.sh          применить
#     bash setup_beget_ws.sh --undo   вернуть как было до всех правок
set -euo pipefail
F=/etc/nginx/sites-enabled/o-bg.pamirlink.ru
[ -L "$F" ] && F=$(readlink -f "$F")
BAK=/root/o-bg.pamirlink.ru.bak-ws
BAK2=/root/o-bg.pamirlink.ru.bak-ws2

if [ "${1:-}" = "--undo" ]; then
  [ -f "$BAK" ] || { echo "Нет копии $BAK"; exit 1; }
  cp "$BAK" "$F" && nginx -t && systemctl reload nginx && echo "Вернул как было."
  exit 0
fi
grep -q "mognu_bg_ws" "$F" && { echo "Уже настроено."; exit 0; }
grep -q 'location /api/stream/' "$F" || { echo "В $F нет /api/stream/ — ничего не меняю."; exit 1; }
if grep -q "mognu_bg_conn" "$F"; then
  cp "$F" "$BAK2"; RESTORE=$BAK2
else
  cp "$F" "$BAK"; RESTORE=$BAK
fi
python3 - "$F" <<'PY'
import sys
path = sys.argv[1]
src = open(path, encoding='utf-8').read()
maps = ('# Mognu: Upgrade/Connection for WebSocket/HTTPUpgrade through Beget (setup_beget_ws.sh).\n'
        '# Beget strips Upgrade and Connection but keeps Sec-WebSocket-Key, so a request with the key gets\n'
        '# "Upgrade: websocket" back; xhttp (neither header) keeps an empty Connection.\n'
        'map $http_sec_websocket_key $mognu_bg_ws {\n    "" $http_upgrade;\n    default websocket;\n}\n'
        'map $mognu_bg_ws $mognu_bg_conn {\n    default upgrade;\n    "" "";\n}\n')
headers = ('        proxy_set_header Upgrade $mognu_bg_ws;\n'
           '        proxy_set_header Connection $mognu_bg_conn;\n')
old_map = ('# Mognu: Connection for WebSocket/HTTPUpgrade through Beget (setup_beget_ws.sh)\n'
           'map $http_upgrade $mognu_bg_conn {\n    default upgrade;\n    "" "";\n}\n')
old_headers = ('        # Mognu: WebSocket/HTTPUpgrade pass the Upgrade on; xhttp (no Upgrade) keeps an empty Connection\n'
               '        proxy_set_header Upgrade $http_upgrade;\n'
               '        proxy_set_header Connection $mognu_bg_conn;\n')
if old_map in src:
    # the first version of this script was applied: swap its map and headers for the new ones
    if old_headers not in src:
        sys.exit('не нашёл прежние строки Upgrade/Connection — файл менялся, пришли его Claude')
    src = src.replace(old_map, maps).replace(old_headers, headers)
else:
    old = '        proxy_set_header Connection "";\n'
    i = src.find('location /api/stream/')
    j = src.find(old, i)
    if i < 0 or j < 0:
        sys.exit('не нашёл Connection "" в /api/stream/ — файл менялся, пришли его Claude')
    src = src[:j] + headers + src[j + len(old):]
    first = src.index('server {')
    src = src[:first] + maps + src[first:]
open(path, 'w', encoding='utf-8').write(src)
PY
if ! nginx -t; then
  echo "!! nginx -t не прошёл — возвращаю как было"; cp "$RESTORE" "$F"; nginx -t && systemctl reload nginx; exit 1
fi
systemctl reload nginx
echo "Готово. Откат: bash setup_beget_ws.sh --undo"
