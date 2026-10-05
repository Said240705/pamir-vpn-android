#!/usr/bin/env python3
"""Режим шлюза для всего бота, а не только для /start.

Сейчас режим шлюза перехватывает только /start и кнопку «На главную». Остальное
(любой текст, команды из меню бота, кнопки старых сообщений, промо-страница) ведёт
в старое меню. Правка:
- bot/middlewares/gateway.py — новый фильтр: при включённом режиме шлюза всё, что
  присылает не-админ, получает одну карточку кабинета. Пропускаются /start с любыми
  параметрами (вход в приложение/на сайт/в админку, оплата, промо, рефералы — их
  обрабатывает cmd_start как раньше), сами платежи и кнопка «На главную».
- bot/handlers/user/__init__.py — фильтр ставится первым, до остальных.
- bot/handlers/user/start.py — /start и «На главную» показывают ту же новую карточку.
Перед изменением копии: *.bak-gateway. Повторный запуск ничего не меняет.
"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/root/YadrenoVPN")
MW = ROOT / "bot/middlewares/gateway.py"
INIT = ROOT / "bot/handlers/user/__init__.py"
START = ROOT / "bot/handlers/user/start.py"

if MW.exists():
    sys.exit("Правка уже применена — ничего не меняю.")

MW_CODE = '''"""Pamir: режим шлюза для всего бота.

Когда режим шлюза включён (админка → «🔒 Режим шлюза»), не-админ на любое сообщение,
команду или кнопку получает одну карточку личного кабинета. Пропускаются:
- /start с любыми параметрами — его обрабатывает cmd_start: вход в приложение, на сайт
  и в веб-админку, ссылки оплаты, промо и рефералы работают как раньше;
- платежи (successful_payment и т.п.) и кнопка «На главную» (callback "start");
- сообщения не из личного чата.
Прежняя карточка удаляется, чтобы в чате была одна.
"""
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message, TelegramObject, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS

logger = logging.getLogger(__name__)

CABINET_URL = 'https://app.pamirlink.ru/index.html'
ANDROID_URL = 'https://app.pamirlink.ru/welcome.html'
IPHONE_URL = 'https://app.pamirlink.ru/iphone.html'

# chat_id -> id последней карточки (в памяти: после перезапуска бота старая просто останется)
_last_card: Dict[int, int] = {}


def gateway_enabled() -> bool:
    from database.requests import get_setting
    return str(get_setting('gateway_mode_enabled', '0') or '0').strip() == '1'


def _card():
    text = (
        "<b>Pamir VPN</b> 🏔\\n\\n"
        "Всё управление — в личном кабинете: подписка и оплата, "
        "ключи и устройства, поддержка.\\n\\n"
        "Открывается прямо здесь, в Telegram 👇"
    )
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text='🔒 Открыть личный кабинет', web_app=WebAppInfo(url=CABINET_URL)))
    b.row(
        InlineKeyboardButton(text='📱 Android', url=ANDROID_URL),
        InlineKeyboardButton(text='🍏 iPhone', url=IPHONE_URL),
    )
    return text, b.as_markup()


async def send_gateway_card(bot, chat_id: int, user_id: int) -> None:
    text, kb = _card()
    old = _last_card.pop(chat_id, None)
    if old:
        try:
            await bot.delete_message(chat_id, old)
        except Exception:
            pass
    try:
        msg = await bot.send_message(chat_id, text, reply_markup=kb, parse_mode='HTML')
        _last_card[chat_id] = msg.message_id
    except TelegramForbiddenError:
        logger.warning('gateway: user %s blocked the bot', user_id)
    except Exception:
        logger.exception('gateway: failed to send the card to %s', user_id)


def _passes(event: TelegramObject) -> bool:
    if isinstance(event, Message):
        if event.chat is not None and event.chat.type != 'private':
            return True
        if event.successful_payment or getattr(event, 'refunded_payment', None):
            return True
        text = (event.text or '').strip()
        return text == '/start' or text.startswith('/start ') or text.startswith('/start@')
    if isinstance(event, CallbackQuery):
        return event.data == 'start'
    return True


class GatewayModeMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get('event_from_user')
        if user is None or getattr(user, 'is_bot', False) or user.id in ADMIN_IDS or _passes(event):
            return await handler(event, data)
        try:
            enabled = gateway_enabled()
        except Exception:
            logger.exception('gateway: cannot read the setting')
            enabled = False
        if not enabled:
            return await handler(event, data)

        bot = data.get('bot')
        if isinstance(event, CallbackQuery):
            try:
                await event.answer()
            except Exception:
                pass
            chat_id = event.message.chat.id if event.message else user.id
        else:
            chat_id = event.chat.id
        await send_gateway_card(bot, chat_id, user.id)
        return None


__all__ = ['GatewayModeMiddleware', 'send_gateway_card', 'gateway_enabled']
'''

init = INIT.read_text(encoding="utf-8")
anchor = "router = Router()\nrouter.message.outer_middleware(ResetAdminPageContextMiddleware())\n"
if init.count(anchor) != 1:
    sys.exit("Не нашёл место в bot/handlers/user/__init__.py — ничего не меняю.")
init = init.replace(anchor,
    "router = Router()\n"
    "# Pamir: режим шлюза — первым, до остальных фильтров\n"
    "from bot.middlewares.gateway import GatewayModeMiddleware\n"
    "router.message.outer_middleware(GatewayModeMiddleware())\n"
    "router.callback_query.outer_middleware(GatewayModeMiddleware())\n"
    "router.message.outer_middleware(ResetAdminPageContextMiddleware())\n")

start = START.read_text(encoding="utf-8")
COND = r"    if user_id not in ADMIN_IDS and str\(get_setting\('gateway_mode_enabled', '0'\) or '0'\)\.strip\(\) == '1':\n"
blocks = list(re.finditer(COND + r"(?:.*\n)*?        return\n", start))
if len(blocks) != 2:
    sys.exit(f"В start.py ожидал 2 блока режима шлюза, нашёл {len(blocks)} — ничего не меняю.")
cond_line = "    if user_id not in ADMIN_IDS and str(get_setting('gateway_mode_enabled', '0') or '0').strip() == '1':\n"
new_cmd = (cond_line +
    "        from bot.middlewares.gateway import send_gateway_card\n"
    "        await send_gateway_card(message.bot, message.chat.id, user_id)\n"
    "        return\n")
new_cb = (cond_line +
    "        from bot.middlewares.gateway import send_gateway_card\n"
    "        await send_gateway_card(callback.bot, callback.message.chat.id if callback.message else user_id, user_id)\n"
    "        await callback.answer()\n"
    "        return\n")
b1, b2 = blocks
if "message.answer(" not in b1.group(0) or "callback.message.answer(" not in b2.group(0):
    sys.exit("Блоки режима шлюза в start.py не такие, как ожидал — ничего не меняю.")
start = start[:b1.start()] + new_cmd + start[b1.end():b2.start()] + new_cb + start[b2.end():]

for p in (INIT, START):
    shutil.copy2(p, p.with_name(p.name + ".bak-gateway"))
MW.write_text(MW_CODE, encoding="utf-8")
INIT.write_text(init, encoding="utf-8")
START.write_text(start, encoding="utf-8")
print("Готово. Копии: __init__.py.bak-gateway, start.py.bak-gateway; новый файл bot/middlewares/gateway.py")
