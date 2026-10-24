#!/usr/bin/env python3
"""Старая «Суточная статистика» бота больше не приходит — её заменяет утренний отчёт новой админки (admin_mognu).

Меняется только отправка статистики в bot/services/scheduler.py; ежедневный бэкап, напоминания и чистка ключей
идут как раньше. Вернуть старый отчёт без отката файла: в базе бота settings.mognu_old_daily_stats = '1'.

    python3 patch_daily_stats_off.py          показать, что изменится (ничего не меняет)
    python3 patch_daily_stats_off.py --apply  применить; копия: scheduler.py.bak-dailystats
Потом: systemctl restart yadreno-vpn
"""
import os
import py_compile
import shutil
import sys
from pathlib import Path

PATH = Path(os.getenv("PAMIR_SCHEDULER", "/root/YadrenoVPN/bot/services/scheduler.py"))
APPLY = "--apply" in sys.argv
MARK = "# Mognu: the morning report comes from the admin backend"
OLD = "    try:\n        report = await collect_daily_stats()\n"
NEW = ("    " + MARK + " (admin_mognu); settings.mognu_old_daily_stats = '1' brings this one back\n"
       "    if get_setting('mognu_old_daily_stats', '0') != '1':\n"
       "        logger.info(\"Суточная статистика: заменена утренним отчётом Mognu\")\n"
       "        return\n" + OLD)

src = PATH.read_text(encoding="utf-8")
if MARK in src:
    sys.exit("Правка уже стоит — ничего не меняю.")
if src.count(OLD) != 1 or "async def send_daily_stats" not in src or "get_setting" not in src:
    sys.exit("scheduler.py отличается от ожидаемого — ничего не меняю.")
print(("ПРИМЕНЯЮ: " if APPLY else "ИЗМЕНИТСЯ: ") + f"{PATH}: «Суточная статистика» больше не отправляется (бэкап остаётся)")
if not APPLY:
    sys.exit("Это был просмотр. Чтобы применить: python3 patch_daily_stats_off.py --apply")
backup = PATH.with_name(PATH.name + ".bak-dailystats")
shutil.copy2(PATH, backup)
PATH.write_text(src.replace(OLD, NEW, 1), encoding="utf-8")
try:
    py_compile.compile(str(PATH), doraise=True)
except py_compile.PyCompileError as error:
    shutil.copy2(backup, PATH)
    sys.exit(f"Ошибка синтаксиса, вернул копию: {error}")
print(f"Готово (копия: {backup}). Перезапустите бота: systemctl restart yadreno-vpn")
