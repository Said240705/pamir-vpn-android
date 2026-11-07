#!/usr/bin/env python3
"""«🏠 Россия · Домой» — шаг 3: привязать существующие ключи к новому входу.

Новые ключи бот привязывает ко всем видимым входам сам; этот скрипт один раз добавляет вход «Домой»
ключам, которые уже есть. Работает тем же клиентом панели, что и бот (_attach_one), других входов
и настроек ключей не трогает. Ничего секретного не печатает.

Запускать Python'ом бота:
    cd /root/YadrenoVPN && venv/bin/python /root/home_attach.py           — показать, что будет сделано
    cd /root/YadrenoVPN && venv/bin/python /root/home_attach.py --test    — только тестовый ключ test@pamirlink.ru
    cd /root/YadrenoVPN && venv/bin/python /root/home_attach.py --apply   — все действующие ключи
"""
import asyncio
import os
import sqlite3
import sys

ROOT = os.getenv("PAMIR_BOT_ROOT", "/root/YadrenoVPN")
DB = os.path.join(ROOT, "database", "vpn_bot.db")
MARK = "Домой"
TEST_EMAIL = "test@pamirlink.ru"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

MODE = "apply" if "--apply" in sys.argv else "test" if "--test" in sys.argv else "dry"

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
if MODE == "test":
    rows = conn.execute("""SELECT k.id, k.server_id, k.panel_email FROM vpn_keys k JOIN users u ON u.id = k.user_id
                           WHERE lower(u.email) = ? AND k.expires_at > datetime('now') AND k.panel_email IS NOT NULL""", (TEST_EMAIL,)).fetchall()
else:
    rows = conn.execute("""SELECT id, server_id, panel_email FROM vpn_keys
                           WHERE expires_at > datetime('now') AND panel_email IS NOT NULL AND panel_email != ''""").fetchall()
servers = {r["server_id"] for r in rows}
server_rows = {sid: dict(conn.execute("SELECT * FROM servers WHERE id = ?", (sid,)).fetchone()) for sid in servers if sid}
conn.close()
if not rows:
    sys.exit("Нет подходящих действующих ключей — ничего не делаю.")

try:
    from bot.services.panels.xui import XUIClient
except Exception as error:
    sys.exit(f"Не удалось загрузить клиент панели бота ({error}) — ничего не менял.")
for name in ("_attach_one", "_get_client_record", "_split_record", "get_inbounds"):
    if not hasattr(XUIClient, name):
        sys.exit(f"Клиент панели бота устроен иначе (нет {name}) — ничего не менял.")


async def main():
    done = skipped = failed = 0
    for sid, server in server_rows.items():
        client = XUIClient(server)
        try:
            inbounds = await client.get_inbounds(include_ignored=True)
            home = [i for i in inbounds if MARK in str(i.get("remark", ""))]
            if len(home) != 1:
                print(f"Сервер {sid}: входов с «{MARK}» в названии {len(home)} (нужен ровно один) — пропускаю.")
                continue
            hid = int(home[0]["id"])
            keys = [r for r in rows if r["server_id"] == sid]
            print(f"Сервер {sid}: вход «{home[0].get('remark')}» (id {hid}), действующих ключей: {len(keys)}, режим: {MODE}")
            for r in keys:
                email = r["panel_email"]
                try:
                    rec = await client._get_client_record(email)
                    if not rec:
                        failed += 1
                        print(f"  ключ {r['id']}: нет в панели")
                        continue
                    _, attached = client._split_record(rec)
                    if hid in (attached or set()):
                        skipped += 1
                        continue
                    if MODE == "dry":
                        done += 1
                        continue
                    await client._attach_one(email, hid)
                    done += 1
                except Exception as error:
                    failed += 1
                    print(f"  ключ {r['id']}: не получилось ({type(error).__name__})")
        finally:
            close = getattr(client, "close", None)
            if close:
                await close()
    verb = "будет привязано" if MODE == "dry" else "привязано"
    print(f"Итого: {verb} {done}, уже были {skipped}, ошибок {failed}.")
    if MODE == "dry":
        print("Это проверка. Сначала --test (только тестовый ключ), потом --apply (все).")


asyncio.run(main())
