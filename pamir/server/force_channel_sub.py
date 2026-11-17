# -*- coding: utf-8 -*-
"""Обязательная подписка на Telegram-канал для доступа к боту (Mognu).

Без подписки — анимация «Подпишись» и под ней текст с кнопками. После «Я подписался» — анимация «Спасибо!»
и карточка кабинета (в режиме шлюза) или главная страница бота. Анимации — media/ рядом с файлом;
нет файла — просто текст, как раньше. Ставится скриптом install_channel_sub.py.
"""
from __future__ import annotations

import logging
import os
import time

from bot.utils.custom_extensions import (
    build_callback_data,
    get_core_api,
    get_extension_config,
    register_callback_handler,
    register_extension_settings,
    register_user_access_guard,
)

logger = logging.getLogger(__name__)

DENIED_TEXT = (
    '👑 Почти готово!\n\n'
    '📢 Подпишитесь на канал Mognu — там новости серверов, подсказки и акции.\n'
    '✅ Подписались? Нажмите «Я подписался» — и бот откроется.'
)
THANKS_TEXT = '🎉 Спасибо, вы с нами!'
MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'media')
SUB_ANIM = os.path.join(MEDIA_DIR, 'mognu-sub.mp4')
THANKS_ANIM = os.path.join(MEDIA_DIR, 'mognu-thanks.mp4')
SUB_ANIM_EVERY = 600          # анимацию «Подпишись» одному человеку — не чаще раза в 10 минут
_file_ids: dict = {}          # путь → file_id в Telegram (после первой отправки файл не загружается заново)
_sub_shown: dict = {}         # telegram_id → когда показали анимацию «Подпишись»

register_extension_settings(fields=[
    {
        'key': 'enabled',
        'type': 'bool',
        'label': 'Проверка подписки включена',
        'required': True,
        'default': True,
        'help': 'Если выключено, бот работает без проверки подписки на канал.',
    },
    {
        'key': 'channel',
        'type': 'text',
        'label': 'Канал (@username или числовой ID)',
        'required': True,
        'default': '@pamir_link',
        'help': 'Юзернейм канала или числовой ID вида -100…',
    },
    {
        'key': 'subscribe_url',
        'type': 'url',
        'label': 'Ссылка для кнопки «Подписаться на канал»',
        'required': True,
        'default': 'https://t.me/pamir_link',
    },
    {
        'key': 'fail_open_on_check_error',
        'type': 'bool',
        'label': 'Пропускать пользователей при ошибке проверки',
        'required': True,
        'default': True,
        'help': 'Если Telegram не отвечает или бот потерял права администратора в канале — пропускать пользователей вместо блокировки бота.',
    },
])


async def _check_membership(context: dict) -> dict:
    config = get_extension_config()
    core = get_core_api()
    return await core.check_telegram_chat_member(
        chat_id=config['channel'],
        telegram_id=context['telegram_id'],
    )


async def _send_anim(bot, chat_id: int, path: str) -> None:
    """Анимация без звука; повторно — по file_id, без загрузки. Ошибка не мешает основному ответу."""
    if not os.path.exists(path) and path not in _file_ids:
        return
    try:
        from aiogram.types import FSInputFile
        msg = await bot.send_animation(chat_id, animation=_file_ids.get(path) or FSInputFile(path), width=960, height=540)
        if path not in _file_ids and getattr(msg, 'animation', None):
            _file_ids[path] = msg.animation.file_id
    except Exception:
        logger.warning('force_channel_sub: animation not sent to %s', chat_id, exc_info=True)


async def _bot_call(fn):
    """Бот из ядра, а если ядро его не отдаёт — отдельное подключение с тем же токеном."""
    core = get_core_api()
    bot = getattr(core, 'bot', None) or getattr(core, '_bot', None)
    own = None
    if bot is None:
        from aiogram import Bot
        from config import BOT_TOKEN
        bot = own = Bot(token=BOT_TOKEN)
    try:
        return await fn(bot)
    finally:
        if own is not None:
            await own.session.close()


async def channel_subscribe_guard(target_event, context_mapping: dict) -> dict:
    context = dict(context_mapping)
    try:
        config = get_extension_config()
        if not config.get('enabled'):
            return {'allowed': True}
        if not config.get('channel'):
            return {'allowed': True}
        result = await _check_membership(context)
    except Exception:
        logger.exception('force_channel_sub: guard check failed, allowing user')
        return {'allowed': True}

    if result.get('is_member'):
        return {'allowed': True}

    reason = str(result.get('reason') or '')
    if config.get('fail_open_on_check_error') and reason != '':
        logger.warning(
            'force_channel_sub: membership check error (reason=%s), allowing user %s',
            reason,
            context.get('telegram_id'),
        )
        return {'allowed': True}

    # анимация над экраном подписки — на сообщения (/start и т.п.), не чаще раза в 10 минут
    tid = context.get('telegram_id')
    if context.get('event_type') == 'message' and tid and time.time() - _sub_shown.get(tid, 0) > SUB_ANIM_EVERY:
        bot = getattr(target_event, 'bot', None)
        chat = getattr(target_event, 'chat', None)
        if bot is not None and chat is not None and getattr(chat, 'type', '') == 'private':
            _sub_shown[tid] = time.time()
            await _send_anim(bot, chat.id, SUB_ANIM)

    return {
        'allowed': False,
        'message': DENIED_TEXT,
        'show_alert': False,
        'buttons': [
            [{'label': '📢 Подписаться на канал', 'url': config.get('subscribe_url') or 'https://t.me/pamir_link'}],
            [{'label': '✅ Я подписался', 'callback_data': build_callback_data('check')}],
        ],
    }


register_user_access_guard('ext_force_channel_sub', channel_subscribe_guard)


def _gateway():
    try:
        from bot.middlewares.gateway import gateway_enabled, send_gateway_card
        return send_gateway_card if gateway_enabled() else None
    except Exception:
        return None


async def check_subscription_callback(context: dict) -> dict:
    telegram_id = context.get('telegram_id')
    try:
        result = await _check_membership({'telegram_id': telegram_id})
    except Exception:
        logger.exception('force_channel_sub: check callback failed')
        return {'answer_text': '⏳ Не получилось проверить — попробуйте ещё раз через минуту.', 'show_alert': True}

    if result.get('is_member'):
        _sub_shown.pop(telegram_id, None)
        card = _gateway()

        async def thanks(bot):
            await _send_anim(bot, telegram_id, THANKS_ANIM)
            if card:
                await card(bot, telegram_id, telegram_id)

        try:
            await _bot_call(thanks)
        except Exception:
            logger.warning('force_channel_sub: thanks not sent to %s', telegram_id, exc_info=True)
        if card:
            return {'answer_text': THANKS_TEXT, 'show_alert': False}
        return {'page_key': 'main'}

    reason = str(result.get('reason') or '')
    config = get_extension_config()
    if reason != '' and config.get('fail_open_on_check_error'):
        return {'answer_text': '⏳ Не получилось проверить — попробуйте ещё раз через минуту.', 'show_alert': True}
    if reason == 'bot_has_no_access':
        return {'answer_text': 'Не удалось проверить подписку: у бота нет прав администратора в канале. Обратитесь в поддержку.', 'show_alert': True}
    return {'answer_text': '🙈 Пока не вижу подписки. Подпишитесь на канал и нажмите «Я подписался» ещё раз.', 'show_alert': True}


register_callback_handler('check', check_subscription_callback, bypass_user_access_guard=True)
