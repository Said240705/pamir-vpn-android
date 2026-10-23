#!/usr/bin/env python3
"""Только чтение: что есть в бэкенде админки и в базе бота — для новой админки Mognu VPN.

Печатает структуру таблиц, адреса админки и бота, имена функций работы с ключами.
Никаких значений из базы (кроме тарифов и групп серверов) и никаких секретов: у таблиц settings и servers —
только названия столбцов и ключей.

    python3 admin_survey.py > /root/admin_survey.txt; wc -l /root/admin_survey.txt
"""
import re
import sqlite3
from pathlib import Path

DB = "/root/YadrenoVPN/database/vpn_bot.db"
BACKEND = Path("/root/pamir-vpn-miniapp/backend")
BOT = Path("/root/YadrenoVPN")
TABLES = [
    "users", "vpn_keys", "payments", "servers", "server_groups", "tariffs", "tariff_groups", "settings", "news",
    "key_device_slots", "balance_operations", "app_notifications", "location_health", "server_health",
    "trial_offers", "trial_activations", "key_operation_log", "traffic_history", "subscription_bindings",
    "push_subscriptions", "notification_log", "user_ui_texts", "pages", "pamir_app_installs",
]
SECRETISH = re.compile(r"pass|secret|token|key|cookie|auth|login|url|host|ip|port|path", re.I)


def section(title):
    print(f"\n===== {title}")


conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

section("таблицы (все)")
print(" ".join(sorted(names)))

for t in TABLES:
    if t not in names:
        continue
    section(f"таблица {t}: {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]} строк")
    for c in conn.execute(f"PRAGMA table_info({t})"):
        print(f"  {c['name']} {c['type']}{' NOT NULL' if c['notnull'] else ''}{' = ' + str(c['dflt_value']) if c['dflt_value'] is not None else ''}")

section("settings: только ключи")
if "settings" in names:
    cols = [c["name"] for c in conn.execute("PRAGMA table_info(settings)")]
    k = "key" if "key" in cols else cols[0]
    print(" ".join(r[0] for r in conn.execute(f"SELECT {k} FROM settings ORDER BY 1")))

for t in ("tariffs", "tariff_groups", "server_groups"):
    if t not in names:
        continue
    section(f"{t}: строки (без столбцов, похожих на секреты)")
    cols = [c["name"] for c in conn.execute(f"PRAGMA table_info({t})") if not SECRETISH.search(c["name"]) or c["name"] in ("is_active",)]
    for r in conn.execute(f"SELECT {', '.join(cols)} FROM {t} LIMIT 40"):
        print("  " + " | ".join(f"{c}={r[c]}" for c in cols))

section("vpn_keys: статусы")
for col in ("status", "state", "provisioning_status"):
    try:
        print(col, [tuple(r) for r in conn.execute(f"SELECT {col}, COUNT(*) FROM vpn_keys GROUP BY 1")])
    except sqlite3.Error:
        pass
section("payments: статусы и типы")
print([tuple(r) for r in conn.execute("SELECT status, payment_type, purpose, COUNT(*) FROM payments GROUP BY 1,2,3")])


def routes(path, pattern):
    if not path.exists():
        print(f"  нет {path}")
        return
    for f in sorted(path.rglob("*.py")) if path.is_dir() else [path]:
        if "venv" in f.parts or ".bak" in f.name:
            continue
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        hits = [(i, l) for i, l in enumerate(lines) if re.search(pattern, l)]
        if not hits:
            continue
        print(f"-- {f}")
        for i, l in hits:
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            print(f"  {l.strip()}   {nxt[:150] if l.strip().startswith('@') else ''}")


section("бэкенд кабинета: адреса /admin")
routes(BACKEND / "routers", r"@router\.(get|post|put|patch|delete)\(\"/admin")
section("бэкенд кабинета: prefix роутеров и подключение")
routes(BACKEND / "routers", r"APIRouter\(")
routes(BACKEND / "main.py", r"include_router|^from routers|^import")
section("бэкенд: auth.current_admin и вызовы бота")
routes(BACKEND / "auth.py", r"^(async )?def |ADMIN")
routes(BACKEND, r"mini-app-api|BOT_API|bot_api|X-Mini-App|_bot_post|async def _call_bot|def _bot")

section("бот: адреса mini-app-api")
routes(BOT / "bot" / "services" / "mini_app_api.py", r"add_(get|post)\(")
section("бот: функции базы (ключи, оплаты, пользователи, серверы, тарифы, настройки)")
req = BOT / "database" / "requests.py"
if req.exists():
    src = req.read_text(encoding="utf-8", errors="replace")
    fns = re.findall(r"^(?:async )?def (\w+)\(([^)]*)\)", src, re.M)
    for n, a in fns:
        if re.search(r"key|server|tariff|setting|balance|trial|user|news|ban|extend|days|group", n):
            print(f"  {n}({' '.join(a.split())[:120]})")
else:
    for d in (BOT / "database").glob("*.py"):
        print("  файл", d.name)
section("бот: сервисы")
print(" ".join(sorted(p.name for p in (BOT / "bot" / "services").glob("*.py"))))
section("бот: панели 3x-ui (vpn_api) — публичные методы клиента")
routes(BOT / "bot" / "services" / "vpn_api.py", r"^\s+async def [a-z]\w*\(|^async def [a-z]\w*\(|^def [a-z]\w*\(")
