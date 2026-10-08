#!/bin/bash
# Pamir VPN emulator smoke test: install, import subscription, connect, check IP. Screenshots -> shots/
P=ru.pamirlink.vpn
mkdir -p shots; N=0; R=shots/report.txt; : > $R
log(){ echo "$*" | tee -a $R; }
shot(){ N=$((N+1)); F=shots/$(printf %02d $N)_$1.png; adb exec-out screencap -p > "$F"; texts "$1"; }
dumpui(){ adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1; adb pull /sdcard/ui.xml /tmp/ui.xml >/dev/null 2>&1; }
texts(){ dumpui; python3 - "$1" >> $R <<'PY'
import re,sys
s=open('/tmp/ui.xml',encoding='utf-8',errors='ignore').read() if __import__('os').path.exists('/tmp/ui.xml') else ''
t=[x for x in re.findall(r'(?:text|content-desc)="([^"]+)"',s) if x.strip()]
print(f'--- [{sys.argv[1]}] экран:', ' | '.join(t[:40]))
PY
tail -1 $R; }
tap_text(){ dumpui; XY=$(python3 - "$1" <<'PY'
import re,sys
s=open('/tmp/ui.xml',encoding='utf-8',errors='ignore').read()
for node in re.findall(r'<node [^>]*>',s):
    lab=' '.join(x for x in re.findall(r'(?:text|content-desc)="([^"]*)"',node) if x.strip()).strip()
    b=re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',node)
    if b and re.search(sys.argv[1],lab,re.I):
        x1,y1,x2,y2=map(int,b.groups()); print((x1+x2)//2,(y1+y2)//2); break
PY
); if [ -n "$XY" ]; then log "тап [$1] -> $XY"; adb shell input tap $XY; else log "не нашёл на экране: [$1]"; fi; }
# like tap_text, but scrolls down (up to 3 times) when the button is below the small emulator screen
tap_scroll(){ for i in 1 2 3 4; do dumpui; if python3 - "$1" <<'PY'
import re,sys
s=open('/tmp/ui.xml',encoding='utf-8',errors='ignore').read()
sys.exit(0 if any(re.search(sys.argv[1],' '.join(re.findall(r'(?:text|content-desc)="([^"]*)"',n)),re.I) for n in re.findall(r'<node [^>]*>',s)) else 1)
PY
then tap_text "$1"; return; fi; adb shell input swipe 160 480 160 200 400; sleep 1; done; log "не нашёл даже с прокруткой: [$1]"; texts "нет $1"; }
relaunch(){ adb shell am force-stop $P; sleep 1; adb shell monkey -p $P -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1; sleep 6; }
toggle(){ adb shell am broadcast -a $P.action.widget.click -n $P/com.v2ray.ang.receiver.WidgetProvider >/dev/null; }
vpn_state(){ log "VPN в системе: $(adb shell dumpsys connectivity | grep -c 'VPN CONNECTED\|type: VPN\[' ) (0 = нет)"; }
expect(){ dumpui; if grep -q "$1" /tmp/ui.xml; then log "OK: $2"; else log "!!! ОШИБКА: $2"; fi; }
check_ip(){ tap_text '(провер|check|tap)'; sleep 12; shot "$1"; }

log "== установка"
adb install -r -g app.apk | tail -1 | tee -a $R
adb shell cmd locale set-app-locales $P --locales ru-RU >/dev/null 2>&1
adb shell appops set $P ACTIVATE_VPN allow
adb shell pm grant $P android.permission.POST_NOTIFICATIONS >/dev/null 2>&1
adb shell input keyevent KEYCODE_HOME; sleep 2; shot home
adb shell monkey -p $P -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1; sleep 10; shot launch

log "== окно входа по почте"
tap_scroll '^Войти по почте и паролю$'; sleep 3; shot email_login
adb shell input keyevent KEYCODE_BACK; sleep 2

if [ "$REG_TEST" = "1" ]; then
  log "== регистрация в приложении (новый тестовый аккаунт)"
  EMAIL="emu$(date +%y%m%d%H%M%S)@pamirlink.ru"; PASS="Emu$(date +%s)x"
  log "почта: $EMAIL"
  tap_scroll '^Нет аккаунта'; sleep 3; shot register_sheet
  tap_text '^Почта$'; sleep 1; adb shell input text "$EMAIL"; sleep 1
  tap_text '^Придумайте пароль$'; sleep 1; adb shell input text "$PASS"; sleep 1
  tap_text '^Повторите пароль$'; sleep 1; adb shell input text "$PASS"; sleep 1
  adb shell input keyevent KEYCODE_BACK; sleep 1; shot register_filled
  tap_scroll '^Создать аккаунт$'; sleep 10; shot registered
  expect 'Подписки пока нет' 'после регистрации открылся кабинет'

  log "== вкладка VPN после входа без подписки (меню не должно пропадать)"
  tap_text '^VPN$'; sleep 3; shot vpn_tab_nokey
  expect 'Выбрать тариф' 'вкладка VPN показывает «Подписки пока нет»'
  expect 'text="Кабинет"' 'нижнее меню на месте'

  log "== оплата внутри приложения (без оплаты: только открыть страницу)"
  tap_scroll '^Выбрать тариф$'; sleep 6; shot renew_sheet
  tap_scroll '^СБП / Карта$'; sleep 12; shot pay_page
  grep -q 'android.webkit.WebView' /tmp/ui.xml && log "страница оплаты открыта внутри приложения (WebView)" || log "!!! страница оплаты не внутри приложения"
  adb shell input keyevent KEYCODE_BACK; sleep 2; adb shell input keyevent KEYCODE_BACK; sleep 3; shot pay_waiting
  tap_text '^Отменить$'; sleep 2; adb shell input keyevent KEYCODE_BACK; sleep 2
fi

log "== импорт подписки"
ENC=$(python3 -c "import urllib.parse,os;print(urllib.parse.quote(os.environ.get('SUB_URL',''),safe=''))")
[ -z "$ENC" ] && log "!!! нет секрета TEST_SUB_URL"
adb logcat -c
adb shell "am start -W -a android.intent.action.VIEW -d 'pamirvpn://install-sub?url=$ENC'" 2>&1 | grep -E 'Status|Activity|Error' | tee -a $R
sleep 12; shot home_after_import

log "== подключение (выбранный сервер)"
tap_text '^Не подключено$'; sleep 3; shot connecting
sleep 10; vpn_state; shot connected

log "== смена на LTE Обход во время подключения"
tap_text 'Сменить'; sleep 5; shot server_sheet
tap_text '^LTE Обход$'; sleep 14; vpn_state; shot connected_lte

log "== плитка в шторке и уведомление"
T=$P/com.v2ray.ang.service.QSTileService
adb shell cmd statusbar add-tile $T >/dev/null 2>&1
adb shell cmd statusbar expand-notifications; sleep 3; shot shade_on
adb shell cmd statusbar click-tile $T; sleep 6; vpn_state; shot tile_off
adb shell cmd statusbar click-tile $T; sleep 12; vpn_state; shot tile_on_again
adb shell cmd statusbar expand-notifications; sleep 3; shot notifications
adb shell cmd statusbar collapse; sleep 3; shot app_after_tile

log "== окно продления (без входа)"
tap_text 'Продлить'; sleep 3; shot renew_sheet
adb shell input keyevent KEYCODE_BACK; sleep 2

log "== настройки"
tap_text '^Настройки$'; sleep 3; shot settings

log "== приложения без VPN"
tap_text '^Приложения без VPN$'; sleep 4; shot apps_screen
adb shell input keyevent KEYCODE_BACK; sleep 2

log "== сообщить о проблеме (отправит тестовый отчёт админу)"
adb shell input swipe 160 520 160 120 400; sleep 2; shot settings_bottom
tap_scroll '^Сообщить о проблеме$'; sleep 3
tap_text '^Например'; sleep 1
adb shell input text "Avtotest%sPamir%sVPN%s-%sotchet%siz%semulyatora"; sleep 1
adb shell input keyevent KEYCODE_BACK; sleep 1; shot report_sheet
tap_text '^Отправить$'; sleep 6; shot report_sent
adb shell input swipe 160 150 160 560 400; sleep 1

log "== кабинет"
tap_text '^Кабинет$'; sleep 3; shot cabinet_logged_out
tap_text '^VPN$'; sleep 2

log "== отключение"
tap_text '^VPN$'; sleep 2
tap_text '^Защищено$|^Подключение'; sleep 6; vpn_state; shot disconnected

adb logcat -d | grep -iE 'Pamir|LauncherManager|StartCore|FATAL|AndroidRuntime: (FATAL|java)' | grep -v 'I/chatty' | tail -150 > shots/logcat.txt
python3 - <<'PY'
import os,urllib.parse
u=os.environ.get('SUB_URL','')
if u:
    for f in ('shots/report.txt','shots/logcat.txt'):
        if os.path.exists(f):
            t=open(f,errors='ignore').read()
            for v in (u,urllib.parse.quote(u,safe=''),u.rsplit('/',1)[-1]):
                if v: t=t.replace(v,'***')
            open(f,'w').write(t)
PY
log "== готово"
