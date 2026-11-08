#!/usr/bin/env python3
"""«🏠 Домой» по желанию, часть 2: сверка ключей бота тоже не добавляет вход «Домой» сама.

patch_home_optin.py научил пропускать «Домой» функцию is_ignored_inbound, но сверка ключей с панелью
(sync_key_to_panel_state, provision_client) берёт список входов через build_inbound_descriptor,
а там признак «пропустить» проверял только «--!» в начале названия. Из-за этого сверка привязывала
«Домой» всем, у кого его не было, в том числе сразу после выключения кнопкой в кабинете.

Меняет bot/services/panels/base.py: вход с «Домой» в названии помечается ignored. Тех, кто включил
«Домой» сам, сверка не отвязывает (она только добавляет недостающие входы), а исполнитель кнопки
(home_optin.py) привязывает вход напрямую — кнопка работает как раньше.

Копия перед изменением: base.py.bak-homedescr. Повторный запуск ничего не меняет.
После: systemctl restart yadreno-vpn

    python3 patch_home_descriptor.py           применить
    python3 patch_home_descriptor.py --undo    вернуть из копии
"""
import py_compile
import re
import shutil
import sys
from pathlib import Path

ROOT = Path("/root/YadrenoVPN")
PATH = ROOT / "bot/services/panels/base.py"
BAK = PATH.with_name(PATH.name + ".bak-homedescr")
MARK = "Pamir: opt-in inbounds"

if "--undo" in sys.argv:
    if not BAK.exists():
        sys.exit("Копии нет — нечего возвращать.")
    shutil.copy2(BAK, PATH)
    sys.exit("Вернул из копии. Теперь: systemctl restart yadreno-vpn")

src = PATH.read_text(encoding="utf-8")
if MARK in src:
    print("Правка уже применена — ничего не меняю.")
else:
    OLD = '        ignored=remark.lstrip().startswith("--!"),\n'
    NEW = ('        # Pamir: opt-in inbounds — «Домой» (российский IP) только тем, кто включил его сам\n'
           '        ignored=remark.lstrip().startswith("--!") or "Домой" in remark,\n')
    if src.count(OLD) != 1:
        sys.exit("Файл устроен иначе, чем ожидалось — ничего не меняю.")
    shutil.copy2(PATH, BAK)
    PATH.write_text(src.replace(OLD, NEW), encoding="utf-8")
    try:
        py_compile.compile(str(PATH), doraise=True)
    except py_compile.PyCompileError as error:
        shutil.copy2(BAK, PATH)
        sys.exit(f"Ошибка в результате — вернул копию: {error}")
    print("Готово. Теперь: systemctl restart yadreno-vpn")

# Другие места, где «пропустить вход» проверяется только по «--!» — их правка не закрывает
other = []
for f in (ROOT / "bot").rglob("*.py"):
    if f == PATH:
        continue
    for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if re.search(r"""startswith\(\s*["']--!""", line):
            other.append(f"{f.relative_to(ROOT)}:{n}: {line.strip()}")
if other:
    print("Внимание, ещё проверки только по «--!» (пришлите этот список):")
    print("\n".join(other))
