#!/usr/bin/env python3
"""Покупка тарифа в кабинете продлевает ключ, которым человек уже пользуется, а не создаёт новый.

Было: «Тарифы» в мини-приложении (/purchase) всегда оформляли заказ «новый ключ». Человек с пробным ключом покупал
«3 месяца» и получал второй ключ с новой ссылкой подписки, а пробный висел рядом. Продление шло только с кнопки
«Продлить» у конкретного ключа.

Стало (bot/services/mini_app_api.py, _purchase_handler): перед созданием заказа ищем ключ для продления —
готовый (не черновик), той же группы тарифов, без «безлимита по сроку», действующий или истёкший не больше 30 дней
назад; берём тот, что действует дольше всех. Нашли — заказ оформляется как продление этого ключа (тот же путь, что
у кнопки «Продлить»: дни прибавляются к сроку, тариф ключа меняется на купленный, ссылка подписки та же).
Не нашли — новый ключ, как раньше. Если у человека уже два и больше действующих платных ключа (берёт на семью),
продление не подставляется — создаётся новый ключ.

Покупка в чате бота (/buy) не меняется. Уже созданные заказы не меняются.

    python3 patch_buy_extends.py          показать, что изменится (ничего не меняет)
    python3 patch_buy_extends.py --apply  применить; копия: mini_app_api.py.bak-buyextends
Потом: systemctl restart yadreno-vpn
"""
import os
import py_compile
import shutil
import sys
from pathlib import Path

PATH = Path(os.getenv("PAMIR_BOT_SERVICES", "/root/YadrenoVPN/bot/services")) / "mini_app_api.py"
APPLY = "--apply" in sys.argv
MARK = "# Mognu: buying extends the key in use"

OLD = """        user, _ = get_or_create_user(telegram_id)

        intent = create_payment_intent(
            user_id=user['id'],
            purpose=PURPOSE_KEY_PURCHASE,
            purpose_data={'tariff_id': tariff_id},
        )
"""
NEW = """        user, _ = get_or_create_user(telegram_id)

        _extend_key_id = _mognu_key_to_extend(user['id'], tariff)  """ + MARK + """
        if _extend_key_id:
            intent = create_payment_intent(
                user_id=user['id'],
                purpose=PURPOSE_KEY_RENEWAL,
                purpose_data={'tariff_id': tariff_id, 'key_id': _extend_key_id},
            )
        else:
            intent = create_payment_intent(
                user_id=user['id'],
                purpose=PURPOSE_KEY_PURCHASE,
                purpose_data={'tariff_id': tariff_id},
            )
"""
ANCHOR = "async def _purchase_handler(request: web.Request) -> web.Response:\n"
HELPER = '''def _mognu_key_to_extend(user_id, tariff):  ''' + MARK + '''
    """Key that a cabinet purchase should extend instead of creating a new one; None means a new key.

    Candidates: the user's ready keys (not drafts) of the tariff's group with a finite term, active or expired at most
    30 days ago. The one that runs longest wins. Users with 2+ active paid keys keep getting new keys.
    """
    try:
        from database import db_payment_intents as _dpi

        with _dpi.get_db() as conn:
            rows = conn.execute(
                """
                SELECT k.id,
                       k.expires_at > datetime('now') AS active,
                       (EXISTS (SELECT 1 FROM trial_activations ta WHERE ta.vpn_key_id = k.id)
                        AND NOT EXISTS (SELECT 1 FROM payments tp WHERE tp.vpn_key_id = k.id
                                        AND tp.purpose = 'key_renewal' AND tp.status = 'paid')) AS trial
                FROM vpn_keys k
                JOIN tariffs t ON t.id = k.tariff_id
                WHERE k.user_id = ?
                  AND COALESCE(t.group_id, 1) = ?
                  AND k.server_id IS NOT NULL AND COALESCE(k.panel_email, '') <> ''
                  AND k.expires_at IS NOT NULL
                  AND k.expires_at > datetime('now', '-30 days')
                ORDER BY k.expires_at DESC, k.id DESC
                """,
                (int(user_id), int(tariff.get('group_id') or 1)),
            ).fetchall()
        if not rows:
            return None
        if sum(1 for r in rows if r['active'] and not r['trial']) >= 2:
            return None
        return int(rows[0]['id'])
    except Exception as error:
        logger.warning('Mognu purchase: key-to-extend lookup failed user=%s: %s', user_id, error)
        return None


'''

src = PATH.read_text(encoding="utf-8")
if MARK in src:
    sys.exit("Правка уже стоит — ничего не меняю.")
if src.count(OLD) != 1 or src.count(ANCHOR) != 1 or "PURPOSE_KEY_RENEWAL" not in src or "\nlogger" not in src:
    sys.exit("mini_app_api.py отличается от ожидаемого — ничего не меняю.")
print(("ПРИМЕНЯЮ: " if APPLY else "ИЗМЕНИТСЯ: ") + f"{PATH.name}: покупка в кабинете продлевает ключ, а не создаёт новый")
if not APPLY:
    sys.exit("Это был просмотр. Чтобы применить: python3 patch_buy_extends.py --apply")
backup = PATH.with_name(PATH.name + ".bak-buyextends")
shutil.copy2(PATH, backup)
PATH.write_text(src.replace(OLD, NEW, 1).replace(ANCHOR, HELPER + ANCHOR, 1), encoding="utf-8")
try:
    py_compile.compile(str(PATH), doraise=True)
except py_compile.PyCompileError as error:
    shutil.copy2(backup, PATH)
    sys.exit(f"Ошибка синтаксиса, вернул копию: {error}")
print(f"Готово (копия: {backup}). Перезапустите бота: systemctl restart yadreno-vpn")
