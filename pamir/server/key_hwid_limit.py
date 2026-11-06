#!/usr/bin/env python3
"""Посмотреть или поменять лимит устройств (HWID) одного ключа в панели x-ui.

Работает тем же клиентом панели, что и бот: меняет только limitHwid у клиента этого ключа
во всех его подключениях, лимит IP и остальное не трогает. Прежнее значение дописывает
в /root/key_hwid_limit.log — чтобы потом вернуть как было. Ничего секретного не печатает.

Запускать Python'ом бота (там нужные библиотеки):
    cd /root/YadrenoVPN && <python бота> /root/key_hwid_limit.py 85          — показать лимит
    cd /root/YadrenoVPN && <python бота> /root/key_hwid_limit.py 85 5 --apply — поставить 5
"""
import asyncio
import datetime
import os
import sqlite3
import sys
import urllib.parse

ROOT = os.getenv("PAMIR_BOT_ROOT", "/root/YadrenoVPN")
DB = os.path.join(ROOT, "database", "vpn_bot.db")
LOG = "/root/key_hwid_limit.log"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

args = [a for a in sys.argv[1:] if not a.startswith("--")]
APPLY = "--apply" in sys.argv
if not args or not args[0].isdigit() or (len(args) > 1 and not args[1].isdigit()):
    sys.exit("Использование: key_hwid_limit.py <ID ключа> [новый лимит] [--apply]")
KEY_ID, NEW = int(args[0]), (int(args[1]) if len(args) > 1 else None)
if NEW is not None and not 1 <= NEW <= 20:
    sys.exit("Лимит от 1 до 20 (0 не ставлю: неясно, как панель отдаёт подписку без проверки HWID).")

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
key = conn.execute("SELECT id, server_id, panel_email FROM vpn_keys WHERE id = ?", (KEY_ID,)).fetchone()
if not key or not key["panel_email"] or not key["server_id"]:
    sys.exit(f"Ключ {KEY_ID} не найден или не привязан к панели — ничего не менял.")
server = dict(conn.execute("SELECT * FROM servers WHERE id = ?", (key["server_id"],)).fetchone())
conn.close()
EMAIL = key["panel_email"]

try:
    from bot.services.panels.xui import XUIClient
except Exception as error:
    sys.exit(f"Не удалось загрузить клиент панели бота ({error}) — ничего не менял.")
for name in ("_get_client_record", "_split_record", "_client_payload", "_write_with_state_check"):
    if not hasattr(XUIClient, name):
        sys.exit(f"Клиент панели бота устроен иначе (нет {name}) — ничего не менял.")


async def main():
    client = XUIClient(server)
    try:
        record = await client._get_client_record(EMAIL)
        if not record:
            sys.exit(f"Клиент ключа {KEY_ID} не найден в панели — ничего не менял.")
        current, inbound_ids = client._split_record(record)
        old = int(current.get("limitHwid") or 0)
        print(f"Ключ {KEY_ID}: лимит устройств сейчас {old}, лимит IP {int(current.get('limitIp') or 0)}, подключений {len(inbound_ids or [])}")
        if NEW is None:
            return
        if NEW == old:
            print("Уже стоит это значение — ничего не менял.")
            return
        if not APPLY:
            print(f"Поставлю {NEW}. Чтобы применить, добавьте --apply")
            return
        payload = client._client_payload(current, email=EMAIL)
        payload["limitHwid"] = NEW
        endpoint = f"/panel/api/clients/update/{urllib.parse.quote(EMAIL, safe='')}"
        if inbound_ids:
            endpoint += "?inboundIds=" + ",".join(str(v) for v in sorted(inbound_ids))

        def ok(rec):
            return bool(rec) and int(client._split_record(rec)[0].get("limitHwid") or 0) == NEW

        if not ok(await client._write_with_state_check("POST", endpoint, data=payload, email=EMAIL, validator=ok)):
            sys.exit("Панель не подтвердила изменение — проверьте ключ в панели.")
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M} UTC ключ {KEY_ID}: limitHwid {old} → {NEW}\n")
        print(f"Готово: лимит устройств {old} → {NEW}. Вернуть: key_hwid_limit.py {KEY_ID} {old or 1} --apply (записано в {LOG})")
    finally:
        close = getattr(client, "close", None)
        if close:
            await close()


asyncio.run(main())
