#!/usr/bin/env python3
"""Экран подписки на канал: анимации, «спасибо» после подписки и правильный порядок со шлюзом.

Что было: режим шлюза стоял в боте первым и перехватывал всё, кроме /start, — нажатие «Я подписался» не доходило
до проверки, человеку без подписки приходила карточка кабинета, а «спасибо» не было. Расширениям бота нельзя
ничего импортировать, кроме своего API, — поэтому анимации отправляет сам бот, а дополнение
custom_extensions/force_channel_sub.py не меняется (тексты — patch_channel_sub_texts.py).

Что делает скрипт (копии — /root/*.bak-channelsub2; проверка синтаксиса; при ошибке всё возвращается):
1. custom_extensions/media/ — анимации mognu-sub.mp4 и mognu-cabinet.mp4 (лежат рядом со скриптом).
2. bot/middlewares/user_access_guard.py — при отказе в доступе на сообщение: сначала анимация «Подпишись»
   (одному человеку не чаще раза в 10 минут), под ней текст с кнопками.
3. bot/handlers/user/extension_callbacks.py — «Я подписался» и подписка найдена: «🎉 Спасибо за подписку!»,
   экран подписки убирается, в режиме шлюза — карточка кабинета.
4б. bot/middlewares/gateway.py — карточка кабинета одним сообщением: анимация «Всё здесь», текст и кнопки.
4. bot/middlewares/gateway.py — шлюз пропускает кнопку «Я подписался» к проверке.
5. bot/handlers/user/__init__.py — проверка подписки раньше шлюза.

    python3 install_channel_sub.py            показать
    python3 install_channel_sub.py --apply    применить и перезапустить бота
"""
import os
import py_compile
import re
import shutil
import subprocess
import sys

ROOT = "/root/YadrenoVPN"
HERE = os.path.dirname(os.path.abspath(__file__))
MEDIA = f"{ROOT}/custom_extensions/media"
GUARD_MW = f"{ROOT}/bot/middlewares/user_access_guard.py"
EXT_CB = f"{ROOT}/bot/handlers/user/extension_callbacks.py"
GW = f"{ROOT}/bot/middlewares/gateway.py"
INIT = f"{ROOT}/bot/handlers/user/__init__.py"
BAK = "/root/{}.bak-channelsub2"
APPLY = "--apply" in sys.argv
MARK = "# Mognu: подписка на канал"

# ── 2. экран отказа: одно сообщение — анимация, текст подписью и кнопки ──
G_OLD = ("    if isinstance(event, Message):\n"
         "        await safe_edit_or_send(event, text, reply_markup=reply_markup, force_new=True)\n")
G_NEW = ("    if isinstance(event, Message):\n"
         "        if await _mognu_denied_animation(event, result, text, reply_markup):  " + MARK + " — анимация с текстом и кнопками\n"
         "            return\n"
         "        await safe_edit_or_send(event, text, reply_markup=reply_markup, force_new=True)\n")
# первая версия (анимация отдельным сообщением над текстом) — заменяется на новую
G_NEW_V1 = ("    if isinstance(event, Message):\n"
            "        await _mognu_denied_animation(event, result)  " + MARK + " — анимация «Подпишись»\n"
            "        await safe_edit_or_send(event, text, reply_markup=reply_markup, force_new=True)\n")
G_HELPER_V1_START = "\n\n" + MARK + ": анимация над экраном отказа"
G_HELPER = '''

''' + MARK + ''': экран отказа одним сообщением — анимация «Подпишись», текст подписью и кнопки под ней
_MOGNU_FILE_IDS: dict = {}


async def _mognu_denied_animation(event, result, text, reply_markup) -> bool:
    """True — отправили анимацию с текстом и кнопками; False — пусть бот пришлёт обычный текст."""
    from pathlib import Path
    from aiogram.types import FSInputFile
    try:
        if not any(str(b.get('url') or '').startswith('https://t.me/') for row in (result.buttons or []) for b in row):
            return False
        path = Path(__file__).resolve().parents[2] / 'custom_extensions' / 'media' / 'mognu-sub.mp4'
        if not path.exists() and str(path) not in _MOGNU_FILE_IDS:
            return False
        msg = await event.answer_animation(_MOGNU_FILE_IDS.get(str(path)) or FSInputFile(path), width=960, height=540,
                                           caption=text, reply_markup=reply_markup)
        if msg.animation:
            _MOGNU_FILE_IDS[str(path)] = msg.animation.file_id
        return True
    except Exception:
        return False
'''
G_ALL = "\n\n__all__ = ['UserAccessGuardMiddleware']"

# ── 3. «Я подписался»: анимация «Спасибо!» и карточка кабинета ──
C_OLD = "    result = await dispatch_extension_callback(context, bot=callback.bot)\n"
C_NEW = (C_OLD +
         "    " + MARK + ": подписка подтверждена — «Спасибо!» и карточка кабинета вместо голого меню\n"
         "    if parsed.get('action_name') == 'check' and 'channel_sub' in str(parsed.get('extension_id') or '') \\\n"
         "            and result.get('page_key') == 'main' and await _mognu_sub_thanks(callback):\n"
         "        return\n")
C_HELPER_START = "\n\n\nasync def _mognu_sub_thanks("
C_HELPER = '''


async def _mognu_sub_thanks(callback: CallbackQuery) -> bool:
    """''' + MARK[2:] + ''': «🎉 Спасибо за подписку!»; экран подписки убираем; в режиме шлюза — карточка кабинета
    (с анимацией «Всё здесь»). True — ответили сами; False — пусть бот покажет главную страницу как обычно."""
    uid = callback.from_user.id
    chat_id = callback.message.chat.id if callback.message else uid
    try:
        from bot.middlewares.gateway import gateway_enabled, send_gateway_card
        if not gateway_enabled():
            return False
    except Exception:
        return False
    try:
        await callback.answer('🎉 Спасибо за подписку!')
    except Exception:
        pass
    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass
    await send_gateway_card(callback.bot, chat_id, uid)
    return True
'''

# ── 4б. карточка кабинета (режим шлюза) — одним сообщением с анимацией «Всё здесь» ──
GW_SEND_OLD = "        msg = await bot.send_message(chat_id, text, reply_markup=kb, parse_mode='HTML')\n"
GW_SEND_NEW = "        msg = await _mognu_send_card(bot, chat_id, text, kb)  " + MARK + " — карточка с анимацией\n"
GW_ALL_RE = re.compile(r"\n\n__all__ = \[")
GW_HELPER = '''

''' + MARK + ''': карточка кабинета — анимация «Всё здесь», текст подписью и кнопки; нет анимации — как раньше
_MOGNU_CARD_FILE: dict = {}


async def _mognu_send_card(bot, chat_id, text, kb):
    from pathlib import Path
    from aiogram.types import FSInputFile
    path = Path(__file__).resolve().parents[2] / 'custom_extensions' / 'media' / 'mognu-cabinet.mp4'
    if path.exists() or 'f' in _MOGNU_CARD_FILE:
        try:
            msg = await bot.send_animation(chat_id, _MOGNU_CARD_FILE.get('f') or FSInputFile(path), caption=text,
                                           reply_markup=kb, parse_mode='HTML', width=960, height=540)
            if msg.animation:
                _MOGNU_CARD_FILE['f'] = msg.animation.file_id
            return msg
        except TelegramForbiddenError:
            raise
        except Exception:
            logger.warning('gateway: animated card failed for %s, sending text', chat_id, exc_info=True)
    return await bot.send_message(chat_id, text, reply_markup=kb, parse_mode='HTML')
'''

# ── 4. шлюз пропускает «Я подписался» ──
GW_RE = re.compile(r"^        return (event\.data == 'start'[^\n]*)\n", re.M)
GW_MARK = "# Mognu: кнопка «Я подписался»"
GW_TAIL = ("            return True\n"
           "        try:  " + GW_MARK + " (проверка подписки) — мимо шлюза, к самой проверке\n"
           "            from bot.utils.extension_callbacks import is_extension_access_check_callback\n"
           "            return bool(is_extension_access_check_callback(event.data))\n"
           "        except Exception:\n"
           "            return False\n")

# ── 5. проверка подписки раньше шлюза ──
GUARD = ("router.message.outer_middleware(UserAccessGuardMiddleware())\n"
         "router.callback_query.outer_middleware(UserAccessGuardMiddleware())\n")
GW_LINE = "# Pamir: режим шлюза — первым, до остальных фильтров\n"
GUARD_NEW = "# Mognu: проверка подписки — раньше шлюза (без подписки — экран подписки, а не кабинет)\n" + GUARD


def fail(what, cmd):
    sys.exit(f"{what} устроен иначе — ничего не меняю. Пришлите: {cmd}")


anims = [os.path.join(HERE, n) for n in ("mognu-sub.mp4", "mognu-cabinet.mp4")]
if any(not os.path.exists(a) for a in anims):
    sys.exit("Нет анимаций mognu-sub.mp4 / mognu-cabinet.mp4 рядом со скриптом.")

out = {}
s = open(GUARD_MW, encoding="utf-8").read()
if G_NEW_V1 in s and G_HELPER_V1_START in s:   # стоит первая версия — меняем на одно сообщение
    s = s.replace(G_NEW_V1, G_OLD)
    s = s[:s.index(G_HELPER_V1_START)] + s[s.index(G_ALL):]
if G_NEW in s:
    out[GUARD_MW] = s
elif s.count(G_OLD) == 1 and s.count(G_ALL) == 1:
    out[GUARD_MW] = s.replace(G_OLD, G_NEW).replace(G_ALL, G_HELPER + G_ALL)
else:
    fail("user_access_guard.py", f"tail -30 {GUARD_MW}")

s = open(EXT_CB, encoding="utf-8").read()
if C_NEW in s and C_HELPER_START in s and C_HELPER not in s:   # стоит прошлая версия «спасибо» — меняем
    s = s[:s.index(C_HELPER_START)].rstrip("\n") + C_HELPER
if C_NEW in s and C_HELPER in s:
    out[EXT_CB] = s
elif s.count(C_OLD) == 1:
    out[EXT_CB] = s.replace(C_OLD, C_NEW).rstrip("\n") + C_HELPER
else:
    fail("extension_callbacks.py", f"sed -n 20,50p {EXT_CB}")

s = open(GW, encoding="utf-8").read()
if GW_MARK not in s:
    if len(GW_RE.findall(s)) != 1:
        fail("gateway.py", f"grep -n 'event.data' {GW}")
    s = GW_RE.sub(lambda m: "        if " + m.group(1) + ":\n" + GW_TAIL, s)
if GW_SEND_NEW not in s:
    if s.count(GW_SEND_OLD) != 1 or len(GW_ALL_RE.findall(s)) != 1:
        fail("gateway.py (отправка карточки)", f"grep -n 'send_message\\|__all__' {GW}")
    s = s.replace(GW_SEND_OLD, GW_SEND_NEW)
    m = GW_ALL_RE.search(s)
    s = s[:m.start()] + GW_HELPER + s[m.start():]
out[GW] = s

s = open(INIT, encoding="utf-8").read()
if GUARD_NEW in s:
    out[INIT] = s
elif s.count(GUARD) == 1 and s.count(GW_LINE) == 1:
    out[INIT] = s.replace(GUARD, "").replace(GW_LINE, GUARD_NEW + GW_LINE)
else:
    fail("__init__.py", f"sed -n 18,32p {INIT}")

for path, text in out.items():
    print(os.path.relpath(path, ROOT) + ":", "уже исправлен" if text == open(path, encoding="utf-8").read() else "исправлю")
print("анимации → custom_extensions/media/")
if not APPLY:
    sys.exit("Это проверка. Применить: python3 install_channel_sub.py --apply")

for path in out:   # копия — только самая первая (до любых наших правок), повторный запуск её не затирает
    if not os.path.exists(BAK.format(os.path.basename(path))):
        shutil.copy2(path, BAK.format(os.path.basename(path)))
os.makedirs(MEDIA, exist_ok=True)
for a in anims:
    shutil.copy2(a, os.path.join(MEDIA, os.path.basename(a)))
try:
    for path, text in out.items():
        open(path, "w", encoding="utf-8").write(text)
        py_compile.compile(path, doraise=True)
except Exception as e:
    for path in out:
        shutil.copy2(BAK.format(os.path.basename(path)), path)
    sys.exit(f"Не прошло проверку — вернул файлы: {e}")
subprocess.run(["systemctl", "restart", "yadreno-vpn"], check=True)
print("Готово, бот перезапущен. Копии: /root/*.bak-channelsub2")
