#!/usr/bin/env python3
"""Поддержка: ответ пользователю без Telegram (аккаунт по почте) сохраняется в переписку.

Меняет bot/handlers/admin/support.py, функцию _send_admin_support_message_locked.

Было: бот сначала отправлял ответ в Telegram и только потом записывал его в переписку.
У аккаунтов, созданных по почте, Telegram нет (их ID отрицательный) — отправка падала
с «Telegram вернул ошибку доставки», и ответ терялся.

Стало: для таких аккаунтов отправка в Telegram пропускается, ответ сразу записывается
в переписку — человек видит его в приложении (Настройки → Поддержка) и в кабинете на сайте.
Пользователям с Telegram всё как раньше.

Копия перед изменением: support.py.bak-supportweb. Повторный запуск ничего не меняет.
"""
import py_compile
import shutil
import sys
from pathlib import Path

PATH = Path(sys.argv[1] if len(sys.argv) > 1 else "/root/YadrenoVPN/bot/handlers/admin/support.py")
src = PATH.read_text(encoding="utf-8")
if "Pamir: аккаунт без Telegram" in src:
    sys.exit("Правка уже применена — ничего не меняю.")

OLD = """        try:
            await send_admin_message_to_user(
                message.bot,
                thread=thread,
                source_message=message,
            )
            record_support_message(
"""
NEW = """        try:
            # Pamir: аккаунт без Telegram (создан по почте, ID отрицательный) — в Telegram не шлём,
            # ответ только записывается: человек увидит его в приложении и в кабинете на сайте.
            if int(thread["user_telegram_id"] or 0) > 0:
                await send_admin_message_to_user(
                    message.bot,
                    thread=thread,
                    source_message=message,
                )
            record_support_message(
"""
if src.count(OLD) != 1:
    sys.exit("Не нашёл отправку ответа в ожидаемом виде — файл отличается, ничего не меняю.")

backup = PATH.with_name(PATH.name + ".bak-supportweb")
shutil.copy2(PATH, backup)
PATH.write_text(src.replace(OLD, NEW), encoding="utf-8")
try:
    py_compile.compile(str(PATH), doraise=True)
except py_compile.PyCompileError as error:
    shutil.copy2(backup, PATH)
    sys.exit(f"Ошибка синтаксиса, вернул копию: {error}")
print(f"Готово: {PATH} (копия: {backup}). Перезапустите бота: systemctl restart yadreno-vpn")
