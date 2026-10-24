#!/usr/bin/env python3
"""Только чтение: как бот создаёт ключ при покупке и как устроены локации в панели — для тарифа «На весь дом».

Нужно понять: (1) где в боте покупка тарифа превращается в ключ, чтобы «Дом» создавал два ключа; (2) какие inbound'ы
и узлы (локации) в 3x-ui и с какими настройками транспорта, чтобы собирать прямые ссылки vless:// для роутера.
Ничего не меняет. Не печатает адреса, пароли, UUID, ключи Reality (privateKey/publicKey/shortIds) и почты.

    python3 home_survey.py > /root/home_survey.txt; wc -l /root/home_survey.txt
"""
import json
import os
import re
import sqlite3
from pathlib import Path

BOT = Path(os.getenv("PAMIR_BOT_ROOT", "/root/YadrenoVPN"))
DB = Path(os.getenv("PAMIR_DB", BOT / "database" / "vpn_bot.db"))
XUI = Path(os.getenv("PAMIR_XUI_DB", "/etc/x-ui/x-ui.db"))
LONG = re.compile(r"(?<![\w/.-])[A-Za-z0-9_\-:+=]{28,}(?![\w/.-])")
IP = re.compile(r"\b\d{1,3}(\.\d{1,3}){3}\b")
FILES = [p for p in sorted((BOT / "bot").rglob("*.py")) + sorted((BOT / "database").rglob("*.py"))
         if "venv" not in p.parts and ".bak" not in p.name]


def section(t):
    print(f"\n===== {t}")


def _mask(m):
    w = m.group(0)
    return w if re.fullmatch(r"[a-z_]+", w) else "***"   # имена функций (snake_case) оставляем, остальное длинное — прячем


def clean(s):
    s = LONG.sub(_mask, str(s))
    s = re.sub(r"https?://[^\s'\"]+", "<url>", s)
    return IP.sub("*.*.*.*", s)


def func(path, name, limit=80):
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
        return True
    return False


def defs(path):
    if path.exists():
        names = re.findall(r"^(?:async )?def (\w+)\(", path.read_text(encoding="utf-8", errors="replace"), re.M)
        print(f"  {path.relative_to(BOT)}: {', '.join(names)}")


bot = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
bot.row_factory = sqlite3.Row


def cols(c, t):
    return [r[1] for r in c.execute(f"PRAGMA table_info({t})")]


section("тарифы и группы")
print("  tariffs:", ", ".join(cols(bot, "tariffs")))
for r in bot.execute("SELECT * FROM tariffs ORDER BY id"):
    d = dict(r)
    print("  ", {k: d.get(k) for k in ("id", "name", "group_id", "is_active", "duration_days", "price_minor", "max_ips", "traffic_limit_gb", "system_type", "display_order") if k in d})
for t in ("tariff_groups", "trial_offers"):
    try:
        print(f"  {t}:", [dict(r) for r in bot.execute(f"SELECT * FROM {t}")])
    except sqlite3.Error as e:
        print(f"  {t}: {e}")
print("  vpn_keys:", ", ".join(cols(bot, "vpn_keys")))
print("  payments:", ", ".join(cols(bot, "payments")))
print("  ключей на пользователя:", [tuple(r) for r in bot.execute(
    "SELECT n, COUNT(*) FROM (SELECT user_id, COUNT(*) AS n FROM vpn_keys GROUP BY user_id) GROUP BY n ORDER BY n")])
print("  ключей по серверам:", [tuple(r) for r in bot.execute("SELECT server_id, COUNT(*) FROM vpn_keys GROUP BY 1")])

section("функции бота вокруг покупки и создания ключа")
for rel in ("bot/services/new_key_setup.py", "bot/services/payment_fulfillment.py", "bot/services/key_plans.py",
            "bot/services/vpn_api.py", "bot/services/subscription_composition.py"):
    defs(BOT / rel)
for rel, names in (("bot/services/payment_fulfillment.py", ("_apply_purpose", "_sync_renewed_key")),
                   ("bot/services/new_key_setup.py", ("provision_new_key", "_provision_resolved_new_key", "_load_setup_context")),
                   ("database/db_payment_intents.py", ("fulfill_key_purchase_once",)),
                   ("bot/services/vpn_api.py", ("get_client_inbound_descriptors", "get_client_external_links", "provision_client_on_server")),
                   ("bot/services/mini_app_api.py", ("_purchase_handler",))):
    p = BOT / rel
    if p.exists():
        for n in names:
            func(p, n, 70)

section("где цена/тариф выбираются для покупки (purpose key_purchase)")
for f in FILES:
    for i, l in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines()):
        if re.search(r"purpose\s*==\s*['\"]key_purchase|'key_purchase'\s*:|def \w*purchase\w*\(", l):
            print(f"  {f.relative_to(BOT)}:{i + 1}: {clean(l.strip())[:160]}")

section("панель 3x-ui: inbound'ы (локации), без ключей и адресов")
if not XUI.exists():
    print(f"  нет {XUI}")
else:
    x = sqlite3.connect(f"file:{XUI}?mode=ro", uri=True, timeout=5)
    x.row_factory = sqlite3.Row
    tables = [r[0] for r in x.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    print("  inbounds:", ", ".join(cols(x, "inbounds")))
    for r in x.execute("SELECT * FROM inbounds ORDER BY id"):
        d = dict(r)
        try:
            ss = json.loads(d.get("stream_settings") or "{}")
        except ValueError:
            ss = {}
        sec = ss.get("security")
        rs = ss.get("realitySettings") or {}
        tls = ss.get("tlsSettings") or {}
        info = {
            "id": d.get("id"), "remark": clean(d.get("remark")), "enable": d.get("enable"), "protocol": d.get("protocol"),
            "port": d.get("port"), "tag": clean(d.get("tag")), "node": d.get("node_id", d.get("node_guid")),
            "network": ss.get("network"), "security": sec,
            "reality": {"sni_count": len(rs.get("serverNames") or []), "has_pbk": bool((rs.get("settings") or {}).get("publicKey")),
                        "fp": (rs.get("settings") or {}).get("fingerprint"), "spx": bool((rs.get("settings") or {}).get("spiderX"))} if sec == "reality" else None,
            "tls": {"sni": bool(tls.get("serverName")), "alpn": tls.get("alpn")} if sec == "tls" else None,
            "transport": {k: bool(v) for k, v in ss.items() if k.endswith("Settings") and k not in ("realitySettings", "tlsSettings")},
        }
        try:
            st = json.loads(d.get("settings") or "{}")
            info["flows"] = sorted({c.get("flow") or "" for c in st.get("clients") or []})
            info["clients_in_json"] = len(st.get("clients") or [])
        except ValueError:
            pass
        print("  ", info)
    for t in ("nodes", "hosts", "sub_balancers", "client_inbounds"):
        if t in tables:
            print(f"  {t}: {x.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]} строк; колонки: {', '.join(cols(x, t))}")
    if "nodes" in tables:
        safe = [c for c in cols(x, "nodes") if not re.search(r"addr|host|ip|url|token|secret|pass|key|cert", c, re.I)]
        for r in x.execute(f"SELECT {', '.join(safe)} FROM nodes"):
            print("    node:", {k: clean(v) for k, v in dict(r).items()})
    if "hosts" in tables:
        safe = [c for c in cols(x, "hosts") if not re.search(r"addr|host$|ip|url|token|secret|pass|key|cert|sni|path", c, re.I)]
        for r in x.execute(f"SELECT {', '.join(safe)} FROM hosts LIMIT 20"):
            print("    host:", {k: clean(v) for k, v in dict(r).items()})
    if "client_inbounds" in tables:
        print("  inbound'ов на клиента:", [tuple(r) for r in x.execute(
            "SELECT n, COUNT(*) FROM (SELECT client_id, COUNT(*) AS n FROM client_inbounds GROUP BY client_id) GROUP BY n")])
    print("  API панели для ссылок (есть ли в коде бота):")
    for f in FILES:
        for i, l in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines()):
            if re.search(r"vless://|/panel/api/\w+/(links|getClientLinks|sub)", l):
                print(f"    {f.relative_to(BOT)}:{i + 1}: {clean(l.strip())[:150]}")
