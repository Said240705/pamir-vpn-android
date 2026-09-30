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
}
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
relaunch(){ adb shell am force-stop $P; sleep 1; adb shell monkey -p $P -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1; sleep 6; }
toggle(){ adb shell am broadcast -a $P.action.widget.click -n $P/com.v2ray.ang.receiver.WidgetProvider >/dev/null; }
vpn_state(){ log "VPN в системе: $(adb shell dumpsys connectivity | grep -c 'VPN CONNECTED\|type: VPN\[' ) (0 = нет)"; }
check_ip(){ tap_text '(провер|check|tap)'; sleep 12; shot "$1"; }

log "== установка"
adb install -r -g app.apk | tail -1 | tee -a $R
adb shell cmd locale set-app-locales $P --locales ru-RU >/dev/null 2>&1
adb shell appops set $P ACTIVATE_VPN allow
adb shell pm grant $P android.permission.POST_NOTIFICATIONS >/dev/null 2>&1
adb shell input keyevent KEYCODE_HOME; sleep 2; shot home
adb shell monkey -p $P -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1; sleep 10; shot launch

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

log "== настройки"
tap_text '^Настройки$'; sleep 3; shot settings

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
