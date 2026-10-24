#!/usr/bin/env python3
"""Проверка на тестовом ключе: отдаёт ли панель подписку роутеру — то есть без заголовка x-hwid.

Берёт ключ тестового пользователя (только test@pamirlink.ru), запрашивает его подписку прямо у панели на этом сервере
так, как это делают пакеты для роутеров (Podkop/PassWall/HomeProxy): без x-hwid, с их User-Agent. Печатает только код
ответа, сколько серверов в подписке и каких типов, и появились ли у ключа новые «устройства». Ссылку подписки, sub_id,
адреса и сами ключи не печатает. Ничего не меняет в базах; если панель засчитает запрос как устройство — его можно
убрать в админке кнопкой «Сбросить устройства».

    python3 router_subtest.py
"""
import base64
import os
import re
import sqlite3
import ssl
import sys
import urllib.error
import urllib.request

BOT_DB = os.getenv("PAMIR_DB", "/root/YadrenoVPN/database/vpn_bot.db")
XUI_DB = os.getenv("PAMIR_XUI_DB", "/etc/x-ui/x-ui.db")
TEST_EMAIL = "test@pamirlink.ru"
AGENTS = ["sing-box 1.10.7 (OpenWrt)", "PassWall/4.x (OpenWrt)", "curl/8.5.0"]


def ro(path):
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    return c


bot = ro(BOT_DB)
user = bot.execute("SELECT id FROM users WHERE lower(email) = ?", (TEST_EMAIL,)).fetchone()
if not user:
    sys.exit(f"Нет пользователя {TEST_EMAIL} — проверку не делаю.")
keys = bot.execute("""SELECT id, sub_id, panel_email FROM vpn_keys WHERE user_id = ? AND expires_at > datetime('now')
                      AND sub_id IS NOT NULL ORDER BY id DESC""", (user["id"],)).fetchall()
if not keys:
    sys.exit("У тестового пользователя нет активного ключа с подпиской.")
key = keys[0]
print(f"Тестовый пользователь ID {user['id']}, ключ ID {key['id']}")

xui = ro(XUI_DB)
st = {r["key"]: r["value"] for r in xui.execute("SELECT key, value FROM settings WHERE key IN ('subPort','subPath','subListen','subCertFile')")}
port, path = st.get("subPort") or "2097", (st.get("subPath") or "/sub/")
lim = xui.execute("SELECT limit_ip, limit_hwid, enable FROM clients WHERE email = ?", (key["panel_email"] or "",)).fetchone()
print("лимиты ключа в панели:", dict(lim) if lim else "клиент не найден")


def devices():
    return [dict(r) for r in xui.execute("SELECT id, user_agent, device_os FROM client_hwids WHERE sub_id = ?", (key["sub_id"],))]


before = devices()
print(f"устройств у ключа до проверки: {len(before)}")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE  # свой же сервер, обращение к 127.0.0.1 — сертификат выписан на другой адрес


def fetch(ua):
    for scheme in (("https", "http") if st.get("subCertFile") else ("http", "https")):
        url = f"{scheme}://127.0.0.1:{port}{path.rstrip('/')}/{key['sub_id']}"
        req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=10, context=ctx if scheme == "https" else None) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)
        except Exception as e:
            last = e
    return None, str(last).encode(), {}


for ua in AGENTS:
    code, body, headers = fetch(ua)
    text = body.decode("utf-8", "replace").strip()
    try:
        if not re.search(r"://", text):
            text = base64.b64decode(text + "=" * (-len(text) % 4)).decode("utf-8", "replace")
    except Exception:
        pass
    schemes = {}
    for line in text.splitlines():
        m = re.match(r"^([a-z0-9]+)://", line.strip())
        if m:
            schemes[m.group(1)] = schemes.get(m.group(1), 0) + 1
    info = "есть" if any(h.lower() == "subscription-userinfo" for h in headers) else "нет"
    if code is None:
        err = re.sub(r"[0-9]+(\.[0-9]+){3}", "*.*.*.*", text)[:160]
        print(f"\n[{ua}] не удалось подключиться к панели: {err}")
    else:
        print(f"\n[{ua}] ответ {code}, серверов в подписке: {sum(schemes.values())} {schemes or ''}, заголовок трафика/срока: {info}")
        if not schemes:
            print("   текст ответа (начало):", re.sub(r"[A-Za-z0-9_\-]{24,}", "***", re.sub(r"[0-9]+(\.[0-9]+){3}", "*.*.*.*", text))[:200])

after = devices()
new = [d for d in after if d["id"] not in {b["id"] for b in before}]
print(f"\nустройств у ключа после проверки: {len(after)}" + (f" — новые: {[(d['user_agent'], d['device_os']) for d in new]}" if new else " — новых нет"))
