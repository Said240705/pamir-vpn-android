#!/usr/bin/env python3
"""Админка: «Удалить» у ключа падала с internal_error — FOREIGN KEY constraint failed, а клиент с панели не удалялся.

На ключ ссылаются таблицы без автоматической очистки: payments (платежи по ключу) и notification_log
(отправленные напоминания). Обработчик удалял только сам ключ, и база отказывала. Теперь перед удалением:
платежи отвязываются от ключа (vpn_key_id = NULL — история и статистика сохраняются), записи уведомлений
о ключе удаляются. Как и при удалении из кабинета, сначала с панели 3X-UI удаляется клиент — иначе подписка
человека продолжала работать.

Копия файла — /root/mini_app_api.py.bak-keydelete-fk; проверка синтаксиса; при ошибке файл возвращается.
Повторный запуск ничего не меняет.

    python3 patch_admin_key_delete_fk.py            показать
    python3 patch_admin_key_delete_fk.py --apply    применить и перезапустить бота
"""
import py_compile
import shutil
import sqlite3
import subprocess
import sys

F = "/root/YadrenoVPN/bot/services/mini_app_api.py"
DB = "/root/YadrenoVPN/database/vpn_bot.db"
OLD = '''        with get_db() as conn:
            conn.execute("DELETE FROM vpn_keys WHERE id = ?", (key_id,))
        return web.json_response({'ok': True})
    except Exception as error:
        logger.exception('Admin key delete unexpected error: %s', error)'''
FK_ONLY = '''        with get_db() as conn:
            # на ключ ссылаются таблицы без ON DELETE: платежи отвязываем (история остаётся), напоминания удаляем
            conn.execute("UPDATE payments SET vpn_key_id = NULL WHERE vpn_key_id = ?", (key_id,))
            conn.execute("DELETE FROM notification_log WHERE vpn_key_id = ?", (key_id,))
            conn.execute("DELETE FROM vpn_keys WHERE id = ?", (key_id,))
        return web.json_response({'ok': True})
    except Exception as error:
        logger.exception('Admin key delete unexpected error: %s', error)'''
NEW = '''        with get_db() as conn:
            row = conn.execute("SELECT server_id, panel_email FROM vpn_keys WHERE id = ?", (key_id,)).fetchone()
        # Mognu: как удаление из кабинета — сначала клиент с панели, иначе подписка человека продолжает работать
        if row and row['server_id'] and row['panel_email']:
            try:
                from bot.services.vpn_api import get_client
                from bot.utils.panel_email import is_managed_panel_email
                if is_managed_panel_email(row['panel_email']):
                    client = await get_client(row['server_id'])
                    await client.delete_client(row['panel_email'])
            except Exception as error:
                logger.warning('Admin key delete: panel client not removed key=%s type=%s', key_id, type(error).__name__)
        with get_db() as conn:
            # на ключ ссылаются таблицы без ON DELETE: платежи отвязываем (история остаётся), напоминания удаляем
            conn.execute("UPDATE payments SET vpn_key_id = NULL WHERE vpn_key_id = ?", (key_id,))
            conn.execute("DELETE FROM notification_log WHERE vpn_key_id = ?", (key_id,))
            conn.execute("DELETE FROM vpn_keys WHERE id = ?", (key_id,))
        logger.info('Admin key delete: key=%s', key_id)
        return web.json_response({'ok': True})
    except Exception as error:
        logger.exception('Admin key delete unexpected error: %s', error)'''


src = open(F, encoding="utf-8").read()
if NEW in src:
    sys.exit("Уже исправлено — менять нечего.")
if src.count(FK_ONLY) == 1:   # первая версия патча уже стоит — дополняем удалением с панели
    OLD = FK_ONLY
if src.count(OLD) != 1:
    sys.exit("Не нашёл обработчик удаления ключа в ожидаемом виде — ничего не меняю. Пришлите: grep -n 'DELETE FROM vpn_keys' " + F)
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
notnull = {r[1]: r[3] for r in c.execute("PRAGMA table_info(payments)")}.get("vpn_key_id")
c.close()
if notnull:
    sys.exit("payments.vpn_key_id объявлен NOT NULL — отвязать платежи нельзя, ничего не меняю. Пришлите этот вывод.")
print("будет: перед удалением ключа — клиент удаляется с панели, payments.vpn_key_id = NULL, удаление из notification_log")
if "--apply" not in sys.argv:
    sys.exit("Это проверка. Применить: python3 patch_admin_key_delete_fk.py --apply")
bak = "/root/mini_app_api.py.bak-keydelete-fk"
shutil.copy2(F, bak)
open(F, "w", encoding="utf-8").write(src.replace(OLD, NEW))
try:
    py_compile.compile(F, doraise=True)
except py_compile.PyCompileError as e:
    shutil.copy2(bak, F)
    sys.exit(f"Синтаксис не прошёл — вернул файл: {e}")
subprocess.run(["systemctl", "restart", "yadreno-vpn"], check=True)
print("Готово, бот перезапущен. Копия:", bak)
