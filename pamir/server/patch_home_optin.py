#!/usr/bin/env python3
"""«🏠 Домой» по желанию: бот не добавляет вход «Домой» в ключи сам.

Меняет bot/utils/inbounds.py, функцию is_ignored_inbound: кроме входов с «--!» в начале названия
бот теперь пропускает и входы, в названии которых есть «Домой». Так вход можно назвать красиво
(«🏠 Домой · российский IP» — это видно людям в приложении), а получат его только те, кто включил
«Домой» сам (кнопка в кабинете → home_optin). Людям в России с автовыбором сервера он не попадёт.

Копия перед изменением: inbounds.py.bak-homeoptin. Повторный запуск ничего не меняет.
После: systemctl restart yadreno-vpn

    python3 patch_home_optin.py           применить
    python3 patch_home_optin.py --undo    вернуть из копии
"""
import py_compile
import shutil
import sys
from pathlib import Path

PATH = Path("/root/YadrenoVPN/bot/utils/inbounds.py")
BAK = PATH.with_name(PATH.name + ".bak-homeoptin")
MARK = "Pamir: opt-in inbounds"

if "--undo" in sys.argv:
    if not BAK.exists():
        sys.exit("Копии нет — нечего возвращать.")
    shutil.copy2(BAK, PATH)
    sys.exit("Вернул из копии. Теперь: systemctl restart yadreno-vpn")

src = PATH.read_text(encoding="utf-8")
if MARK in src:
    sys.exit("Правка уже применена — ничего не меняю.")

OLD = '''    remark = inbound.get("remark") or ""
    return str(remark).lstrip().startswith(IGNORED_INBOUND_PREFIX)
'''
NEW = '''    remark = inbound.get("remark") or ""
    # Pamir: opt-in inbounds — «Домой» (российский IP) добавляется только тем, кто включил его сам
    if any(marker in str(remark) for marker in OPT_IN_INBOUND_MARKERS):
        return True
    return str(remark).lstrip().startswith(IGNORED_INBOUND_PREFIX)
'''
if src.count(OLD) != 1:
    sys.exit("Файл устроен иначе, чем ожидалось — ничего не меняю.")
src = src.replace(OLD, NEW)
src = src.replace('IGNORED_INBOUND_PREFIX = "--!"\n',
                  'IGNORED_INBOUND_PREFIX = "--!"\nOPT_IN_INBOUND_MARKERS = ("Домой",)  # Pamir: opt-in inbounds\n', 1)

shutil.copy2(PATH, BAK)
PATH.write_text(src, encoding="utf-8")
try:
    py_compile.compile(str(PATH), doraise=True)
except py_compile.PyCompileError as error:
    shutil.copy2(BAK, PATH)
    sys.exit(f"Ошибка в результате — вернул копию: {error}")
print("Готово. Теперь: systemctl restart yadreno-vpn")
