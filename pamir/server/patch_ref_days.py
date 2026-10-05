#!/usr/bin/env python3
"""«Приведи друга»: первая оплата приглашённого — +7 дней ему и пригласившему.

Меняет bot/services/billing.py, функцию process_referral_reward (начисление рефералам
после оплаты, вызывается один раз на заказ):
- если у плательщика есть пригласивший и это его первая оплата по приглашению —
  оба получают PAMIR_REF_DAYS дней к активному ключу (штатная функция бота,
  повторно по тому же заказу не начисляет);
- следующие оплаты того же друга ничего не начисляют;
- оплаты с баланса, пробные и бесплатные по промокоду не считаются (как и раньше).
PAMIR_REF_DAYS = 0 в billing.py возвращает прежнюю схему (проценты из настроек).
Копия перед изменением: billing.py.bak-refdays. Повторный запуск ничего не меняет.
"""
import shutil
import sys
from pathlib import Path

PATH = Path(sys.argv[1] if len(sys.argv) > 1 else "/root/YadrenoVPN/bot/services/billing.py")
src = PATH.read_text(encoding="utf-8")
if "PAMIR_REF_DAYS" in src:
    sys.exit("Правка уже применена — ничего не меняю.")

HELPER = '''# --- Pamir: «Приведи друга» ---
# Первая оплата приглашённого: +PAMIR_REF_DAYS дней ему и пригласившему (1-й уровень),
# следующие оплаты ничего не начисляют. 0 — прежняя схема (проценты из настроек рефералки).
PAMIR_REF_DAYS = 7


async def _pamir_ref_days(
    payer_id: int,
    order: Dict[str, Any],
    payment_order_id: str,
    *,
    period_days: int,
    amount_minor: int,
    amount_base_minor: int,
    base_currency: str,
    payment_type: str,
) -> list[Dict[str, Any]]:
    referrer_id = get_user_referrer(payer_id)
    if not referrer_id:
        return []
    from database.connection import get_db

    with get_db() as conn:
        earlier = conn.execute(
            "SELECT 1 FROM payment_referral_effects "
            "WHERE payer_id = ? AND level = 1 AND order_id != ? LIMIT 1",
            (payer_id, payment_order_id),
        ).fetchone()
    if earlier:
        return []

    from bot.services.rewards import grant_days_to_first_active_key

    metadata = {
        'payer_id': payer_id,
        'level': 1,
        'payment_type': payment_type,
        'reward_policy': 'pamir_ref_days',
    }
    granted: Dict[int, bool] = {}
    for user_id, reference_id, reason in (
        (referrer_id, f'{payment_order_id}:1', 'Приведи друга: друг оформил подписку'),
        (payer_id, f'{payment_order_id}:friend', 'Приведи друга: подписка по приглашению'),
    ):
        try:
            result = await grant_days_to_first_active_key(
                user_id,
                PAMIR_REF_DAYS,
                source='referral_reward',
                reason=reason,
                reference_type='payment_referral',
                reference_id=reference_id,
                metadata=metadata,
            )
            granted[user_id] = bool(result.get('ok'))
            if not result.get('ok'):
                logger.warning('Pamir ref days: user %s order %s: %s', user_id, payment_order_id, result.get('reason'))
        except Exception as error:
            logger.warning('Pamir ref days: user %s order %s failed: %s', user_id, payment_order_id, error)
            granted[user_id] = False

    reward_days = PAMIR_REF_DAYS if granted.get(referrer_id) else 0
    from database.requests import record_payment_referral_stat_once

    record_payment_referral_stat_once(
        payment_order_id,
        level=1,
        referrer_id=referrer_id,
        payer_id=payer_id,
        reward_minor=0,
        reward_days=reward_days,
        reward_currency=base_currency,
    )
    logger.info(
        'Pamir ref days: order %s payer %s referrer %s +%s days (referrer %s, friend %s)',
        payment_order_id, payer_id, referrer_id, PAMIR_REF_DAYS,
        granted.get(referrer_id), granted.get(payer_id),
    )
    return [{
        'referrer_id': referrer_id,
        'payer_id': payer_id,
        'level': 1,
        'reward_type': 'days',
        'reward_cents': 0,
        'reward_minor': 0,
        'reward_currency': base_currency,
        'reward_days': reward_days,
        'reward_policy': 'pamir_ref_days',
        'reward_policies': [],
        'period_days': period_days,
        'amount_raw': amount_minor,
        'amount_base_minor': amount_base_minor,
        'base_currency': base_currency,
        'amount_rub_cents': amount_base_minor,
        'payment_type': payment_type,
    }]


async def process_referral_reward(
'''

EDITS = [
    ("async def process_referral_reward(\n", HELPER),
    (
        """    payment_order_id = str(order.get('order_id') or '')
    if not payment_order_id:
        raise ValueError('Payment Intent order_id is required')
""",
        """    payment_order_id = str(order.get('order_id') or '')
    if not payment_order_id:
        raise ValueError('Payment Intent order_id is required')

    if PAMIR_REF_DAYS > 0:
        return await _pamir_ref_days(
            payer_id,
            order,
            payment_order_id,
            period_days=period_days,
            amount_minor=amount_minor,
            amount_base_minor=amount_base_minor,
            base_currency=base_currency,
            payment_type=payment_type,
        )
""",
    ),
]

for old, new in EDITS:
    count = src.count(old)
    if count != 1:
        sys.exit(f"Не нашёл нужное место в billing.py (найдено {count} раз), ничего не меняю:\n{old[:120]}")
    src = src.replace(old, new)

backup = PATH.with_name(PATH.name + ".bak-refdays")
shutil.copy2(PATH, backup)
PATH.write_text(src, encoding="utf-8")
print(f"Готово. Копия старого файла: {backup}")
