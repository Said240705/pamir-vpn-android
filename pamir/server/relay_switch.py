#!/usr/bin/env python3
"""Адрес «Испании» в подписке: напрямую или через ретранслятор (setup_relay.sh на другом сервере).

Во входах «Испания-1» (65535) и «Испания-2» (4443) адрес, который получают приложения, задан в
External proxy (stream_settings.externalProxy[].dest). Скрипт меняет только это поле — ключи, порты,
Reality и всё остальное не трогает. Перед изменением — копия базы панели. Порт остаётся тем же:
ретранслятор слушает те же порты.

    python3 relay_switch.py                  показать, какой адрес сейчас
    python3 relay_switch.py --to 89.125.114.53   поставить адрес ретранслятора и перезапустить панель
    python3 relay_switch.py --to 78.17.158.230   вернуть прямой адрес
    python3 relay_switch.py --home --to 31.77.6.71   то же для входа «Домой» (8445; External proxy создаётся
                                                 по образцу «Испании-1», если его нет). На ретрансляторе
                                                 нужна пересылка 8445:8445 (MAP в setup_relay.sh)

Приложения получат новый адрес при следующем обновлении подписки.
"""
import datetime
import json
import shutil
import sqlite3
import subprocess
import sys

DB = "/etc/x-ui/x-ui.db"
PORTS = (8445,) if "--home" in sys.argv else (65535, 4443)


def current(c):
    out = []
    for iid, remark, port, ss in c.execute("SELECT id, remark, port, stream_settings FROM inbounds WHERE port IN (%s)" % ",".join("?" * len(PORTS)), PORTS):
        s = json.loads(ss or "{}")
        out.append((iid, remark.strip(), port, [p.get("dest") for p in s.get("externalProxy") or []], s))
    return out


ro = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
rows = current(ro)
ro.close()
for iid, remark, port, dests, _ in rows:
    print(f"вход {iid} «{remark}» :{port} → {', '.join(map(str, dests)) or 'нет External proxy'}")
if "--to" not in sys.argv:
    sys.exit(0)

new = sys.argv[sys.argv.index("--to") + 1].strip()
if not new or " " in new:
    sys.exit("Укажите адрес: --to 1.2.3.4")
if not rows:
    sys.exit("Нет таких входов — ничего не меняю.")
if any(not r[3] for r in rows) and "--home" not in sys.argv:
    sys.exit("У входов нет External proxy — ничего не меняю.")

bak = f"{DB}.bak-relay-{datetime.datetime.now():%Y%m%d-%H%M%S}"
subprocess.run(["systemctl", "stop", "x-ui"], check=True)
try:
    shutil.copy2(DB, bak)
    c = sqlite3.connect(DB)
    for iid, remark, port, dests, s in current(c):
        if not s.get("externalProxy"):  # «Домой»: создать по образцу «Испании-1»
            tpl = json.loads(c.execute("SELECT stream_settings FROM inbounds WHERE port = 65535").fetchone()[0]).get("externalProxy") or [{}]
            s["externalProxy"] = [dict(tpl[0], dest=new, port=port)]
        for p in s.get("externalProxy") or []:
            p["dest"] = new
        c.execute("UPDATE inbounds SET stream_settings = ? WHERE id = ?", (json.dumps(s, ensure_ascii=False, indent=2), iid))
    c.commit()
    c.close()
finally:
    subprocess.run(["systemctl", "start", "x-ui"], check=True)
print(f"Готово: адрес {'«Домой»' if '--home' in sys.argv else '«Испании»'} теперь {new}. Копия базы: {bak}")
print("Откат: python3 relay_switch.py --to 78.17.158.230")
