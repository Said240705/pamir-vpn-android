#!/usr/bin/env python3
"""Скидка ушедшим в приложении и кабинете: бот отдаёт персональный купон возврата через /last-chance-offer.

Сейчас /mini-app-api/last-chance-offer (bot/services/mini_app_api.py) даёт скидку только в первые сутки после
окончания ключа. Патч добавляет запасной вариант: если таких суток нет, у человека нет ни одного действующего ключа,
а есть действующий персональный купон возврата (автокупон ушедшим `auto_lapsed:*` или рассылка `winback:*`), — бот
отдаёт его с kind = "comeback". Приложение покажет «Скучаю 🥲 −N% на возвращение», кабинет — плашку с днями.

    python3 patch_comeback_offer.py          показать, что изменится (ничего не меняет)
    python3 patch_comeback_offer.py --apply  применить (копия файла рядом, .bak-comeback)
Потом перезапустить бота.
"""
import os
import py_compile
import shutil
import sys

PATH = '/root/YadrenoVPN/bot/services/mini_app_api.py'
MARK = '# Mognu: comeback coupon'
ANCHOR = """            if not key:
                return web.json_response({'ok': True, 'available': False})
"""
NEW = """            if not key:
                # Mognu: comeback coupon — someone who left earlier and holds a personal lapsed / win-back coupon
                has_active = conn.execute(
                    "SELECT 1 FROM vpn_keys WHERE user_id = ? "
                    "AND (expires_at IS NULL OR expires_at > datetime('now')) LIMIT 1",
                    (user['id'],),
                ).fetchone()
                promo = None if has_active else conn.execute(
                    "SELECT code, discount_percent, expires_at FROM promo_codes "
                    "WHERE issued_to_user_id = ? AND is_active = 1 "
                    "AND (source LIKE 'auto_lapsed:%' OR source LIKE 'winback:%') "
                    "AND (expires_at IS NULL OR expires_at > datetime('now')) "
                    "AND usage_count < COALESCE(activation_limit, 1) "
                    "ORDER BY id DESC LIMIT 1",
                    (user['id'],),
                ).fetchone()
                if promo:
                    return web.json_response({
                        'ok': True, 'available': True, 'kind': 'comeback',
                        'code': promo['code'], 'discount_percent': promo['discount_percent'],
                        'expires_at': promo['expires_at'], 'tariff_name': None, 'key_name': None,
                    })
                return web.json_response({'ok': True, 'available': False})
"""


def main():
    src = open(PATH, encoding='utf-8').read()
    if MARK in src:
        print('Уже применён — ничего не делаю.'); return
    if src.count(ANCHOR) != 1:
        sys.exit(f'Не нашёл место для правки (совпадений: {src.count(ANCHOR)}). Файл менялся — пришли его кусок Claude.')
    if '--apply' not in sys.argv:
        print('Будет добавлено в _last_chance_offer_handler:\n' + NEW + '\nЧтобы применить: --apply'); return
    backup = PATH + '.bak-comeback'
    shutil.copy2(PATH, backup)
    open(PATH, 'w', encoding='utf-8').write(src.replace(ANCHOR, NEW))
    try:
        py_compile.compile(PATH, doraise=True)
    except py_compile.PyCompileError as e:
        shutil.copy2(backup, PATH)
        sys.exit(f'Ошибка компиляции, вернул как было: {e}')
    print(f'Готово. Копия: {backup}\nПерезапусти бота, чтобы правка заработала.')


if __name__ == '__main__':
    main()
