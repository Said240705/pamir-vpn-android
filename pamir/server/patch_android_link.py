#!/usr/bin/env python3
"""Кнопка «📱 Android» в карточке бота ведёт на новую страницу приложения (android.html), а не на лендинг.

    python3 patch_android_link.py          показать, что изменится (ничего не меняет)
    python3 patch_android_link.py --apply  применить; копия: gateway.py.bak-androidlink
Потом: systemctl restart yadreno-vpn
"""
import os
import py_compile
import re
import shutil
import sys
from pathlib import Path

PATH = Path(os.getenv("PAMIR_GATEWAY", "/root/YadrenoVPN/bot/middlewares/gateway.py"))
APPLY = "--apply" in sys.argv
NEW = "ANDROID_URL = 'https://mognu.app/android.html'"
LINE = re.compile(r"^ANDROID_URL = ['\"]https://[\w.-]+/welcome\.html['\"]$", re.M)

src = PATH.read_text(encoding="utf-8")
if NEW in src:
    sys.exit("Кнопка уже ведёт на android.html — ничего не меняю.")
found = LINE.findall(src)
if len(found) != 1:
    sys.exit("Не нашёл строку ANDROID_URL в ожидаемом виде — ничего не меняю.")
print(("ПРИМЕНЯЮ: " if APPLY else "ИЗМЕНИТСЯ: ") + f"{found[0]}  →  {NEW}")
if not APPLY:
    sys.exit("Это был просмотр. Чтобы применить: python3 patch_android_link.py --apply")
backup = PATH.with_name(PATH.name + ".bak-androidlink")
shutil.copy2(PATH, backup)
PATH.write_text(LINE.sub(NEW, src, count=1), encoding="utf-8")
try:
    py_compile.compile(str(PATH), doraise=True)
except py_compile.PyCompileError as error:
    shutil.copy2(backup, PATH)
    sys.exit(f"Ошибка синтаксиса, вернул копию: {error}")
print(f"Готово (копия: {backup}). Перезапустите бота: systemctl restart yadreno-vpn")
