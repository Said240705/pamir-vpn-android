#!/usr/bin/env python3
"""«Домой» через входной сервер в Финляндии.

Исходящий ru-home (основной сервер → российский сервер:8443) мигал: запрос из Испании до российского сервера
доходит, а ответ обратно теряется (на российском сервере висят соединения в SYN-RECV, из Испании 2 из 40).
Из Финляндии до российского сервера путь чистый. Теперь ru-home идёт на Финляндию (31.77.6.71:8446), а она
пересылает на российский сервер:8443 (NAME=mognu-relay-home … setup_relay.sh). Ключи, Reality и всё остальное —
те же, меняется только адрес и порт.

Копия базы — /etc/x-ui/x-ui.db.bak-home-route. Повторный запуск ничего не меняет.

    python3 patch_home_route.py                       показать
    python3 patch_home_route.py --apply               через Финляндию (панель перезапускается — через nohup)
    python3 patch_home_route.py --apply --direct      вернуть напрямую на российский сервер
"""
import json
import shutil
import sqlite3
import subprocess
import sys

DB = "/etc/x-ui/x-ui.db"
TAG = "ru-home"
VIA = ("31.77.6.71", 8446)
DIRECT = ("185.198.152.202", 8443)
target = DIRECT if "--direct" in sys.argv else VIA

ro = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
row = ro.execute("SELECT value FROM settings WHERE key = 'xrayTemplateConfig'").fetchone()
ro.close()
if not row or not row[0].strip():
    sys.exit("Нет шаблона Xray в панели — ничего не меняю.")
cfg = json.loads(row[0])
out = next((o for o in cfg.get("outbounds", []) if o.get("tag") == TAG), None)
if not out:
    sys.exit(f"Нет исходящего {TAG} — ничего не меняю.")
st = out.get("settings") or {}
# старый формат: settings.vnext[0].address/port; новый (Xray 25+): settings.address/port
srv = (st.get("vnext") or [None])[0] or (st if "address" in st else None)
if not srv:
    sys.exit(f"У {TAG} не нашёл адрес сервера (ни vnext, ни address) — ничего не меняю. Ключи: {sorted(st)}")
cur = (srv.get("address"), srv.get("port"))
print(f"{TAG}: сейчас {cur[0]}:{cur[1]} → {target[0]}:{target[1]}")
if cur == target:
    sys.exit("Менять нечего — уже так.")
if "--apply" not in sys.argv:
    sys.exit("Это проверка. Применить: nohup python3 patch_home_route.py --apply > /root/home-route.log 2>&1 &")
srv["address"], srv["port"] = target
shutil.copy2(DB, DB + ".bak-home-route")
subprocess.run(["systemctl", "stop", "x-ui"], check=True)
try:
    c = sqlite3.connect(DB)
    c.execute("UPDATE settings SET value = ? WHERE key = 'xrayTemplateConfig'", (json.dumps(cfg, ensure_ascii=False, indent=2),))
    c.commit()
    c.close()
finally:
    subprocess.run(["systemctl", "start", "x-ui"], check=True)
print(f"Готово: {TAG} → {target[0]}:{target[1]}")
