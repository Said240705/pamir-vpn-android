#!/usr/bin/env python3
"""Лимит устройств по умолчанию: 1 → 2.

С лимитом 1 почти все жалобы «все места заняты» — телефон и второе приложение, старый Incy и новый OneXray.
Скрипт поднимает лимит до 2:
1. в боте — у действующих тарифов с лимитом 1 (tariffs.max_ips), чтобы новые ключи и продления получали 2;
2. в панели 3X-UI — у клиентов с лимитом 1: limit_hwid (устройства) и limit_ip (одновременные адреса), бот
   передаёт в панель одно и то же число в оба поля.
Ключи с другим лимитом (0, «Весь дом», докупленные места, тестовые), неактивные тарифы и личные лимиты ключей
(vpn_keys.max_ips_override) не трогаются — личные только показываются.

Копии баз — *.bak-limit2. Панель на время записи останавливается (через nohup), всё в одной транзакции на базу.
Повторный запуск ничего не меняет.

    python3 raise_device_limit.py            показать
    python3 raise_device_limit.py --apply    применить (через nohup — панель перезапускается)
"""
import shutil
import sqlite3
import subprocess
import sys

BOT = "/root/YadrenoVPN/database/vpn_bot.db"
XUI = "/etc/x-ui/x-ui.db"
OLD, NEW = 1, 2
APPLY = "--apply" in sys.argv

b = sqlite3.connect(f"file:{BOT}?mode=ro", uri=True)
b.row_factory = sqlite3.Row
tcols = [r[1] for r in b.execute("pragma table_info(tariffs)")]
tariffs = b.execute("SELECT id, name FROM tariffs WHERE max_ips = ? AND is_active = 1", (OLD,)).fetchall()
overrides = b.execute("SELECT count(*) FROM vpn_keys WHERE max_ips_override = ? AND expires_at > datetime('now')", (OLD,)).fetchone()[0]
texts = []
for col in ("description", "name", "title"):
    if col in tcols:
        texts += [f"тариф {r['id']} ({col}): {r[col]}" for r in b.execute(f"SELECT id, {col} FROM tariffs WHERE is_active = 1 AND {col} LIKE '%устройств%'")]
b.close()

x = sqlite3.connect(f"file:{XUI}?mode=ro", uri=True)
xcols = [r[1] for r in x.execute("pragma table_info(clients)")]
if "limit_hwid" not in xcols:
    sys.exit(f"В панели нет clients.limit_hwid ({xcols}) — ничего не меняю.")
has_ip = "limit_ip" in xcols
n_hwid = x.execute("SELECT count(*) FROM clients WHERE limit_hwid = ?", (OLD,)).fetchone()[0]
n_ip = x.execute("SELECT count(*) FROM clients WHERE limit_ip = ?", (OLD,)).fetchone()[0] if has_ip else 0
x.close()

print(f"бот: тарифы с лимитом {OLD} → {NEW}: {', '.join(f'{r[0]} «{r[1]}»' for r in tariffs) or 'нет'}")
print(f"панель: клиентов с лимитом устройств {OLD} → {NEW}: {n_hwid}" + (f"; с лимитом адресов {OLD} → {NEW}: {n_ip}" if has_ip else ""))
if overrides:
    print(f"не трогаю: у {overrides} действующих ключей личный лимит {OLD} (max_ips_override) — при продлении у них останется {OLD}")
for t in texts:
    print("проверьте текст:", t)
if not tariffs and not n_hwid and not n_ip:
    sys.exit("Менять нечего.")
if not APPLY:
    sys.exit("Это проверка. Применить: nohup python3 raise_device_limit.py --apply > /root/limit2.log 2>&1 &")

shutil.copy2(BOT, BOT + ".bak-limit2")
c = sqlite3.connect(BOT)
with c:
    c.executemany("UPDATE tariffs SET max_ips = ? WHERE id = ? AND max_ips = ?", [(NEW, r[0], OLD) for r in tariffs])
c.close()

shutil.copy2(XUI, XUI + ".bak-limit2")
subprocess.run(["systemctl", "stop", "x-ui"], check=True)
try:
    c = sqlite3.connect(XUI)
    with c:
        c.execute("UPDATE clients SET limit_hwid = ? WHERE limit_hwid = ?", (NEW, OLD))
        if has_ip:
            c.execute("UPDATE clients SET limit_ip = ? WHERE limit_ip = ?", (NEW, OLD))
    c.close()
finally:
    subprocess.run(["systemctl", "start", "x-ui"], check=True)
print(f"Готово: тарифов {len(tariffs)}, клиентов панели {n_hwid} — лимит {NEW}. Копии: {BOT}.bak-limit2, {XUI}.bak-limit2")
