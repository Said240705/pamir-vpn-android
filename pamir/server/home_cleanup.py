#!/usr/bin/env python3
"""«🏠 Домой» — разовая уборка: отвязать вход «Домой» у всех, кто не включал его сам.

До patch_home_descriptor.py сверка бота привязала «Домой» почти всем клиентам. Скрипт оставляет
вход только ключам, у которых в pamir_home_optin стоит want=1 (включили кнопкой) и подписка действует,
у остальных убирает его тем же клиентом панели, что и бот (_detach_one). Другие входы не трогает;
если «Домой» у клиента единственный вход — не трогает и сообщает. Печатает только номера ключей.

Сначала проверка (ничего не меняет), потом --apply (перед изменениями — копия базы панели).
Тот же замок, что у home_optin.py, чтобы не мешать кнопке:

    cd /root/YadrenoVPN && flock -w 60 /run/mognu-home.lock venv/bin/python /root/home_cleanup.py
    cd /root/YadrenoVPN && flock -w 60 /run/mognu-home.lock venv/bin/python /root/home_cleanup.py --apply
"""
import asyncio
import datetime
import os
import sqlite3
import sys

ROOT = os.getenv("PAMIR_BOT_ROOT", "/root/YadrenoVPN")
DB = os.path.join(ROOT, "database", "vpn_bot.db")
XUI_DB = os.getenv("PAMIR_XUI_DB", "/etc/x-ui/x-ui.db")
MARK = "Домой"
APPLY = "--apply" in sys.argv
sys.path.insert(0, ROOT)
os.chdir(ROOT)

# 1. Кто сейчас привязан к «Домой» (база панели, только чтение)
x = sqlite3.connect(f"file:{XUI_DB}?mode=ro", uri=True, timeout=10)
home = [r[0] for r in x.execute("SELECT id FROM inbounds WHERE remark LIKE ?", (f"%{MARK}%",))]
if len(home) != 1:
    sys.exit(f"Входов с «{MARK}» в панели: {len(home)} (нужен ровно один) — ничего не делаю.")
hid = home[0]
attached = {r[0] for r in x.execute("""SELECT cl.email FROM clients cl JOIN client_inbounds ci ON ci.client_id = cl.id
                                       WHERE ci.inbound_id = ?""", (hid,))}
x.close()

# 2. Кто включил «Домой» сам (база бота)
c = sqlite3.connect(DB, timeout=10)
c.row_factory = sqlite3.Row
has_optin = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pamir_home_optin'").fetchone()
keep = set()
if has_optin:
    keep = {r[0] for r in c.execute("""SELECT k.panel_email FROM pamir_home_optin h JOIN vpn_keys k ON k.id = h.key_id
                                       WHERE h.want = 1 AND k.expires_at > datetime('now')""")}
keys = {r["panel_email"]: dict(r) for r in c.execute(
    "SELECT id, server_id, panel_email FROM vpn_keys WHERE panel_email IS NOT NULL")}
servers = {r["id"]: dict(r) for r in c.execute("SELECT * FROM servers")}
c.close()

drop = sorted(attached - keep)
unknown = [e for e in drop if e not in keys]
drop = [e for e in drop if e in keys]
print(f"Вход «{MARK}» (id {hid}): привязан у {len(attached)}, включили сами {len(attached & keep)}, "
      f"убрать у {len(drop)}" + (f", не нашлось в базе бота {len(unknown)} (их не трогаю)" if unknown else ""))
if drop:
    print("Ключи:", ", ".join(str(keys[e]["id"]) for e in drop))
if not APPLY:
    sys.exit("Это проверка, ничего не изменено. Чтобы убрать: добавьте --apply")
if not drop:
    sys.exit("Убирать нечего.")

# 3. Копия базы панели
bak = f"{XUI_DB}.bak-homecleanup-{datetime.datetime.now():%Y%m%d-%H%M%S}"
src = sqlite3.connect(f"file:{XUI_DB}?mode=ro", uri=True, timeout=10)
dst = sqlite3.connect(bak)
src.backup(dst)
dst.close()
src.close()
os.chmod(bak, 0o600)
print(f"Копия базы панели: {bak}")

from bot.services.panels.xui import XUIClient  # noqa: E402

for _name in ("_detach_one", "_get_client_record", "_split_record"):
    if not hasattr(XUIClient, _name):
        sys.exit(f"Клиент панели бота устроен иначе (нет {_name}) — ничего не делаю.")


async def main():
    done = failed = 0
    by_server = {}
    for e in drop:
        by_server.setdefault(keys[e]["server_id"], []).append(e)
    for sid, emails in by_server.items():
        if sid not in servers:
            print(f"сервер {sid}: нет в базе бота — пропускаю {len(emails)}")
            failed += len(emails)
            continue
        client = XUIClient(servers[sid])
        try:
            for e in emails:
                kid = keys[e]["id"]
                try:
                    rec = await client._get_client_record(e)
                    if not rec:
                        raise RuntimeError("клиента нет в панели")
                    _, now_in = client._split_record(rec)
                    now_in = set(now_in or ())
                    if hid not in now_in:
                        done += 1
                        continue
                    if not now_in - {hid}:
                        raise RuntimeError("«Домой» — единственный вход, не трогаю")
                    await client._detach_one(e, hid)
                    _, after = client._split_record(await client._get_client_record(e))
                    if hid in set(after or ()):
                        raise RuntimeError("панель не подтвердила")
                    done += 1
                except Exception as error:
                    failed += 1
                    print(f"ключ {kid}: не получилось ({type(error).__name__}: {str(error)[:120]})")
        finally:
            close = getattr(client, "close", None)
            if close:
                await close()
    print(f"Готово: убрано у {done}, не получилось у {failed}.")


asyncio.run(main())
