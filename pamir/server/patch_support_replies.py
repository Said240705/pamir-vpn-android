#!/usr/bin/env python3
"""Ответ на сообщение поддержки не превращается в карточку кабинета.

Было: режим шлюза (bot/middlewares/gateway.py) на любое сообщение не-админа отвечает карточкой «Всё управление — в
личном кабинете». Поэтому ответ человека на сообщение из админки («Написать через бота», ответ в обращение) и даже
кнопка «Ответить» терялись.

Стало: если у человека есть ОТКРЫТОЕ обращение в поддержку, его сообщение (текст, фото, ответ свайпом) уходит в это
обращение — тем же обработчиком поддержки, что и после кнопки «Ответить»; кнопки поддержки тоже пропускаются. Без
открытого обращения всё как раньше: карточка кабинета. Команды (/…) обращения не трогают.

    python3 patch_support_replies.py          показать, что изменится (ничего не меняет)
    python3 patch_support_replies.py --apply  применить; копия: gateway.py.bak-supportreplies
Потом: systemctl restart yadreno-vpn
"""
import os
import py_compile
import shutil
import sys
from pathlib import Path

PATH = Path(os.getenv("PAMIR_GATEWAY", "/root/YadrenoVPN/bot/middlewares/gateway.py"))
APPLY = "--apply" in sys.argv
MARK = "# Mognu: replies into an open support thread"

PASS_OLD = "        return event.data == 'start'\n"
PASS_NEW = ("        # " + MARK[2:] + ": support buttons («Ответить» and the like) are not replaced by the card\n"
            "        return event.data == 'start' or 'support' in str(event.data or '')\n")
CALL_OLD = ("        if user is None or getattr(user, 'is_bot', False) or user.id in ADMIN_IDS or _passes(event):\n"
            "            return await handler(event, data)\n")
CALL_NEW = CALL_OLD + '''        if isinstance(event, Message) and await _mognu_route_to_support(event, data, user.id):
            return await handler(event, data)
'''
HELPER = '''

def _mognu_open_thread_id(telegram_id: int):
    from database.connection import get_db

    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM support_threads WHERE user_telegram_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
            (telegram_id,),
        ).fetchone()
    return int(row[0]) if row else None


async def _mognu_route_to_support(event, data, telegram_id: int) -> bool:
    """''' + MARK + ''': with an open thread the message goes to the support handler, as after «Ответить».
    Sets the same FSM state that button sets; True — let the update through to the handlers."""
    text = (event.text or event.caption or '').strip()
    if text.startswith('/'):
        return False
    state = data.get('state')
    if state is None:
        return False
    try:
        thread_id = _mognu_open_thread_id(telegram_id)
        if not thread_id:
            return False
        from bot.handlers.user import support as _support

        waiting = _support.SupportUserStates.waiting_for_message
        await state.set_state(waiting)
        await state.update_data(support_thread_id=thread_id)
        data['raw_state'] = waiting.state
        return True
    except Exception:
        logger.exception('gateway: support routing failed for %s', telegram_id)
        return False
'''

src = PATH.read_text(encoding="utf-8")
if MARK in src:
    sys.exit("Правка уже стоит — ничего не меняю.")
if src.count(PASS_OLD) != 1 or src.count(CALL_OLD) != 1 or "logger" not in src:
    sys.exit("gateway.py отличается от ожидаемого — ничего не меняю.")
print(("ПРИМЕНЯЮ: " if APPLY else "ИЗМЕНИТСЯ: ") + f"{PATH}: ответы в открытое обращение — в поддержку, кнопки поддержки пропускаются")
if not APPLY:
    sys.exit("Это был просмотр. Чтобы применить: python3 patch_support_replies.py --apply")
backup = PATH.with_name(PATH.name + ".bak-supportreplies")
shutil.copy2(PATH, backup)
new = src.replace(PASS_OLD, PASS_NEW, 1).replace(CALL_OLD, CALL_NEW, 1)
anchor = "\n__all__ = "
new = new.replace(anchor, HELPER + "\n" + anchor, 1) if anchor in new else new.rstrip("\n") + "\n" + HELPER
PATH.write_text(new, encoding="utf-8")
try:
    py_compile.compile(str(PATH), doraise=True)
except py_compile.PyCompileError as error:
    shutil.copy2(backup, PATH)
    sys.exit(f"Ошибка синтаксиса, вернул копию: {error}")
print(f"Готово (копия: {backup}). Перезапустите бота: systemctl restart yadreno-vpn")
