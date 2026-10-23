#!/usr/bin/env python3
"""Закрытое обращение: понятный текст и кнопка «Написать в поддержку».

Было: «🔒 Обращение №N закрыто. Если вопрос остался — просто напишите снова.» — но режим шлюза на новое сообщение
отвечает карточкой кабинета, обращение не открывается.

Стало:
- текст «🔒 Обращение №N закрыто — спасибо, что написали! Если появится новый вопрос, нажмите «Написать в
  поддержку» 👇» и кнопка «💬 Написать в поддержку» (кнопка бота support_start — открывает новое обращение);
  в обоих местах, где обращение закрывается: веб-админка (mini_app_api.py) и бот (handlers/admin/pamir_tickets.py);
- шлюз пропускает того, кто только что нажал кнопку поддержки, — его сообщение уходит в новое обращение
  (если patch_support_replies.py уже стоит, он дополняется; если нет — сначала запустите его).

    python3 patch_support_close.py          показать, что изменится (ничего не меняет)
    python3 patch_support_close.py --apply  применить; копии: *.bak-supportclose
Потом: systemctl restart yadreno-vpn
"""
import os
import py_compile
import shutil
import sys
from pathlib import Path

ROOT = Path(os.getenv("PAMIR_BOT_ROOT", "/root/YadrenoVPN"))
APPLY = "--apply" in sys.argv
MARK = "# Mognu: support again button"
NEW_TEXT = "🔒 Обращение №{N} закрыто — спасибо, что написали!\\nЕсли появится новый вопрос, нажмите «Написать в поддержку» 👇"
KB = "reply_markup=_mognu_support_again_kb()"
HELPER = '''

def _mognu_support_again_kb():
    """''' + MARK + ''': the closed-thread message offers a new thread (bot button support_start)."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 Написать в поддержку", callback_data="support_start")]])
'''
TARGETS = [
    (ROOT / "bot/services/mini_app_api.py",
     'f"🔒 Обращение №{int(thread_id)} закрыто.\\nЕсли вопрос остался — просто напишите снова.",',
     'f"' + NEW_TEXT.replace("{N}", "{int(thread_id)}") + '", ' + KB + ','),
    (ROOT / "bot/handlers/admin/pamir_tickets.py",
     'f"🔒 Обращение №{thread_id} закрыто.\\nЕсли вопрос остался — просто напишите снова."',
     'f"' + NEW_TEXT.replace("{N}", "{thread_id}") + '", ' + KB),
]
GW = ROOT / "bot/middlewares/gateway.py"
GW_OLD = '''    try:
        thread_id = _mognu_open_thread_id(telegram_id)
        if not thread_id:
            return False
        from bot.handlers.user import support as _support

        waiting = _support.SupportUserStates.waiting_for_message
'''
GW_NEW = '''    try:
        from bot.handlers.user import support as _support

        waiting = _support.SupportUserStates.waiting_for_message
        if data.get('raw_state') == waiting.state:
            return True  # pressed «Написать в поддержку» / «Ответить»: the support handler takes it
        thread_id = _mognu_open_thread_id(telegram_id)
        if not thread_id:
            return False
'''

plan = []
for path, old, new in TARGETS:
    if not path.exists():
        sys.exit(f"Нет {path} — ничего не меняю.")
    src = path.read_text(encoding="utf-8")
    if MARK in src:
        print(f"{path.name}: уже исправлено — не трогаю.")
        continue
    if src.count(old) != 1:
        sys.exit(f"{path.name}: не нашёл текст закрытия в ожидаемом виде — ничего не меняю.")
    plan.append((path, src.replace(old, new, 1).rstrip("\n") + "\n" + HELPER))

gw = GW.read_text(encoding="utf-8") if GW.exists() else ""
if "_mognu_route_to_support" not in gw:
    sys.exit("Шлюз ещё без правки поддержки — сначала: python3 patch_support_replies.py --apply, потом этот скрипт.")
if "data.get('raw_state') == waiting.state" in gw:
    print("gateway.py: уже пропускает нажавших кнопку поддержки — не трогаю.")
elif gw.count(GW_OLD) != 1:
    sys.exit("gateway.py отличается от ожидаемого — ничего не меняю.")
else:
    plan.append((GW, gw.replace(GW_OLD, GW_NEW, 1)))

for path, _ in plan:
    print(("ПРИМЕНЯЮ: " if APPLY else "ИЗМЕНИТСЯ: ") + str(path.relative_to(ROOT)))
if not plan:
    sys.exit("Всё уже исправлено.")
if not APPLY:
    sys.exit("Это был просмотр. Чтобы применить: python3 patch_support_close.py --apply")

done = []
try:
    for path, new in plan:
        backup = path.with_name(path.name + ".bak-supportclose")
        shutil.copy2(path, backup)
        path.write_text(new, encoding="utf-8")
        done.append((path, backup))
        py_compile.compile(str(path), doraise=True)
except Exception as error:
    for path, backup in done:
        shutil.copy2(backup, path)
    sys.exit(f"Ошибка, вернул все файлы как были: {error}")
print("Готово (копии *.bak-supportclose). Перезапустите бота: systemctl restart yadreno-vpn")
