#!/usr/bin/env python3
"""Разовая рассылка «Скучаю 🥲» тем, кто платил, но ушёл до включения автокупонов.

Код скидки создаётся заранее в админке бота (Промокоды → ➕ Добавить), скрипт его только называет.

    python3 mognu_winback.py SKUCHAYU            показать, кому уйдёт (ничего не отправляет)
    python3 mognu_winback.py SKUCHAYU --send     отправить

Кому: у человека нет ни одного действующего ключа, был хотя бы один платный платёж, он не админ,
ему ещё не уходил автокупон ушедшим и не уходила эта рассылка (журнал — /var/lib/mognu-watch/winback_sent.json,
повторный запуск не пишет людям второй раз). Токен и ADMIN_IDS — из /root/YadrenoVPN/config.py, в вывод не попадают.
"""
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DB = '/root/YadrenoVPN/database/vpn_bot.db'
CONFIG_PY = '/root/YadrenoVPN/config.py'
SENT = '/var/lib/mognu-watch/winback_sent.json'

TEXT = ('Скучаю 🥲\n\n'
        'Без тебя тут как-то тихо. Вот <b>−30%</b> на возвращение — код действует 14 дней:\n'
        '<pre>{code}</pre>\n'
        'Открой «🔑 Мои ключи», нажми «Продлить» и введи код — могнём, как раньше 👑')


def bot_token():
    for line in open(CONFIG_PY, encoding='utf-8'):
        m = re.match(r'\s*(BOT_TOKEN|TELEGRAM_BOT_TOKEN|TOKEN)\s*=\s*["\']([0-9]+:[A-Za-z0-9_-]+)', line)
        if m:
            return m.group(2)
    sys.exit('нет токена бота в config.py')


def admin_ids():
    m = re.search(r'ADMIN_IDS\s*=\s*\[([^\]]*)\]', open(CONFIG_PY, encoding='utf-8').read(), re.S)
    return {int(x) for x in re.findall(r'-?\d{5,}', m.group(1))} if m else set()


def recipients(db):
    rows = db.execute('''
        WITH last AS (SELECT user_id, MAX(expires_at) AS last_exp FROM vpn_keys
                      WHERE expires_at IS NOT NULL GROUP BY user_id)
        SELECT u.id, u.telegram_id, date(l.last_exp)
        FROM last l JOIN users u ON u.id = l.user_id
        WHERE l.last_exp < datetime('now')
          AND EXISTS (SELECT 1 FROM payments p WHERE p.user_id = l.user_id AND p.status = 'paid'
                      AND COALESCE(p.is_promo_free, 0) = 0)
        ORDER BY l.last_exp DESC''').fetchall()
    try:
        got_auto = {r[0] for r in db.execute('SELECT user_id FROM lapsed_coupon_deliveries')}
    except sqlite3.Error:
        got_auto = set()
    admins = admin_ids()
    return [r for r in rows if r[1] and int(r[1]) not in admins and r[0] not in got_auto]


def code_exists(db, code):
    try:
        return db.execute('SELECT 1 FROM promo_codes WHERE upper(code) = upper(?)', (code,)).fetchone() is not None
    except sqlite3.Error:
        return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    send = '--send' in sys.argv
    if len(args) != 1 or not re.fullmatch(r'[A-Za-z0-9_-]{3,32}', args[0]):
        sys.exit(__doc__)
    code = args[0]
    db = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    exists = code_exists(db, code)
    if exists is False:
        sys.exit(f'Кода {code} нет в промокодах — сначала создай его в админке (30%, 14 дней).')
    try:
        sent = set(json.load(open(SENT, encoding='utf-8')))
    except (OSError, ValueError):
        sent = set()
    todo = [r for r in recipients(db) if r[0] not in sent]
    print(f'Получателей: {len(todo)} (уже получали раньше: {len(sent)})')
    for uid, _tg, ended in todo:
        print(f'  user {uid}: ключ закончился {ended}')
    if not send:
        print('\nЭто проверка. Чтобы отправить: добавь --send')
        return
    token = bot_token()
    ok = 0
    os.makedirs(os.path.dirname(SENT), exist_ok=True)
    for uid, tg, _ended in todo:
        data = urllib.parse.urlencode({'chat_id': tg, 'text': TEXT.format(code=code), 'parse_mode': 'HTML'}).encode()
        try:
            urllib.request.urlopen(f'https://api.telegram.org/bot{token}/sendMessage', data, timeout=20).read()
            ok += 1; print(f'  ✓ user {uid}')
        except urllib.error.HTTPError as e:
            print(f'  ✗ user {uid}: HTTP {e.code}' + (' (заблокировал бота)' if e.code == 403 else ''))
        except Exception as e:  # noqa: BLE001
            print(f'  ✗ user {uid}: {type(e).__name__}'); continue
        sent.add(uid)  # 403 too: retrying a blocked chat is pointless
        json.dump(sorted(sent), open(SENT, 'w', encoding='utf-8'))
        time.sleep(0.5)
    print(f'Отправлено: {ok} из {len(todo)}')


if __name__ == '__main__':
    main()
