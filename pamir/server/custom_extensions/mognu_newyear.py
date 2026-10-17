# -*- coding: utf-8 -*-
"""Новогодняя скидка Mognu: годовые тарифы дешевле на 25% с 20 декабря по 10 января (по Москве).

Цену при оплате считает бот (pricing policy), поэтому скидка одинакова для всех способов оплаты: в боте,
в кабинете и с баланса. С промокодом не складывается: человек платит по той скидке, что больше.
До начала акции её видят только Telegram ID из настройки «Видят заранее» — для проверки.
Список тарифов показывает зачёркнутую цену через ту же политику (patch_newyear_prices.py).

Ставится в /root/YadrenoVPN/custom_extensions/, включается и настраивается в админке бота → Расширения.
"""
from __future__ import annotations

import datetime
import logging

from bot.utils.custom_extensions import (
    get_core_api,
    get_extension_config,
    register_extension_settings,
    register_pricing_policy,
)

logger = logging.getLogger(__name__)

MSK = datetime.timezone(datetime.timedelta(hours=3))

register_extension_settings(fields=[
    {
        'key': 'enabled',
        'type': 'bool',
        'label': 'Новогодняя скидка включена',
        'required': True,
        'default': True,
        'help': 'Главный выключатель. Даже включённая, скидка действует только в даты акции.',
    },
    {
        'key': 'percent',
        'type': 'int',
        'label': 'Скидка, %',
        'required': True,
        'default': 25,
        'help': 'На сколько процентов дешевле годовые тарифы (от 1 до 90).',
    },
    {
        'key': 'min_days',
        'type': 'int',
        'label': 'Тарифы от скольких дней',
        'required': True,
        'default': 360,
        'help': 'Скидка действует на тарифы не короче этого срока (360 — годовые).',
    },
    {
        'key': 'start',
        'type': 'text',
        'label': 'Начало акции (ГГГГ-ММ-ДД, по Москве)',
        'required': True,
        'default': '2026-12-20',
    },
    {
        'key': 'end',
        'type': 'text',
        'label': 'Последний день акции (ГГГГ-ММ-ДД, включительно)',
        'required': True,
        'default': '2027-01-10',
    },
    {
        'key': 'preview_telegram_ids',
        'type': 'text',
        'label': 'Видят заранее (Telegram ID через запятую)',
        'required': False,
        'default': '',
        'help': 'Этим людям скидка действует и до начала акции — чтобы проверить. После акции не действует ни у кого.',
    },
])


def _date(value, fallback: datetime.date) -> datetime.date:
    try:
        return datetime.date.fromisoformat(str(value).strip())
    except Exception:
        return fallback


def _preview_user_ids(config: dict) -> set[int]:
    """Internal user ids of the preview Telegram IDs (the pricing context carries the internal id)."""
    ids: set[int] = set()
    raw = str(config.get('preview_telegram_ids') or '')
    if not raw.strip():
        return ids
    core = get_core_api()
    for part in raw.replace(';', ',').split(','):
        part = part.strip()
        if not part.isdigit():
            continue
        try:
            user = core.get_user_by_telegram_id(int(part))
        except Exception:
            logger.warning('mognu_newyear: preview lookup failed for one Telegram ID')
            continue
        if user and user.get('id'):
            ids.add(int(user['id']))
    return ids


def season_state(config: dict, user_id: int | None, now: datetime.datetime | None = None) -> str | None:
    """'on' during the sale, 'preview' for preview users before it starts, None otherwise."""
    if not config.get('enabled'):
        return None
    today = (now or datetime.datetime.now(MSK)).astimezone(MSK).date()
    start = _date(config.get('start'), datetime.date(2026, 12, 20))
    end = _date(config.get('end'), datetime.date(2027, 1, 10))
    if start <= today <= end:
        return 'on'
    if today < start and user_id and int(user_id) in _preview_user_ids(config):
        return 'preview'
    return None


def newyear_price(context: dict) -> dict | None:
    """Pricing policy: −N% on long tariffs during the New Year sale; a bigger promo discount wins."""
    config = get_extension_config()
    tariff = dict(context.get('tariff') or {})
    try:
        days = int(tariff.get('duration_days') or 0)
    except (TypeError, ValueError):
        return None
    if days < int(config.get('min_days') or 360):
        return None
    state = season_state(config, context.get('user_id'))
    if not state:
        return None
    percent = max(1, min(90, int(config.get('percent') or 25)))
    quote = dict(context.get('quote') or {})
    original = int(quote.get('original_amount') or 0)
    current = int(quote.get('final_amount') if quote.get('final_amount') is not None else original)
    if original <= 0:
        return None
    target = original - original * percent // 100
    if current <= target:
        return None   # the promo code already gives as much or more
    end = _date(config.get('end'), datetime.date(2027, 1, 10))
    return {
        'final_amount': target,
        'label': f'🎄 Новогодняя скидка −{percent}%',
        'metadata': {'percent': percent, 'until': end.isoformat(), 'state': state},
    }


register_pricing_policy('ext_mognu_newyear', newyear_price)
