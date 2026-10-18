#!/bin/bash
# WebSocket / HTTPUpgrade через Beget CDN: nginx для o-bg.pamirlink.ru начинает передавать Upgrade в Xray на /api/stream/.
# Запросы без Upgrade (xhttp) идут как раньше — Connection остаётся пустым, как было. Другие сайты не трогает.
# Копия файла — /root/o-bg.pamirlink.ru.bak-ws (не в sites-enabled: nginx читает там все файлы).
#     bash setup_beget_ws.sh          применить
#     bash setup_beget_ws.sh --undo   вернуть как было
set -euo pipefail
F=/etc/nginx/sites-enabled/o-bg.pamirlink.ru
[ -L "$F" ] && F=$(readlink -f "$F")
BAK=/root/o-bg.pamirlink.ru.bak-ws

if [ "${1:-}" = "--undo" ]; then
  [ -f "$BAK" ] || { echo "Нет копии $BAK"; exit 1; }
  cp "$BAK" "$F" && nginx -t && systemctl reload nginx && echo "Вернул как было."
  exit 0
fi
grep -q "mognu_bg_conn" "$F" && { echo "Уже настроено."; exit 0; }
grep -q 'location /api/stream/' "$F" || { echo "В $F нет /api/stream/ — ничего не меняю."; exit 1; }
cp "$F" "$BAK"
python3 - "$F" <<'PY'
import sys
path = sys.argv[1]
src = open(path, encoding='utf-8').read()
old = '        proxy_set_header Connection "";\n'
i = src.find('location /api/stream/')
j = src.find(old, i)
if i < 0 or j < 0:
    sys.exit('не нашёл Connection "" в /api/stream/ — файл менялся, пришли его Claude')
src = src[:j] + ('        # Mognu: WebSocket/HTTPUpgrade pass the Upgrade on; xhttp (no Upgrade) keeps an empty Connection\n'
                 '        proxy_set_header Upgrade $http_upgrade;\n'
                 '        proxy_set_header Connection $mognu_bg_conn;\n') + src[j + len(old):]
first = src.index('server {')
src = src[:first] + ('# Mognu: Connection for WebSocket/HTTPUpgrade through Beget (setup_beget_ws.sh)\n'
                     'map $http_upgrade $mognu_bg_conn {\n    default upgrade;\n    "" "";\n}\n') + src[first:]
open(path, 'w', encoding='utf-8').write(src)
PY
if ! nginx -t; then
  echo "!! nginx -t не прошёл — возвращаю как было"; cp "$BAK" "$F"; nginx -t && systemctl reload nginx; exit 1
fi
systemctl reload nginx
echo "Готово. Откат: bash setup_beget_ws.sh --undo"
