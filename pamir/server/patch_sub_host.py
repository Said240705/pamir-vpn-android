#!/usr/bin/env python3
"""Подписка по адресам входных серверов (Финляндия 31.77.6.71:2096, Германия 89.125.114.53:2097) отвечала 403.

Ретранслятор пересылает соединение как есть, поэтому в запросе остаётся адрес ретранслятора (Host: 31.77.6.71:2096),
а подписка панели отвечает только на свой адрес (subDomain = 78.17.158.230) — отсюда 403. nginx на 2096
(pamir-sub-proxy.conf) теперь всегда передаёт панели её адрес. Сами адреса и пути подписки не меняются.

Копия файла — в /root (.bak-mognu-host), nginx -t; при ошибке файл возвращается. Повторный запуск ничего не меняет.

    python3 patch_sub_host.py            показать, что изменится
    python3 patch_sub_host.py --apply    применить (nginx перечитывает настройки, соединения не рвутся)
"""
import os
import re
import shutil
import sqlite3
import subprocess
import sys

P = os.path.realpath("/etc/nginx/sites-enabled/pamir-sub-proxy.conf")
ro = sqlite3.connect("file:/etc/x-ui/x-ui.db?mode=ro", uri=True)
get = lambda k: (ro.execute("SELECT value FROM settings WHERE key = ?", (k,)).fetchone() or [""])[0]
DOMAIN, PORT = get("subDomain") or "78.17.158.230", get("subPort") or "2097"
ro.close()
HOST = f"{DOMAIN}:2096"
print(f"подписка панели: адрес {DOMAIN}, порт {PORT}; nginx будет передавать Host {HOST}")

s = open(P, encoding="utf-8").read()
# location-блоки, которые ведут на подписку панели
blocks = [m for m in re.finditer(r"location[^{]*\{[^{}]*proxy_pass\s+https?://(?:127\.0\.0\.1|localhost):" + re.escape(PORT) + r"[^{}]*\}", s)]
if not blocks:
    sys.exit(f"Не нашёл в {P} location с proxy_pass на порт {PORT} — ничего не меняю. Пришлите: grep -n proxy {P}")

new = s
for m in reversed(blocks):
    b = m.group(0)
    print("\nбыло:\n   " + "\n   ".join(l.strip() for l in b.splitlines() if "proxy" in l or "location" in l))
    nb = re.sub(r"\n[ \t]*proxy_set_header\s+Host\s+[^;]*;", "", b)
    indent = re.search(r"\n([ \t]+)proxy_pass", nb).group(1)
    nb = re.sub(r"(\n[ \t]+proxy_pass[^;]*;)", r"\1" + "\n" + indent + f"proxy_set_header Host {HOST};  # mognu: адрес панели и при входе через ретранслятор", nb, count=1)
    print("стало:\n   " + "\n   ".join(l.strip() for l in nb.splitlines() if "proxy" in l or "location" in l))
    new = new[:m.start()] + nb + new[m.end():]

if new == s:
    sys.exit("Менять нечего — уже так.")
if "--apply" not in sys.argv:
    sys.exit("\nЭто проверка. Применить: python3 patch_sub_host.py --apply")
bak = "/root/" + os.path.basename(P) + ".bak-mognu-host"   # не рядом: nginx читает все файлы из sites-enabled
shutil.copy2(P, bak)
open(P, "w", encoding="utf-8").write(new)
t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
if t.returncode != 0:
    shutil.copy2(bak, P)
    print("\n".join(l for l in t.stderr.splitlines() if "emerg" in l or "error" in l)[:600])
    sys.exit("nginx -t не прошёл — вернул файл, ничего не изменено.")
subprocess.run(["systemctl", "reload", "nginx"], check=True)
print("\nГотово. Копия:", bak)
