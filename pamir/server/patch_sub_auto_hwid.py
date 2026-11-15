#!/usr/bin/env python3
"""Подписка без HWID: nginx подставляет постоянный HWID по названию приложения.

Когда у ключа есть лимит устройств, панель отказывает любому запросу подписки без HWID — человек видит
«все места заняты», даже если места свободны и устройства отключены. Так ведут себя Karing (HWID не шлёт вовсе),
OneXray с выключенным переключателем HWID и другие. Теперь, если приложение HWID не прислало, nginx передаёт
панели «auto-<приложение>» (auto-Karing, auto-OneXray …): приложение занимает одно место, видно в «Устройствах»
и отключается как обычное. Если HWID прислан — передаётся как есть. Запросы без названия приложения (сканеры)
и из браузера (ссылку открыли посмотреть) не трогаются.

Уступка: два телефона с одним приложением без HWID на одном ключе делят одно место.

Копия файла — /root/pamir-sub-proxy.conf.bak-autohwid; nginx -t — при ошибке файл возвращается.

    python3 patch_sub_auto_hwid.py            показать
    python3 patch_sub_auto_hwid.py --apply    применить (nginx reload, соединения не рвутся)
    python3 patch_sub_auto_hwid.py --undo     убрать
"""
import os
import shutil
import subprocess
import sys

P = os.path.realpath("/etc/nginx/sites-enabled/pamir-sub-proxy.conf")
BAK = "/root/pamir-sub-proxy.conf.bak-autohwid"   # не рядом: nginx читает все файлы из sites-enabled
MAP = ('# mognu: нет HWID — постоянный HWID по названию приложения (patch_sub_auto_hwid.py)\n'
       'map "$http_x_hwid|$http_user_agent" $mognu_sub_hwid {\n'
       '    "~^\\|(?!Mozilla/)(?<mognu_app>[A-Za-z][A-Za-z0-9._-]{1,30})"  "auto-$mognu_app";  # браузер не занимает место\n'
       '    default  $http_x_hwid;\n'
       '}\n')
ANCHOR = "        proxy_pass https://127.0.0.1:2097;\n"
HDR = "        proxy_set_header x-hwid $mognu_sub_hwid;  # mognu: patch_sub_auto_hwid.py\n"

s = open(P, encoding="utf-8").read()
if "--undo" in sys.argv:
    new = s.replace(MAP, "").replace(HDR, "")
    if new == s:
        sys.exit("Подстановки нет — убирать нечего.")
else:
    if MAP in s and HDR in s:
        sys.exit("Уже стоит — менять нечего.")
    if s.count(ANCHOR) != 1:
        sys.exit("Не нашёл proxy_pass на 2097 в ожидаемом виде — ничего не меняю.")
    if "x-hwid" in s.replace(MAP, "").replace(HDR, "").lower().replace("$http_x_hwid", ""):
        sys.exit("В файле уже есть своя обработка x-hwid — ничего не меняю, пришлите файл.")
    first = s.find("server {")
    new = s
    if MAP not in new:
        new = new[:first] + MAP + new[first:]
    if HDR not in new:
        new = new.replace(ANCHOR, ANCHOR + HDR)
    print("будет:\n" + MAP + "  и в location /:\n" + HDR)
    if "--apply" not in sys.argv:
        sys.exit("Это проверка. Применить: python3 patch_sub_auto_hwid.py --apply")
shutil.copy2(P, BAK)
open(P, "w", encoding="utf-8").write(new)
t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
if t.returncode != 0:
    shutil.copy2(BAK, P)
    print("\n".join(l for l in t.stderr.splitlines() if "emerg" in l or "error" in l)[:600])
    sys.exit("nginx -t не прошёл — вернул файл, ничего не изменено. Пришлите строки выше.")
subprocess.run(["systemctl", "reload", "nginx"], check=True)
print("Готово:", "подстановка убрана" if "--undo" in sys.argv else "запросы без HWID получают auto-<приложение>", "| копия:", BAK)
