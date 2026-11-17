#!/usr/bin/env python3
"""Экран подписки на канал: анимации, «спасибо» после подписки и правильный порядок со шлюзом.

Что было: режим шлюза стоял в боте первым и перехватывал всё, кроме /start, — нажатие «Я подписался» не доходило
до проверки, человеку без подписки приходила карточка кабинета, а «спасибо» не было.

Что делает скрипт (копии всех файлов — *.bak-channelsub в /root; проверка синтаксиса; при ошибке всё возвращается):
1. custom_extensions/force_channel_sub.py — новая версия (force_channel_sub.py рядом со скриптом): без подписки —
   анимация «Подпишись» и текст с кнопками; после «Я подписался» — анимация «Спасибо!» и карточка кабинета.
2. custom_extensions/media/ — анимации mognu-sub.mp4 и mognu-thanks.mp4 (лежат рядом со скриптом).
3. bot/middlewares/gateway.py — шлюз пропускает кнопку «Я подписался» к проверке.
4. bot/handlers/user/__init__.py — проверка подписки раньше шлюза: без подписки — экран подписки, а не кабинет.

    python3 install_channel_sub.py            показать
    python3 install_channel_sub.py --apply    применить и перезапустить бота
"""
import os
import py_compile
import shutil
import subprocess
import sys

ROOT = "/root/YadrenoVPN"
HERE = os.path.dirname(os.path.abspath(__file__))
EXT = f"{ROOT}/custom_extensions/force_channel_sub.py"
MEDIA = f"{ROOT}/custom_extensions/media"
GW = f"{ROOT}/bot/middlewares/gateway.py"
INIT = f"{ROOT}/bot/handlers/user/__init__.py"
CFG = f"{ROOT}/config.py"
APPLY = "--apply" in sys.argv

GW_OLD = "        return event.data == 'start'\n"
GW_NEW = ("        if event.data == 'start':\n"
          "            return True\n"
          "        try:  # Mognu: кнопка «Я подписался» (проверка подписки) — мимо шлюза, к самой проверке\n"
          "            from bot.utils.extension_callbacks import is_extension_access_check_callback\n"
          "            return bool(is_extension_access_check_callback(event.data))\n"
          "        except Exception:\n"
          "            return False\n")
GUARD = ("router.message.outer_middleware(UserAccessGuardMiddleware())\n"
         "router.callback_query.outer_middleware(UserAccessGuardMiddleware())\n")
GW_MARK = "# Pamir: режим шлюза — первым, до остальных фильтров\n"
GUARD_NEW = "# Mognu: проверка подписки — раньше шлюза (без подписки — экран подписки, а не кабинет)\n" + GUARD

src_ext = open(os.path.join(HERE, "force_channel_sub.py"), encoding="utf-8").read()
anims = [os.path.join(HERE, n) for n in ("mognu-sub.mp4", "mognu-thanks.mp4")]
missing = [a for a in anims if not os.path.exists(a)]
if missing:
    sys.exit("Нет анимаций рядом со скриптом: " + ", ".join(os.path.basename(m) for m in missing))
if "BOT_TOKEN" not in open(CFG, encoding="utf-8").read():
    sys.exit("В config.py бота нет BOT_TOKEN — ничего не меняю.")

gw = open(GW, encoding="utf-8").read()
if GW_NEW in gw:
    gw_new = gw
elif gw.count(GW_OLD) == 1:
    gw_new = gw.replace(GW_OLD, GW_NEW)
else:
    sys.exit("gateway.py устроен иначе — ничего не меняю. Пришлите: grep -n \"event.data\" " + GW)

init = open(INIT, encoding="utf-8").read()
if GUARD_NEW in init:
    init_new = init
elif init.count(GUARD) == 1 and init.count(GW_MARK) == 1:
    init_new = init.replace(GUARD, "").replace(GW_MARK, GUARD_NEW + GW_MARK)
else:
    sys.exit("__init__.py устроен иначе — ничего не меняю. Пришлите: sed -n 18,32p " + INIT)

ext_same = os.path.exists(EXT) and open(EXT, encoding="utf-8").read() == src_ext
print("1. force_channel_sub.py:", "уже новый" if ext_same else "заменю на новый")
print("2. анимации → custom_extensions/media/")
print("3. gateway.py:", "уже пропускает «Я подписался»" if gw_new == gw else "пропущу «Я подписался» к проверке")
print("4. __init__.py:", "проверка уже раньше шлюза" if init_new == init else "проверка подписки — раньше шлюза")
if not APPLY:
    sys.exit("Это проверка. Применить: python3 install_channel_sub.py --apply")

files = [(EXT, src_ext), (GW, gw_new), (INIT, init_new)]
for path, _ in files:
    if os.path.exists(path):
        shutil.copy2(path, "/root/" + os.path.basename(path) + ".bak-channelsub")
os.makedirs(MEDIA, exist_ok=True)
for a in anims:
    shutil.copy2(a, os.path.join(MEDIA, os.path.basename(a)))
try:
    for path, text in files:
        open(path, "w", encoding="utf-8").write(text)
        py_compile.compile(path, doraise=True)
except Exception as e:
    for path, _ in files:
        bak = "/root/" + os.path.basename(path) + ".bak-channelsub"
        if os.path.exists(bak):
            shutil.copy2(bak, path)
    sys.exit(f"Не прошло проверку — вернул файлы: {e}")
subprocess.run(["systemctl", "restart", "yadreno-vpn"], check=True)
print("Готово, бот перезапущен. Копии: /root/*.bak-channelsub")
