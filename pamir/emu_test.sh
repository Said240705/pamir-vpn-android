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
for m in re.finditer(r'<node [^>]*?(?:text|content-desc)="([^"]*)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',s):
    if re.search(sys.argv[1],m.group(1),re.I):
        x1,y1,x2,y2=map(int,m.groups()[1:]); print((x1+x2)//2,(y1+y2)//2); break
PY
); if [ -n "$XY" ]; then log "тап [$1] -> $XY"; adb shell input tap $XY; else log "не нашёл на экране: [$1]"; fi; }
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
adb shell "am start -a android.intent.action.VIEW -d 'pamirvpn://install-sub?url=$ENC'" >/dev/null
sleep 20; shot imported

log "== Испания"
tap_text 'Испания'; sleep 2
toggle; sleep 10; vpn_state; shot connected_spain
check_ip ip_spain
toggle; sleep 4

log "== LTE Обход"
tap_text 'LTE Обход$|LTE Обход[^ 2]'; sleep 2
toggle; sleep 12; vpn_state; shot connected_lte
check_ip ip_lte
toggle; sleep 3

adb logcat -d | grep -iE 'xray|v2ray|ang|failed|error' | grep -v 'I/chatty' | tail -120 > shots/logcat.txt
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
