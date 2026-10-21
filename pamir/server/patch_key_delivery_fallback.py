#!/usr/bin/env python3
"""Покупка из приложения или сайта: ключ ставится в панель, даже если Telegram-бот у человека не запущен.

Меняет bot/services/payment_completion.py, ветку фонового завершения оплаты (её запускает автопроверка
платежей, когда ЮKassa подтвердила оплату раньше, чем приложение или сайт).

Было: фоновое завершение ставит ключ через start_new_key_config_background — та же настройка, но с
сообщениями «оплата прошла / настраиваем ключ» в Telegram. Если человек ни разу не открывал бота
(Telegram отвечает «chat not found»), настройка возвращает progress_delivery_failed, автопроверка три раза
повторяет то же самое и сдаётся: платёж «completed», а ключ остаётся черновиком без сервера и подписки —
в кабинете он есть, а приложению нечего подключать (заказ 003S, ключ 74, 21.10.2026).

Стало: при progress_delivery_failed ключ сразу ставится без сообщений — тем же
_run_key_setup_without_delivery, что и при оплате из приложения (и fix_draft_keys.py). В журнале бота —
строка «Pamir: key progress not delivered».

Копия перед изменением: payment_completion.py.bak-delivery. Повторный запуск ничего не меняет.
"""
import py_compile
import shutil
import sys
from pathlib import Path

PATH = Path(sys.argv[1] if len(sys.argv) > 1 else "/root/YadrenoVPN/bot/services/payment_completion.py")
src = PATH.read_text(encoding="utf-8")
if "Pamir: key progress not delivered" in src:
    sys.exit("Правка уже применена — ничего не меняю.")

OLD = """                key_setup = await start_new_key_config_background(
                    bot,
                    telegram_id=owner_telegram_id,
                    username=(owner or {}).get("username"),
                    order_id=normalized_order_id,
                    anchor_message=primary_message,
                )
"""
NEW = OLD + """                # Pamir: бот в Telegram у человека не запущен (покупка из приложения или сайта) — сообщение
                # не доставить, но ключ всё равно ставим в панель, как при оплате из приложения.
                if (
                    key_setup is not None
                    and key_setup.retryable
                    and key_setup.error_code == "progress_delivery_failed"
                ):
                    logger.warning(
                        "Pamir: key progress not delivered order=%s, setting the key up without delivery",
                        normalized_order_id,
                    )
                    key_setup = await _run_key_setup_without_delivery(
                        normalized_order_id,
                        telegram_id=owner_telegram_id,
                    )
"""

if src.count(OLD) != 1 or "async def _run_key_setup_without_delivery(" not in src:
    sys.exit("Не нашёл фоновую настройку ключа в ожидаемом виде — файл отличается, ничего не меняю.")

backup = PATH.with_name(PATH.name + ".bak-delivery")
shutil.copy2(PATH, backup)
PATH.write_text(src.replace(OLD, NEW), encoding="utf-8")
try:
    py_compile.compile(str(PATH), doraise=True)
except py_compile.PyCompileError as error:
    shutil.copy2(backup, PATH)
    sys.exit(f"Ошибка синтаксиса, вернул копию: {error}")
print(f"Готово: {PATH} (копия: {backup}). Перезапустите бота: systemctl restart yadreno-vpn")
