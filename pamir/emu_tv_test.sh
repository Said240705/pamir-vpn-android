#!/bin/bash
# Pamir VPN on Android TV (emulator): launcher entry, remote-control focus, QR sign-in, import, connect.
# Everything is driven by D-pad key events, as with a real remote. Screenshots -> shots/
P=ru.pamirlink.vpn
mkdir -p shots; N=0; R=shots/report.txt; : > $R
log(){ echo "$*" | tee -a $R; }
shot(){ N=$((N+1)); F=shots/$(printf %02d $N)_tv_$1.png; adb exec-out screencap -p > "$F"; texts "$1"; }
texts(){ adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1; adb pull /sdcard/ui.xml /tmp/ui.xml >/dev/null 2>&1
python3 - "$1" >> $R <<'PY'
import os,re,sys
s=open('/tmp/ui.xml',encoding='utf-8',errors='ignore').read() if os.path.exists('/tmp/ui.xml') else ''
t=[x for x in re.findall(r'(?:text|content-desc)="([^"]+)"',s) if x.strip()]
f=re.findall(r'<node [^>]*focused="true"[^>]*>',s)
lab=[' '.join(x for x in re.findall(r'(?:text|content-desc)="([^"]*)"',n) if x.strip()) for n in f]
print(f'--- [{sys.argv[1]}] экран:', ' | '.join(t[:40]))
print(f'    в фокусе: {lab[-1] if lab else "-"}')
PY
}
key(){ for k in "$@"; do adb shell input keyevent "KEYCODE_$k"; sleep 1; done; }
vpn_state(){ log "VPN в системе: $(adb shell dumpsys connectivity | grep -c 'VPN CONNECTED\|type: VPN\[' ) (0 = нет)"; }

log "== установка"
adb install -r -g app.apk | tail -1 | tee -a $R
adb shell cmd locale set-app-locales $P --locales ru-RU >/dev/null 2>&1
adb shell appops set $P ACTIVATE_VPN allow

log "== приложение в меню телевизора"
adb shell cmd package query-activities --brief -a android.intent.action.MAIN -c android.intent.category.LEANBACK_LAUNCHER \
  | grep -q "$P/" && log "есть в меню ТВ (LEANBACK_LAUNCHER)" || log "!!! НЕТ в меню ТВ"
key HOME; sleep 3; shot launcher

log "== запуск с пульта"
adb shell monkey -p $P -c android.intent.category.LEANBACK_LAUNCHER 1 2>&1 | grep -iE "Events injected|No activities|error" | tee -a $R
sleep 10; log "на экране: $(adb shell dumpsys activity activities | grep -m1 -E 'topResumedActivity|mResumedActivity' | sed 's/^ *//')"
shot onboarding

log "== вход через Telegram: QR-код"
key DPAD_CENTER; sleep 5; shot login_qr
key BACK; sleep 2; shot login_cancelled

log "== переход пультом вниз: вход по почте"
key DPAD_DOWN; shot focus_email
key DPAD_CENTER; sleep 3; shot email_login
key BACK BACK; sleep 2

log "== импорт подписки"
ENC=$(python3 -c "import urllib.parse,os;print(urllib.parse.quote(os.environ.get('SUB_URL',''),safe=''))")
[ -z "$ENC" ] && log "!!! нет секрета TEST_SUB_URL"
adb logcat -c
adb shell "am start -W -a android.intent.action.VIEW -d 'pamirvpn://install-sub?url=$ENC'" 2>&1 | grep -E 'Status|Activity|Error' | tee -a $R
sleep 12; shot home

log "== подключение кнопкой OK (фокус на кнопке питания)"
key DPAD_CENTER; sleep 14; vpn_state; shot connected

log "== выбор сервера пультом"
key DPAD_DOWN DPAD_DOWN; shot focus_server
key DPAD_CENTER; sleep 4; shot server_sheet
key DPAD_DOWN DPAD_DOWN; shot server_sheet_focus
key BACK; sleep 2

log "== настройки и кабинет пультом"
key DPAD_DOWN DPAD_DOWN DPAD_DOWN; shot focus_nav
key DPAD_RIGHT DPAD_RIGHT DPAD_CENTER; sleep 3; shot settings
key DPAD_DOWN DPAD_DOWN; shot settings_focus
key BACK; sleep 2
key DPAD_DOWN DPAD_DOWN DPAD_DOWN DPAD_DOWN DPAD_DOWN DPAD_DOWN DPAD_LEFT DPAD_CENTER; sleep 4; shot cabinet

log "== отключение"
key BACK; sleep 2; shot home_again
key DPAD_CENTER; sleep 6; vpn_state; shot disconnected

adb logcat -d | grep -iE 'Pamir|pamirlink|LauncherManager|StartCore|FATAL|AndroidRuntime' | grep -vE 'I/chatty|systemui|SystemUI' | tail -150 > shots/logcat.txt
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
