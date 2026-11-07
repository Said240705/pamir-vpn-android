#!/usr/bin/env python3
"""«🏠 Домой» по желанию — исполнитель запросов из кабинета. Запускается раз в минуту (cron).

Кабинет пишет в pamir_home_optin «хочу Домой / не хочу» по ключу. Скрипт тем же клиентом панели,
что и бот, добавляет или убирает вход с «Домой» в названии у клиента этого ключа и отмечает результат.
Заодно следит, чтобы у включивших вход не пропал (например, если бот переписал клиента при продлении).
Других входов и настроек ключей не трогает. Ничего секретного не печатает.

    cd /root/YadrenoVPN && venv/bin/python /root/home_optin.py

cron (от root):
    * * * * * cd /root/YadrenoVPN && flock -n /run/mognu-home.lock venv/bin/python /root/home_optin.py >> /var/log/mognu-home.log 2>&1
"""
import asyncio
import datetime
import os
import sqlite3
import sys

ROOT = os.getenv("PAMIR_BOT_ROOT", "/root/YadrenoVPN")
DB = os.path.join(ROOT, "database", "vpn_bot.db")
MARK = "Домой"
sys.path.insert(0, ROOT)
os.chdir(ROOT)


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def log(text):
    print(f"{now()} {text}", flush=True)


def db():
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    return c


c = db()
if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pamir_home_optin'").fetchone():
    sys.exit(0)  # кабинет ещё ни разу не включал «Домой»
rows = [dict(r) for r in c.execute("""SELECT h.key_id, h.want, h.status, h.requested_at, k.server_id, k.panel_email,
                                       k.expires_at > datetime('now') AS active
                                       FROM pamir_home_optin h JOIN vpn_keys k ON k.id = h.key_id
                                       WHERE h.status = 'pending' OR h.want = 1""")]
servers = {r["server_id"]: dict(c.execute("SELECT * FROM servers WHERE id = ?", (r["server_id"],)).fetchone())
           for r in rows if r["server_id"]}
c.close()
if not rows:
    sys.exit(0)

from bot.services.panels.xui import XUIClient  # noqa: E402

for _name in ("_attach_one", "_detach_one", "_get_client_record", "_split_record", "get_inbounds"):
    if not hasattr(XUIClient, _name):
        sys.exit(f"Клиент панели бота устроен иначе (нет {_name}) — ничего не делаю.")


def mark(key_id, status, error=None):
    c = db()
    try:
        c.execute("UPDATE pamir_home_optin SET status = ?, done_at = ?, error = ? WHERE key_id = ?", (status, now(), error, key_id))
        c.commit()
    finally:
        c.close()


async def set_home(client, email, hid, on):
    """Добавить (_attach_one) или убрать (_detach_one) вход hid у клиента; → привязан ли вход после этого.
    Просто сохранить клиента с новым списком входов нельзя — эта панель вход при этом не убирает."""
    rec = await client._get_client_record(email)
    if not rec:
        raise RuntimeError("клиента нет в панели")
    current, attached = client._split_record(rec)
    attached = set(attached or ())
    if (hid in attached) == on:
        return on
    if on:
        await client._attach_one(email, hid)
    else:
        if not attached - {hid}:
            raise RuntimeError("у ключа не осталось бы входов — не трогаю")
        await client._detach_one(email, hid)
    _, after = client._split_record(await client._get_client_record(email))
    return hid in set(after or ())


async def main():
    for sid, server in servers.items():
        client = XUIClient(server)
        try:
            home = [i for i in await client.get_inbounds(include_ignored=True) if MARK in str(i.get("remark", ""))]
            if len(home) != 1:
                log(f"сервер {sid}: входов с «{MARK}» {len(home)} (нужен ровно один) — жду")
                continue
            hid = int(home[0]["id"])
            for r in [r for r in rows if r["server_id"] == sid]:
                want = bool(r["want"]) and bool(r["active"])
                try:
                    got = await set_home(client, r["panel_email"], hid, want)
                    if got != want:
                        raise RuntimeError("панель не подтвердила")
                    if r["status"] == "pending":
                        mark(r["key_id"], "done")
                        log(f"ключ {r['key_id']}: «Домой» {'включён' if want else 'выключен'}")
                    elif want:
                        pass  # проверка включивших: на месте
                except Exception as error:
                    # запрос из кабинета пробуем 5 минут, потом «ошибка» — кабинет покажет «напишите в поддержку»
                    fresh = r["status"] == "pending" and r["requested_at"] and r["requested_at"] > (
                        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
                    if r["status"] == "pending":
                        mark(r["key_id"], "pending" if fresh else "error", f"{type(error).__name__}: {error}"[:300])
                    # у уже включённых (проверка раз в минуту) статус не трогаем — попробуем в следующий раз
                    log(f"ключ {r['key_id']}: не получилось ({type(error).__name__}: {str(error)[:120]})")
        finally:
            close = getattr(client, "close", None)
            if close:
                await close()


asyncio.run(main())
