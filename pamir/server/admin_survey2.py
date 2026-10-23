#!/usr/bin/env python3
"""Только чтение, часть 2: как старая админка зовёт бота — для новой админки Mognu VPN.

Печатает куски кода (функции целиком) и сводки из базы без личных данных. Всё, что похоже на токен,
пароль или ключ (длинные строки букв и цифр, значения переменных окружения), заменяется на ***.

    python3 admin_survey2.py > /root/admin_survey2.txt; wc -l /root/admin_survey2.txt
"""
import re
import sqlite3
from pathlib import Path

DB = "/root/YadrenoVPN/database/vpn_bot.db"
BACKEND = Path("/root/pamir-vpn-miniapp/backend")
BOT = Path("/root/YadrenoVPN")
LONG = re.compile(r"(?<![\w/.-])[A-Za-z0-9_\-:]{28,}(?![\w/.-])")
ASSIGN = re.compile(r"((?:token|secret|password|passwd|api_key|apikey)\w*\s*[=:]\s*)(['\"])[^'\"]{6,}\2", re.I)


def clean(line):
    line = ASSIGN.sub(lambda m: m.group(1) + m.group(2) + "***" + m.group(2), line)
    return LONG.sub("***", line)


def section(title):
    print(f"\n===== {title}")


def func(path, name, limit=80):
    """Функция целиком (до следующего def/@ на том же отступе), не больше limit строк."""
    if not path.exists():
        print(f"  нет {path}")
        return
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, l in enumerate(lines):
        m = re.match(r"^(\s*)(async\s+)?def\s+" + re.escape(name) + r"\b", l)
        if not m:
            continue
        indent = len(m.group(1))
        start = i
        while start > 0 and lines[start - 1].strip().startswith("@"):
            start -= 1
        out = lines[start:i + 1]
        for l2 in lines[i + 1:]:
            if l2.strip() and len(l2) - len(l2.lstrip()) <= indent and not l2.strip().startswith((")", "]", "}")):
                break
            out.append(l2)
            if len(out) >= limit:
                out.append("  …")
                break
        print(f"-- {path.name}:{start + 1}")
        print("\n".join(clean(x) for x in out))
        return
    print(f"  нет функции {name} в {path.name}")


def grep(path, pattern, ctx=0):
    files = sorted(path.rglob("*.py")) if path.is_dir() else [path]
    for f in files:
        if "venv" in f.parts or ".bak" in f.name:
            continue
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, l in enumerate(lines):
            if re.search(pattern, l):
                print(f"  {f.name}:{i + 1}: " + " ⏎ ".join(clean(x.strip()) for x in lines[i:i + 1 + ctx]))


ADMIN = BACKEND / "routers" / "admin_router.py"
section("admin_router.py: адреса и функции")
grep(ADMIN, r"^@router\.|^(async )?def |^[A-Z_]+ = ")
section("admin_router.py: функции, которые зовут бота (продление, удаление, онлайн, рассылка)")
src = ADMIN.read_text(encoding="utf-8", errors="replace") if ADMIN.exists() else ""
helpers = sorted(set(re.findall(r"^(?:async )?def (_\w+)\(", src, re.M)))
print("  вспомогательные:", " ".join(helpers))
for h in helpers:
    if re.search(r"bot|call|post|get|secret|header|request|admin|tg|telegram", h, re.I):
        func(ADMIN, h, 40)
for name in re.findall(r"^@router\.post\(\"(/keys/[^\"]+|/users/[^\"]+|/broadcast/send)\"\)\s*\n(?:async )?def (\w+)", src, re.M):
    func(ADMIN, name[1], 60)
section("auth.py: current_admin и issue_admin_token")
func(BACKEND / "auth.py", "current_admin", 40)
func(BACKEND / "auth.py", "issue_admin_token", 20)
section("бэкенд: имена переменных окружения (без значений)")
names = set()
for f in BACKEND.rglob("*.py"):
    if "venv" in f.parts or ".bak" in f.name:
        continue
    names |= set(re.findall(r"getenv\(\s*['\"]([A-Z0-9_]+)['\"]", f.read_text(encoding="utf-8", errors="replace")))
    names |= set(re.findall(r"environ(?:\.get)?[\[(]\s*['\"]([A-Z0-9_]+)['\"]", f.read_text(encoding="utf-8", errors="replace")))
print(" ", " ".join(sorted(n for n in names if not n.startswith("BOT_MINI_APP_"))))
section("бэкенд: где берётся токен бота и как вызывается Telegram API")
grep(BACKEND, r"api\.telegram\.org|BOT_TOKEN|bot_token")
section("db.py: get_db")
func(BACKEND / "db.py", "get_db", 25)

MINI = BOT / "bot" / "services" / "mini_app_api.py"
section("бот mini_app_api: проверка секрета и админские обработчики")
for n in ("_check_secret", "_admin_key_extend_handler", "_devices_handler", "_device_remove_handler", "_news_handler", "_admin_broadcast_handler"):
    func(MINI, n, 70)
section("бот: payment_completion — функции настройки ключа")
grep(BOT / "bot" / "services" / "payment_completion.py", r"^(async )?def ")
section("бот: trials.py и key_lifecycle.py — функции")
grep(BOT / "bot" / "services" / "trials.py", r"^(async )?def ")
grep(BOT / "bot" / "services" / "key_lifecycle.py", r"^(async )?def ")
section("бот: где функции базы (database/)")
d = BOT / "database"
print(" ", " ".join(sorted(str(p.relative_to(d)) for p in d.rglob("*.py") if "venv" not in p.parts))[:3000])
grep(d, r"^(async )?def (extend|update_key|set_key|get_key_details_for_user|delete_vpn_key|get_setting|set_setting|add_news|create_news)\w*\(")

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
section("база: fulfillment_status у оплаченных")
print(conn.execute("SELECT fulfillment_status, COUNT(*) FROM payments WHERE status='paid' GROUP BY 1").fetchall())
section("база: ключи без сервера или без клиента в панели (черновики)")
print(conn.execute("SELECT COUNT(*), SUM(server_id IS NULL), SUM(panel_email IS NULL OR panel_email='') FROM vpn_keys").fetchall())
section("база: location_health и server_health")
print(conn.execute("SELECT server_id, inbound_id, name, status, sort, checked_at FROM location_health ORDER BY sort").fetchall())
print(conn.execute("SELECT server_id, status, checked_at, up_since FROM server_health").fetchall())
section("база: безопасные настройки (значения)")
SAFE = ["referral_enabled", "coupon_auto_enabled", "coupon_auto_discount_percent", "coupon_auto_lifetime_days",
        "coupon_lapsed_enabled", "coupon_lapsed_discount_percent", "coupon_lapsed_lifetime_days", "coupon_lapsed_delay_days",
        "stars_enabled", "yookassa_qr_enabled", "crypto_enabled", "cryptobot_enabled", "cards_enabled",
        "payment_notifications_enabled", "notification_days", "expired_key_retention_days", "trial_usage_scope",
        "display_timezone", "update_notifications_enabled", "expired_key_deletion_notifications_enabled", "key_name_prefix",
        "broadcast_in_progress", "star_rub_rate"]
for k, v in conn.execute(f"SELECT key, value FROM settings WHERE key IN ({','.join('?' * len(SAFE))})", SAFE):
    print(f"  {k} = {clean(str(v))[:80]}")
section("база: support_threads — столбцы и статусы")
print([r[1] for r in conn.execute("PRAGMA table_info(support_threads)")])
try:
    print(conn.execute("SELECT status, COUNT(*) FROM support_threads GROUP BY 1").fetchall())
except sqlite3.Error as e:
    print(" ", e)
section("база: trial_activations — сколько и последние даты")
print(conn.execute("SELECT COUNT(*), MAX(activated_at) FROM trial_activations").fetchall())
