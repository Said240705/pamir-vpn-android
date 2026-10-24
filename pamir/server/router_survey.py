#!/usr/bin/env python3
"""Только чтение: как ключи привязаны к устройствам — чтобы понять, заработает ли подписка Mognu на роутере.

Приложения Mognu шлют при получении подписки заголовок x-hwid (номер установки), панель по нему считает устройства.
Пакеты для роутеров (Podkop, PassWall, HomeProxy) этот заголовок не шлют. Скрипт показывает, что делает бот или
панель, если x-hwid нет, и какие лимиты устройств стоят. Ничего не меняет; адреса серверов, пароли и ключи не печатает.

    python3 router_survey.py > /root/router_survey.txt; wc -l /root/router_survey.txt
"""
import os
import re
import sqlite3
from pathlib import Path

BOT = Path(os.getenv("PAMIR_BOT_ROOT", "/root/YadrenoVPN"))
DB = Path(os.getenv("PAMIR_DB", BOT / "database" / "vpn_bot.db"))
LONG = re.compile(r"(?<![\w/.-])[A-Za-z0-9_\-:]{32,}(?![\w/.-])")
SECRET = re.compile(r"(token|secret|password|passwd|api_key|apikey|private)", re.I)
FILES = [p for p in sorted((BOT / "bot").rglob("*.py")) + sorted((BOT / "database").rglob("*.py"))
         if "venv" not in p.parts and ".bak" not in p.name]


def section(t):
    print(f"\n===== {t}")


def clean(s):
    s = LONG.sub("***", s)
    s = re.sub(r"https?://[^\s'\"]+", "<url>", s)
    return re.sub(r"\b\d{1,3}(\.\d{1,3}){3}\b", "*.*.*.*", s)


def func(path, name, limit=70):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, l in enumerate(lines):
        m = re.match(r"^(\s*)(async\s+)?def\s+" + re.escape(name) + r"\b", l)
        if not m:
            continue
        indent = len(m.group(1))
        out = [l]
        for l2 in lines[i + 1:]:
            if l2.strip() and len(l2) - len(l2.lstrip()) <= indent and not l2.strip().startswith((")", "]", "}")):
                break
            out.append(l2)
            if len(out) >= limit:
                out.append("    …")
                break
        print(f"\n-- {path.relative_to(BOT)}:{i + 1}")
        print("\n".join(clean(x) for x in out))
        return


conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row


def cols(table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


section("панели: тип и версия (без адресов и паролей)")
for r in conn.execute("SELECT * FROM servers"):
    d = dict(r)
    print({k: d.get(k) for k in ("id", "name", "is_active", "protocol", "panel_version") if k in d})
panels = BOT / "bot" / "services" / "panels"
if panels.exists():
    print("файлы panels/:", ", ".join(p.name for p in sorted(panels.iterdir()) if p.suffix == ".py"))

section("настройки про устройства, HWID, лимиты (значения секретов скрыты)")
for r in conn.execute("SELECT key, value FROM settings"):
    if re.search(r"hwid|device|limit|ip|sub", r["key"], re.I):
        v = "***" if SECRET.search(r["key"]) else clean(str(r["value"]))[:120]
        print(f"  {r['key']} = {v}")

section("лимиты устройств в тарифах и у ключей")
tc = cols("tariffs")
for r in conn.execute("SELECT * FROM tariffs ORDER BY id"):
    d = dict(r)
    print({k: d.get(k) for k in ("id", "name", "is_active", "max_ips", "duration_days", "system_type") if k in tc})
if "max_ips_override" in cols("vpn_keys"):
    print("ключей с личным лимитом:", conn.execute("SELECT COUNT(*) FROM vpn_keys WHERE max_ips_override IS NOT NULL").fetchone()[0])
try:
    print("доп. слоты устройств:", [tuple(r) for r in conn.execute("SELECT device_limit, COUNT(*) FROM key_device_slots GROUP BY 1")])
except sqlite3.Error as e:
    print("key_device_slots:", e)

section("таблицы про устройства и HWID")
for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
    if re.search(r"hwid|device", name, re.I):
        n = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(f"  {name}: {n} строк, колонки: {', '.join(cols(name))}")

section("где в коде бота упоминается hwid / x-hwid / лимит устройств")
hits = {}
for f in FILES:
    for i, l in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines()):
        if re.search(r"hwid|x-device|device_limit|hwidDeviceLimit|limitIp|limit_ip", l, re.I):
            hits.setdefault(f, []).append(i)
            if len(hits[f]) <= 12:
                print(f"  {f.relative_to(BOT)}:{i + 1}: {clean(l.strip())[:170]}")
for f, ls in hits.items():
    if len(ls) > 12:
        print(f"  … {f.relative_to(BOT)}: ещё {len(ls) - 12} строк")

section("функции, которые решают по hwid (что будет без заголовка)")
seen = set()
for f in FILES:
    text = f.read_text(encoding="utf-8", errors="replace")
    for name in re.findall(r"^\s*(?:async )?def (\w*(?:hwid|device|subscription_request|serve_sub|sub_handler)\w*)\(", text, re.M | re.I):
        if (f, name) not in seen:
            seen.add((f, name))
            func(f, name, 60)

section("кто отдаёт подписку: обработчики адресов /sub")
for f in FILES:
    for i, l in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines()):
        if re.search(r"""(add_get|add_route|@\w+\.get|router\.get)\(\s*['"][^'"]*sub""", l):
            print(f"  {f.relative_to(BOT)}:{i + 1}: {clean(l.strip())[:170]}")

section("панель 3x-ui на этом сервере: настройки HWID и подписки (только чтение /etc/x-ui/x-ui.db)")
XUI = Path(os.getenv("PAMIR_XUI_DB", "/etc/x-ui/x-ui.db"))
if not XUI.exists():
    print(f"  нет {XUI} — панель, видимо, на другом сервере")
else:
    x = sqlite3.connect(f"file:{XUI}?mode=ro", uri=True, timeout=5)
    x.row_factory = sqlite3.Row
    tables = [r[0] for r in x.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print("  таблицы:", ", ".join(tables))
    if "settings" in tables:
        for r in x.execute("SELECT key, value FROM settings ORDER BY key"):
            if re.search(r"hwid|device|sub|limit", r["key"], re.I):
                v = "***" if SECRET.search(r["key"]) else clean(str(r["value"]))[:120]
                print(f"  {r['key']} = {v}")
    for t in tables:
        if re.search(r"hwid|device|client", t, re.I):
            c = [r[1] for r in x.execute(f"PRAGMA table_info({t})")]
            print(f"  {t}: {x.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]} строк; колонки: {', '.join(c)}")
    if "clients" in tables:
        c = [r[1] for r in x.execute("PRAGMA table_info(clients)")]
        for col in ("limit_hwid", "limit_ip"):
            if col in c:
                print(f"  {col} по клиентам:", [tuple(r) for r in x.execute(f"SELECT {col}, COUNT(*) FROM clients GROUP BY 1 ORDER BY 2 DESC LIMIT 8")])
    if "client_hwids" in tables:
        hc = [r[1] for r in x.execute("PRAGMA table_info(client_hwids)")]
        key = next((k for k in ("client_email", "email", "client_id") if k in hc), None)
        if key:
            print("  устройств на клиента:", [tuple(r) for r in x.execute(
                f"SELECT n, COUNT(*) FROM (SELECT {key}, COUNT(*) AS n FROM client_hwids GROUP BY {key}) GROUP BY n ORDER BY n")])
        if "user_agent" in hc:
            print("  чем получают подписку (по User-Agent, без версий):")
            for r in x.execute("SELECT user_agent, COUNT(*) AS n FROM client_hwids GROUP BY user_agent ORDER BY n DESC LIMIT 15"):
                print("   ", re.sub(r"/[\w.\-]+", "", str(r[0] or "—"))[:60], r[1])
    x.close()
for d in ("/usr/local/x-ui", "/etc/x-ui"):
    if Path(d).exists():
        print(f"  {d}:", ", ".join(sorted(p.name for p in Path(d).iterdir() if not p.name.endswith((".db", ".db-wal", ".db-shm"))))[:300])
