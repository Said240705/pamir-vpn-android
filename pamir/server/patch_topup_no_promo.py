#!/usr/bin/env python3
"""Промокоды и купоны не действуют на пополнение баланса.

Было: бот применял активный промокод человека к любой оплате, в том числе к пополнению баланса — пополнение на
194 ₽ стоило 145,50 ₽ (−25%), а на баланс приходили полные 194 ₽. С промокодом можно было «дёшево» набить баланс
и потом тратить его на что угодно, а сам промокод сгорал на пополнении вместо покупки подписки.

Стало (bot/services/promotions.py, build_quote): для purpose == 'balance_topup' активный промокод не подставляется.
Покупка и продление ключей — со скидкой, как раньше. Уже созданные неоплаченные заказы не меняются.

    python3 patch_topup_no_promo.py          показать, что изменится (ничего не меняет)
    python3 patch_topup_no_promo.py --apply  применить; копия: promotions.py.bak-topupnopromo
Потом: systemctl restart yadreno-vpn
"""
import os
import py_compile
import shutil
import sys
from pathlib import Path

PATH = Path(os.getenv("PAMIR_BOT_SERVICES", "/root/YadrenoVPN/bot/services")) / "promotions.py"
APPLY = "--apply" in sys.argv
MARK = "# Mognu: no promo on balance top-ups"
OLD = "    elif _use_active_promo:\n        promo = get_user_active_promo_code(user_id, order_id=order_id)\n"
NEW = ("    elif _use_active_promo and purpose != 'balance_topup':  " + MARK + "\n"
       "        promo = get_user_active_promo_code(user_id, order_id=order_id)\n")

src = PATH.read_text(encoding="utf-8")
if MARK in src:
    sys.exit("Правка уже стоит — ничего не меняю.")
if src.count(OLD) != 1 or "def build_quote(" not in src:
    sys.exit("promotions.py отличается от ожидаемого — ничего не меняю.")
print(("ПРИМЕНЯЮ: " if APPLY else "ИЗМЕНИТСЯ: ") + f"{PATH.name}: промокоды не действуют на пополнение баланса")
if not APPLY:
    sys.exit("Это был просмотр. Чтобы применить: python3 patch_topup_no_promo.py --apply")
backup = PATH.with_name(PATH.name + ".bak-topupnopromo")
shutil.copy2(PATH, backup)
PATH.write_text(src.replace(OLD, NEW, 1), encoding="utf-8")
try:
    py_compile.compile(str(PATH), doraise=True)
except py_compile.PyCompileError as error:
    shutil.copy2(backup, PATH)
    sys.exit(f"Ошибка синтаксиса, вернул копию: {error}")
print(f"Готово (копия: {backup}). Перезапустите бота: systemctl restart yadreno-vpn")
