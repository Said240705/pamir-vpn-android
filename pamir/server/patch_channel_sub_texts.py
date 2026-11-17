#!/usr/bin/env python3
"""Экран «подпишитесь на канал» в боте: живые тексты и кнопки с эмодзи вместо «Доступ ограничен».

Меняет только строки в дополнении бота custom_extensions/force_channel_sub.py; логика проверки та же.
Копия — /root/force_channel_sub.py.bak-texts; проверка синтаксиса — при ошибке файл возвращается.
Повторный запуск ничего не меняет.

    python3 patch_channel_sub_texts.py            показать
    python3 patch_channel_sub_texts.py --apply    применить и перезапустить бота
"""
import py_compile
import shutil
import subprocess
import sys

F = "/root/YadrenoVPN/custom_extensions/force_channel_sub.py"
BAK = "/root/force_channel_sub.py.bak-texts"
REPL = [
    ("""DENIED_TEXT = (
    'Доступ ограничен\\n\\n'
    'Чтобы пользоваться ботом, нужно подписаться на наш канал. '
    'После подписки нажмите кнопку Проверить подписку.'
)""",
     """DENIED_TEXT = (
    '👑 Почти готово!\\n\\n'
    '📢 Подпишитесь на канал Mognu — там новости серверов, подсказки и акции.\\n'
    '✅ Подписались? Нажмите «Я подписался» — и бот откроется.'
)"""),
    ("[{'label': 'Подписаться на канал', 'url':", "[{'label': '📢 Подписаться на канал', 'url':"),
    ("[{'label': 'Проверить подписку', 'callback_data':", "[{'label': '✅ Я подписался', 'callback_data':"),
    ("""    if result.get('is_member'):
        return {'page_key': 'main'}""",
     """    if result.get('is_member'):
        return {'page_key': 'main', 'answer_text': '🎉 Готово, добро пожаловать!'}"""),
    ("'Подписка не найдена. Подпишитесь на канал и нажмите кнопку ещё раз.'",
     "'🙈 Пока не вижу подписки. Подпишитесь на канал и нажмите «Я подписался» ещё раз.'"),
]

s = open(F, encoding="utf-8").read()
new = s
missing = []
for old, rep in REPL:
    if rep in new:
        continue
    if new.count(old) != 1:
        missing.append(old.splitlines()[0][:60])
        continue
    new = new.replace(old, rep)
if missing:
    sys.exit("Не нашёл в файле: " + " | ".join(missing) + " — ничего не меняю. Пришлите: cat " + F)
if new == s:
    sys.exit("Уже стоит — менять нечего.")
print("будет: «👑 Почти готово!», кнопки «📢 Подписаться на канал» и «✅ Я подписался», «🎉 Готово» после проверки")
if "--apply" not in sys.argv:
    sys.exit("Это проверка. Применить: python3 patch_channel_sub_texts.py --apply")
shutil.copy2(F, BAK)
open(F, "w", encoding="utf-8").write(new)
try:
    py_compile.compile(F, doraise=True)
except py_compile.PyCompileError as e:
    shutil.copy2(BAK, F)
    sys.exit(f"Синтаксис не прошёл — вернул файл: {e}")
subprocess.run(["systemctl", "restart", "yadreno-vpn"], check=True)
print("Готово, бот перезапущен. Копия:", BAK)
