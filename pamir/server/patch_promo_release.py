#!/usr/bin/env python3
"""Скидка не теряется из-за брошенного заказа.

Было: при расчёте цены бот проверяет активный промокод человека с block_user_reservations=True. Если тот уже
«забронирован» другим заказом — человек открыл оплату и не заплатил, — скидка молча пропускается: следующая попытка
и покупка с баланса идут по полной цене, хотя код не использован (заказы 003W → 003X/003a, 23.10.2026, −10%
«Последнего шанса»).

Стало: если активный код не прошёл проверку, бот снимает бронь этого кода с других НЕоплаченных заказов того же
человека и проверяет ещё раз. Оплаченные заказы и чужие брони не трогаются; срок, лимит и выключенный код
отказывают по-прежнему. Работает везде, где считается цена: бот, кабинет, приложения, СБП и баланс.

    python3 patch_promo_release.py          показать, что изменится (ничего не меняет)
    python3 patch_promo_release.py --apply  применить; копия: promotions.py.bak-promorelease
Потом: systemctl restart yadreno-vpn
"""
import os
import py_compile
import shutil
import sys
from pathlib import Path

PATH = Path(os.getenv("PAMIR_PROMOTIONS", "/root/YadrenoVPN/bot/services/promotions.py"))
APPLY = "--apply" in sys.argv
MARK = "# Mognu: release stale promo reservations"

OLD = '''    elif _use_active_promo:
        promo = get_user_active_promo_code(user_id, order_id=order_id)
        if promo:
            availability = get_promo_code_availability(
                promo["code"],
                order_id=order_id,
                user_id=user_id,
                block_user_reservations=True,
            )
            if not availability.get("ok"):
'''
NEW = '''    elif _use_active_promo:
        promo = get_user_active_promo_code(user_id, order_id=order_id)
        if promo:
            availability = get_promo_code_availability(
                promo["code"],
                order_id=order_id,
                user_id=user_id,
                block_user_reservations=True,
            )
            if not availability.get("ok") and _mognu_release_stale_reservations(user_id, promo["id"], order_id):
                availability = get_promo_code_availability(
                    promo["code"],
                    order_id=order_id,
                    user_id=user_id,
                    block_user_reservations=True,
                )
            if not availability.get("ok"):
'''
HELPER = '''

def _mognu_release_stale_reservations(user_id, promo_code_id, order_id) -> bool:
    """''' + MARK + ''': the person opened a payment with this code and left it unpaid; the reservation of that
    order must not take the discount away from the next order. Only the person's own unpaid orders are released."""
    try:
        from database.connection import get_db

        with get_db() as conn:
            cursor = conn.execute(
                """
                UPDATE promo_redemptions SET status = 'canceled'
                WHERE user_id = ? AND promo_code_id = ? AND status = 'reserved' AND order_id != ?
                  AND order_id IN (SELECT order_id FROM payments WHERE user_id = ? AND status != 'paid')
                """,
                (user_id, promo_code_id, order_id or "", user_id),
            )
            released = cursor.rowcount > 0
        if released:
            logger.info("Mognu: promo %s reservation released for user %s (unpaid order)", promo_code_id, user_id)
        return released
    except Exception as error:
        logger.warning("Mognu: promo reservation release failed user=%s: %s", user_id, type(error).__name__)
        return False
'''

src = PATH.read_text(encoding="utf-8")
if MARK in src:
    sys.exit("Правка уже стоит — ничего не меняю.")
if src.count(OLD) != 1:
    sys.exit("Не нашёл расчёт цены с активным промокодом в ожидаемом виде — файл отличается, ничего не меняю.")
if "logger" not in src:
    sys.exit("В promotions.py нет logger — файл отличается, ничего не меняю.")
print(("ПРИМЕНЯЮ: " if APPLY else "ИЗМЕНИТСЯ: ") + f"{PATH}: снятие брони с брошенных заказов при расчёте цены")
if not APPLY:
    sys.exit("Это был просмотр. Чтобы применить: python3 patch_promo_release.py --apply")
backup = PATH.with_name(PATH.name + ".bak-promorelease")
shutil.copy2(PATH, backup)
PATH.write_text(src.replace(OLD, NEW, 1).rstrip("\n") + "\n" + HELPER, encoding="utf-8")
try:
    py_compile.compile(str(PATH), doraise=True)
except py_compile.PyCompileError as error:
    shutil.copy2(backup, PATH)
    sys.exit(f"Ошибка синтаксиса, вернул копию: {error}")
print(f"Готово (копия: {backup}). Перезапустите бота: systemctl restart yadreno-vpn")
