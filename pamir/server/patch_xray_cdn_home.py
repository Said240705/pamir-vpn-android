#!/usr/bin/env python3
"""Запасной кабинет и мини-приложение у подключённых к «Испании».

Мини-приложение и запасной адрес кабинета живут на российских CDN (CDNvideo *.trbcdn.net, Beget
*.begetcdn.cloud). Из Испании их узлы не отвечают, поэтому у человека с VPN «Испания» мини-приложение висело
серым экраном. Теперь Xray основного сервера отправляет такие запросы через выход «Домой» (ru-home →
Финляндия → российский сервер): по имени (если приложение передаёт имя) и по адресам узлов CDN.
Правила действуют только для входов «Испании»; остальное не трогается. Новые правила ставятся первыми.

Меняется шаблон Xray в панели (settings.xrayTemplateConfig). Копия базы — .bak-cdn-home. Повторный запуск
ничего не дублирует (и обновляет правила прежней версии).

    python3 patch_xray_cdn_home.py            показать
    python3 patch_xray_cdn_home.py --apply    применить (панель перезапускается — через nohup)
    python3 patch_xray_cdn_home.py --undo     убрать
"""
import json
import shutil
import sqlite3
import subprocess
import sys

DB = "/etc/x-ui/x-ui.db"
OUT = "ru-home"
MARK = "mognu-cdn-home"   # пометка правил (поле ruleTag), чтобы их узнавать и убирать
DOMAINS = ["domain:trbcdn.net", "domain:begetcdn.cloud"]
# узлы CDNvideo, которые видели в ответах DNS (Яндекс, Google, Cloudflare): сети /24
IPS = ["151.236.110.0/24", "151.236.94.0/24", "185.31.113.0/24"]

ro = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
row = ro.execute("SELECT value FROM settings WHERE key = 'xrayTemplateConfig'").fetchone()
SPAIN = [t for (t,) in ro.execute("SELECT tag FROM inbounds WHERE port IN (65535, 4443) AND tag != ''")]
ro.close()
if not SPAIN:
    sys.exit("Не нашёл входы «Испании» — ничего не меняю.")
cfg = json.loads(row[0])
if not any(o.get("tag") == OUT for o in cfg.get("outbounds", [])):
    sys.exit(f"Нет исходящего {OUT} («Домой») — ничего не меняю.")
rules = cfg.setdefault("routing", {}).setdefault("rules", [])
mine = [r for r in rules if r.get("ruleTag") == MARK]
NEW = [
    {"type": "field", "ruleTag": MARK, "inboundTag": SPAIN, "domain": DOMAINS, "outboundTag": OUT},
    {"type": "field", "ruleTag": MARK, "inboundTag": SPAIN, "ip": IPS, "outboundTag": OUT},
]
print("входы «Испании»:", ", ".join(SPAIN), f"| наших правил сейчас: {len(mine)}")
if "--undo" in sys.argv:
    rules[:] = [r for r in rules if r.get("ruleTag") != MARK]
elif "--apply" in sys.argv:
    rules[:] = NEW + [r for r in rules if r.get("ruleTag") != MARK]
else:
    print("будет:", json.dumps(NEW, ensure_ascii=False))
    sys.exit("Это проверка. Применить: nohup python3 patch_xray_cdn_home.py --apply > /root/cdn-home.log 2>&1 &")

shutil.copy2(DB, DB + ".bak-cdn-home")
subprocess.run(["systemctl", "stop", "x-ui"], check=True)
try:
    c = sqlite3.connect(DB)
    c.execute("UPDATE settings SET value = ? WHERE key = 'xrayTemplateConfig'", (json.dumps(cfg, ensure_ascii=False, indent=2),))
    c.commit()
    c.close()
finally:
    subprocess.run(["systemctl", "start", "x-ui"], check=True)
print("Готово:", "правила убраны" if "--undo" in sys.argv else "CDN для подключённых к «Испании» — через «Домой»")
