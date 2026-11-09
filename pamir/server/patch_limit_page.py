#!/usr/bin/env python3
"""Страница «лимит устройств» в подписке (nginx, блок @pamir_limit в pamir-sub-proxy.conf): Pamir → Mognu.

Тексты там лежат в base64 (название, объявление и заглушка-«сервер» с подписью). Скрипт раскодирует их,
меняет «Pamir VPN» на «Mognu VPN», кодирует обратно и показывает, что было и что стало. Копия файла рядом
(.bak-mognu), nginx -t — при ошибке файл возвращается. Повторный запуск ничего не меняет.

    python3 patch_limit_page.py          показать тексты и применить
"""
import base64
import os
import re
import shutil
import subprocess
import sys
import urllib.parse

P = os.path.realpath("/etc/nginx/sites-enabled/pamir-sub-proxy.conf")
s = open(P, encoding="utf-8").read()
a = s.find("location @pamir_limit")
if a < 0:
    sys.exit("Блока @pamir_limit нет — ничего не меняю.")
b = s.find("\n    }", a)
block = s[a:b]


def fix(text):
    return text.replace("Pamir VPN", "Mognu VPN").replace("Pamir", "Mognu")


def recode(raw):
    """base64-строка → та же строка с Mognu вместо Pamir (или без изменений)."""
    try:
        dec = base64.b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
    except Exception:
        return raw
    if dec.startswith("vless://") and "#" in dec:
        # заглушка-«сервер»: подпись после # в URL-кодировке
        head, tag = dec.split("#", 1)
        new = head + "#" + urllib.parse.quote(fix(urllib.parse.unquote(tag)), safe="")
    else:
        new = "\n".join(fix(line) if not line.startswith("vless://") else line for line in dec.split("\n"))
        if dec.startswith("vless://"):
            new = "\n".join(recode_line(line) for line in dec.split("\n"))
    if new == dec:
        return raw
    print("было: ", urllib.parse.unquote(dec)[:110].replace("\n", " / "))
    print("стало:", urllib.parse.unquote(new)[:110].replace("\n", " / "))
    return base64.b64encode(new.encode("utf-8")).decode("ascii")


def recode_line(line):
    if "#" not in line:
        return line
    head, tag = line.split("#", 1)
    return head + "#" + urllib.parse.quote(fix(urllib.parse.unquote(tag)), safe="")


new_block = re.sub(r'base64:([A-Za-z0-9+/=]+)', lambda m: "base64:" + recode(m.group(1)), block)
new_block = re.sub(r'return 200 "([A-Za-z0-9+/=]+)"', lambda m: 'return 200 "' + recode(m.group(1)) + '"', new_block)
if new_block == block:
    sys.exit("Менять нечего — уже Mognu.")
bak = P + ".bak-mognu"
shutil.copy2(P, bak)
open(P, "w", encoding="utf-8").write(s[:a] + new_block + s[b:])
if subprocess.run(["nginx", "-t"], capture_output=True).returncode != 0:
    shutil.copy2(bak, P)
    sys.exit("nginx -t не прошёл — вернул файл, ничего не изменено.")
subprocess.run(["systemctl", "reload", "nginx"], check=True)
print("Готово. Копия:", bak)
