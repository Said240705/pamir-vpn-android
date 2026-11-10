#!/usr/bin/env python3
"""Кабинет mognu.app для тех, кто подключён к VPN на основном сервере («Испания»).

Сайт живёт на основном сервере, а mognu.app указывает на входной сервер (Финляндия, 31.77.6.71), который
пересылает обратно на основной. У подключённых к «Испании» запрос делает лишний круг «основной → Финляндия →
основной» (~0.6 с и зависимость от Финляндии), а раньше, когда адрес был российским, не открывался вовсе.
Xray отправляет такие запросы прямо на свой nginx:
  • к mognu.app / www.mognu.app (по имени, sniffing) и к адресам входа (31.77.6.71, прежний 185.198.152.202)
    на 443 → свой внешний адрес:443
  • то же на 80 → свой внешний адрес:80
Правила действуют только для входов «Испании» (порты 65535 и 4443), остальные (в том числе «Домой» → ru-home)
не трогаются; новые правила ставятся первыми.

Меняется шаблон Xray в панели (settings.xrayTemplateConfig). Копия базы — рядом (.bak-mognu-local).
Повторный запуск ничего не дублирует (и обновляет правила прежней версии).

    python3 patch_xray_mognu_local.py            показать, что изменится
    python3 patch_xray_mognu_local.py --apply    применить (панель перезапускается — запускать через nohup)
    python3 patch_xray_mognu_local.py --undo     убрать эти правила
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys

DB = "/etc/x-ui/x-ui.db"
# входной сервер (Финляндия) и прежний российский — оба пересылают 443/80 на этот сервер без изменений
ENTRY = ["31.77.6.71", "185.198.152.202"]
# Свой внешний адрес, а не 127.0.0.1: Xray 26 не пускает подключения людей на внутренние адреса
# («proxy/freedom: blocked target: tcp:127.0.0.1:443, blackholing connection»). Подключение к своему
# внешнему адресу всё равно не выходит с сервера.
SELF_IP = os.environ.get("SELF_IP", "78.17.158.230")
OUT = [
    {"tag": "mognu-local-443", "protocol": "freedom", "settings": {"redirect": SELF_IP + ":443"}},
    {"tag": "mognu-local-80", "protocol": "freedom", "settings": {"redirect": SELF_IP + ":80"}},
]
RULES = [
    {"type": "field", "domain": ["full:mognu.app", "full:www.mognu.app"], "port": "443", "outboundTag": "mognu-local-443"},
    {"type": "field", "ip": ENTRY, "port": "443", "outboundTag": "mognu-local-443"},
    {"type": "field", "domain": ["full:mognu.app", "full:www.mognu.app"], "port": "80", "outboundTag": "mognu-local-80"},
    {"type": "field", "ip": ENTRY, "port": "80", "outboundTag": "mognu-local-80"},
]
TAGS = {o["tag"] for o in OUT}

ro = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
row = ro.execute("SELECT value FROM settings WHERE key = 'xrayTemplateConfig'").fetchone()
# только входы «Испании» на этом сервере: если панель раздаёт шаблон и узлам («Германия»), там правило не сработает
SPAIN_TAGS = [t for (t,) in ro.execute("SELECT tag FROM inbounds WHERE port IN (65535, 4443) AND tag != ''")]
ro.close()
if not SPAIN_TAGS:
    sys.exit("Не нашёл входы «Испании» (порты 65535 и 4443) — ничего не меняю.")
print("входы «Испании»:", ", ".join(SPAIN_TAGS))
for r in RULES:
    r["inboundTag"] = SPAIN_TAGS
if not row or not row[0].strip():
    sys.exit("В панели нет шаблона Xray (xrayTemplateConfig) — ничего не меняю.")
cfg = json.loads(row[0])
outs = cfg.setdefault("outbounds", [])
routing = cfg.setdefault("routing", {})
rules = routing.setdefault("rules", [])

has = [o for o in outs if o.get("tag") in TAGS]
mine = [r for r in rules if r.get("outboundTag") in TAGS]
print(f"сейчас: исходящих {len(outs)} (наших {len(has)}), правил {len(rules)} (наших {len(mine)})")
for r in rules[:6]:
    print("  правило:", {k: v for k, v in r.items() if k in ("inboundTag", "domain", "ip", "port", "outboundTag")})

if "--undo" in sys.argv:
    outs[:] = [o for o in outs if o.get("tag") not in TAGS]
    rules[:] = [r for r in rules if r.get("outboundTag") not in TAGS]
elif "--apply" in sys.argv:
    # исходящие прежней версии (на 127.0.0.1) заменяются
    outs[:] = [o for o in outs if o.get("tag") not in TAGS] + OUT
    # старая версия правил (без адреса Финляндии) заменяется новой
    rules[:] = [r for r in rules if r.get("outboundTag") not in TAGS]
    rules[:0] = RULES
else:
    print("Это проверка. Применить: --apply (через nohup, панель перезапустится)")
    sys.exit(0)

shutil.copy2(DB, DB + ".bak-mognu-local")
subprocess.run(["systemctl", "stop", "x-ui"], check=True)
try:
    c = sqlite3.connect(DB)
    c.execute("UPDATE settings SET value = ? WHERE key = 'xrayTemplateConfig'", (json.dumps(cfg, ensure_ascii=False, indent=2),))
    c.commit()
    c.close()
finally:
    subprocess.run(["systemctl", "start", "x-ui"], check=True)
print("Готово:", "правила убраны" if "--undo" in sys.argv else "mognu.app для подключённых к «Испании» — напрямую")
