#!/bin/bash
# День запуска Mognu: серверная часть.
#
#   bash launch_mognu.sh          проверка, ничего не меняет (что готово, что будет сделано)
#   bash launch_mognu.sh go       запуск
#   bash launch_mognu.sh rollback вернуть настройки nginx как были до запуска
#
# Что делает «go»:
#   1. копия всей /etc/nginx → /root/mognu-launch-<время>.tgz
#   2. app.pamirlink.ru: страницы сайта (главная, кабинет, лендинг, статус, инструкции) — постоянный переход (301)
#      на mognu.app. API (/api), APK (/download), страница возврата из оплаты, open-app и go остаются на старом
#      адресе: ими пользуются уже установленные версии Pamir, они должны работать и после запуска.
#   3. mognu.app и mognu.net открываются для поисковиков (убирается noindex).
#   4. nginx -t; при ошибке всё возвращается из копии.
# Бот, письма и BotFather — отдельные шаги, список печатается в конце.
set -uo pipefail
MODE=${1:-check}
OLD=/etc/nginx/sites-enabled/app.pamirlink.ru
NEWS=(/etc/nginx/sites-available/mognu.app /etc/nginx/sites-available/mognu.net)
MARK="# Mognu launch: pages moved"
LAST=/root/mognu-launch.last

ok() { echo "  ✓ $*"; }
no() { echo "  ✗ $*"; }

check() {
  echo "== Проверка (ничего не меняется)"
  for d in mognu.app mognu.net; do
    c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 https://$d/welcome.html); a=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 https://$d/api/topup/public/server-status)
    [ "$c$a" = "200200" ] && ok "$d: сайт и API отвечают" || no "$d: сайт $c, api $a"
  done
  [ -f "$OLD" ] && ok "конфиг старого сайта: $OLD" || no "нет $OLD"
  grep -q "$MARK" "$OLD" 2>/dev/null && echo "  • переход app.pamirlink.ru → mognu.app уже включён" || echo "  • переход app.pamirlink.ru → mognu.app будет включён"
  for f in "${NEWS[@]}"; do
    [ -f "$f" ] || { no "нет $f"; continue; }
    grep -q "noindex" "$f" && echo "  • $(basename "$f"): сейчас скрыт от поисковиков — будет открыт" || ok "$(basename "$f"): уже открыт для поисковиков"
  done
  n=$(grep -rl "Pamir VPN" /root/YadrenoVPN --include=*.py --include=*.json --include=*.txt 2>/dev/null | grep -v "\.bak" | wc -l)
  echo "  • файлов бота с текстом «Pamir VPN»: $n (их меняем отдельным шагом)"
  echo "  • старые версии приложения продолжат ходить на app.pamirlink.ru/api и /download — это не трогается"
}

restore() {
  local bk; bk=$(cat "$LAST" 2>/dev/null)
  [ -f "$bk" ] || { echo "Нет копии для отката"; exit 1; }
  tar -xzf "$bk" -C / && nginx -t && systemctl reload nginx && echo "Откат выполнен: $bk"
}

go() {
  check
  echo; echo "== Запуск"
  BK=/root/mognu-launch-$(date +%Y%m%d-%H%M%S).tgz
  tar -czf "$BK" -C / etc/nginx && echo "$BK" > "$LAST" && ok "копия nginx: $BK"
  if ! grep -q "$MARK" "$OLD"; then
    # вставляем перед первым «location / {» (блок HTTPS старого сайта)
    python3 - "$OLD" "$MARK" <<'PY' || { echo "!! не смог изменить $OLD"; restore; exit 1; }
import sys
p, mark = sys.argv[1], sys.argv[2]
s = open(p, encoding='utf-8').read()
anchor = '    location / {\n'
if s.count(anchor) < 1: sys.exit('no anchor')
block = f'''    {mark} to mognu.app; API, APK and payment pages stay for installed Pamir builds
    location = / {{ return 301 https://mognu.app/$is_args$args; }}
    location ~ ^/(index|login|welcome|status|iphone|reset-password)\\.html$ {{ return 301 https://mognu.app$request_uri; }}
    location ^~ /tv/ {{ return 301 https://mognu.app$request_uri; }}

'''
s = s.replace(anchor, block + anchor, 1)
open(p, 'w', encoding='utf-8').write(s)
PY
    ok "app.pamirlink.ru: страницы → mognu.app"
  fi
  for f in "${NEWS[@]}"; do [ -f "$f" ] && sed -i '/X-Robots-Tag "noindex, nofollow" always;/d; /пока бренд не объявлен/d' "$f"; done
  ok "mognu.app и mognu.net открыты для поисковиков"
  if nginx -t 2>/dev/null; then systemctl reload nginx; ok "nginx перезагружен"; else echo "!! nginx -t не прошёл — возвращаю"; restore; exit 1; fi
  echo; echo "== Проверка после запуска"
  echo "  app.pamirlink.ru/            → $(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' --resolve app.pamirlink.ru:443:127.0.0.1 -k https://app.pamirlink.ru/)"
  echo "  app.pamirlink.ru/api (старые версии) → $(curl -s -o /dev/null -w '%{http_code}' --resolve app.pamirlink.ru:443:127.0.0.1 -k https://app.pamirlink.ru/api/topup/public/server-status)"
  echo "  app.pamirlink.ru/download/android.json → $(curl -s -o /dev/null -w '%{http_code}' --resolve app.pamirlink.ru:443:127.0.0.1 -k https://app.pamirlink.ru/download/android.json)"
  cat <<'EOF'

Готово на сервере. Осталось вручную (чек-лист pamir/docs/MOGNU_LAUNCH.md):
  • BotFather: /setdomain → mognu.app (вход через Telegram на сайте), имя бота, аватарка, кнопка Mini App → https://mognu.app/
  • тексты бота и писем — отдельный патч
  • Яндекс Вебмастер и Google Search Console: добавить mognu.app
Откат nginx: bash launch_mognu.sh rollback
EOF
}

case "$MODE" in
  check) check ;;
  go) go ;;
  rollback) restore ;;
  *) echo "использование: bash launch_mognu.sh [check|go|rollback]"; exit 2 ;;
esac
