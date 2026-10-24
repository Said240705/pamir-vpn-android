#!/usr/bin/env python3
"""Проверка «режима роутера» на тестовом ключе: отдаёт ли панель подписку без HWID, если у ключа лимит HWID = 0.

Только для ключа test@pamirlink.ru. Через API панели (тем же клиентом, что и бот) ставит этому ключу limitHwid = 0,
лимит IP не трогает, запускает router_subtest.py (лежит рядом) и в конце ВСЕГДА возвращает прежний limitHwid —
даже при ошибке или Ctrl+C. Другие ключи не трогает. Ничего секретного не печатает.

Запускать Python'ом бота (там нужные библиотеки):
    cd /root/YadrenoVPN && <python бота> /root/router_hwid_test.py
"""
import asyncio
import os
import sqlite3
import subprocess
import sys
import urllib.parse

ROOT = os.getenv("PAMIR_BOT_ROOT", "/root/YadrenoVPN")
DB = os.path.join(ROOT, "database", "vpn_bot.db")
HERE = os.path.dirname(os.path.abspath(__file__))
TEST_EMAIL = "test@pamirlink.ru"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
user = conn.execute("SELECT id FROM users WHERE lower(email) = ?", (TEST_EMAIL,)).fetchone()
if not user:
    sys.exit(f"Нет пользователя {TEST_EMAIL} — ничего не делаю.")
key = conn.execute("""SELECT id, server_id, panel_email FROM vpn_keys WHERE user_id = ? AND expires_at > datetime('now')
                      AND sub_id IS NOT NULL ORDER BY id DESC""", (user["id"],)).fetchone()
if not key or not key["panel_email"] or not key["server_id"]:
    sys.exit("У тестового пользователя нет активного ключа в панели — ничего не делаю.")
server = dict(conn.execute("SELECT * FROM servers WHERE id = ?", (key["server_id"],)).fetchone())
conn.close()
EMAIL = key["panel_email"]
print(f"Тестовый ключ ID {key['id']}")

try:
    from bot.services.panels.xui import XUIClient
except Exception as error:
    sys.exit(f"Не удалось загрузить клиент панели бота ({error}) — ничего не менял.")
for name in ("_get_client_record", "_split_record", "_client_payload", "_write_with_state_check"):
    if not hasattr(XUIClient, name):
        sys.exit(f"Клиент панели бота устроен иначе (нет {name}) — ничего не менял.")


async def set_hwid(client, value):
    record = await client._get_client_record(EMAIL)
    if not record:
        raise RuntimeError("клиент не найден в панели")
    current, inbound_ids = client._split_record(record)
    payload = client._client_payload(current, email=EMAIL)
    payload["limitHwid"] = int(value)
    endpoint = f"/panel/api/clients/update/{urllib.parse.quote(EMAIL, safe='')}"
    if inbound_ids:
        endpoint += "?inboundIds=" + ",".join(str(v) for v in sorted(inbound_ids))

    def ok(rec):
        return bool(rec) and int(client._split_record(rec)[0].get("limitHwid") or 0) == int(value)

    if not ok(await client._write_with_state_check("POST", endpoint, data=payload, email=EMAIL, validator=ok)):
        raise RuntimeError("панель не подтвердила изменение")


async def main():
    client = XUIClient(server)
    try:
        record = await client._get_client_record(EMAIL)
        if not record:
            sys.exit("Клиент тестового ключа не найден в панели — ничего не менял.")
        before = client._split_record(record)[0]
        old_hwid, old_ip = int(before.get("limitHwid") or 0), int(before.get("limitIp") or 0)
        print(f"было: limitHwid={old_hwid}, limitIp={old_ip}")
        try:
            await set_hwid(client, 0)
            print("поставил limitHwid=0 (лимит IP не трогал), проверяю подписку как роутер…\n")
            subprocess.run([sys.executable, os.path.join(HERE, "router_subtest.py")], check=False)
        finally:
            await set_hwid(client, old_hwid)
            after = client._split_record(await client._get_client_record(EMAIL))[0]
            print(f"\nвернул как было: limitHwid={after.get('limitHwid')}, limitIp={after.get('limitIp')}")
    finally:
        close = getattr(client, "close", None)
        if close:
            await close()


asyncio.run(main())
