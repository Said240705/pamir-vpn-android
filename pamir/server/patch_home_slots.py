#!/usr/bin/env python3
"""Лимит устройств ключа = максимум из докупленных слотов и лимита тарифа (тариф «На весь дом» — 3 устройства).

Было: бот считал лимит только по докупленным слотам (key_device_slots, по умолчанию 1), лимит тарифа и личный лимит
ключа (max_ips_override) не учитывал. Поэтому у ключа «Весь дом» на 3 устройства кабинет показывал «1» и предлагал
докупить устройство — а покупка ставила в панели лимит 2, то есть урезала ключ.

Стало (bot/services/mini_app_api.py):
- /mini-app-api/device-slots отдаёт лимит с учётом тарифа и личного лимита ключа;
- докупка устройства начинает счёт с того же лимита — ключ «Весь дом» сразу на максимуме, урезать нечего.

    python3 patch_home_slots.py          показать, что изменится (ничего не меняет)
    python3 patch_home_slots.py --apply  применить; копия: mini_app_api.py.bak-homeslots
Потом: systemctl restart yadreno-vpn
"""
import os
import py_compile
import shutil
import sys
from pathlib import Path

PATH = Path(os.getenv("PAMIR_BOT_SERVICES", "/root/YadrenoVPN/bot/services")) / "mini_app_api.py"
APPLY = "--apply" in sys.argv
MARK = "# Mognu: device limit includes the tariff"
BASE = "COALESCE(vk.max_ips_override, (SELECT t.max_ips FROM tariffs t WHERE t.id = vk.tariff_id), 1)"

LIST_OLD = '"SELECT vk.id AS key_id, COALESCE(kds.device_limit, 1) AS device_limit "\n'
LIST_NEW = f'"SELECT vk.id AS key_id, MAX(COALESCE(kds.device_limit, 1), {BASE}) AS device_limit "  {MARK}\n'
BUY_OLD = "            current_limit = slot_row['device_limit'] if slot_row else 1\n"
BUY_NEW = BUY_OLD + (
    "            _mognu_base = conn.execute(  " + MARK + "\n"
    f'                "SELECT {BASE} FROM vpn_keys vk WHERE vk.id = ?", (key_id,)\n'
    "            ).fetchone()\n"
    "            current_limit = max(int(current_limit or 1), int(_mognu_base[0] or 1) if _mognu_base else 1)\n")

src = PATH.read_text(encoding="utf-8")
if MARK in src:
    sys.exit("Правка уже стоит — ничего не меняю.")
if src.count(LIST_OLD) != 1 or src.count(BUY_OLD) != 1:
    sys.exit("mini_app_api.py отличается от ожидаемого — ничего не меняю.")
print(("ПРИМЕНЯЮ: " if APPLY else "ИЗМЕНИТСЯ: ") + f"{PATH.name}: лимит устройств с учётом тарифа (список и докупка)")
if not APPLY:
    sys.exit("Это был просмотр. Чтобы применить: python3 patch_home_slots.py --apply")
backup = PATH.with_name(PATH.name + ".bak-homeslots")
shutil.copy2(PATH, backup)
PATH.write_text(src.replace(LIST_OLD, LIST_NEW, 1).replace(BUY_OLD, BUY_NEW, 1), encoding="utf-8")
try:
    py_compile.compile(str(PATH), doraise=True)
except py_compile.PyCompileError as error:
    shutil.copy2(backup, PATH)
    sys.exit(f"Ошибка синтаксиса, вернул копию: {error}")
print(f"Готово (копия: {backup}). Перезапустите бота: systemctl restart yadreno-vpn")
