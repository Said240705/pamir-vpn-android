#!/usr/bin/env python3
"""Разовая рассылка «Скучаю 🥲» тем, кто платил, но ушёл до включения автокупонов.

Код скидки создаётся заранее в админке бота (Промокоды → ➕ Добавить), скрипт его только называет.
Каналы: Telegram; push в браузер (у кого разрешены уведомления на сайте); колокольчик в кабинете.
Push берёт VAPID_PRIVATE_KEY / VAPID_CLAIM_EMAIL из окружения (того же файла, что у бэкенда сайта)
и pywebpush из venv бэкенда; без них push пропускается, остальное уходит.

    python3 mognu_winback.py SKUCHAYU            показать, кому уйдёт (ничего не отправляет)
    python3 mognu_winback.py SKUCHAYU --test     отправить всё только админам — посмотреть, как выглядит
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
PUSH_TITLE = 'Скучаю 🥲'
PUSH_BODY = 'Вот −30% на возвращение: код {code}, 14 дней. Нажми «Продлить», введи код — и могнём, как раньше 👑'

TEXT = ('Скучаю 🥲\n\n'
        'Без тебя тут как-то тихо. Вот <b>−30%</b> на возвращение — код действует 14 дней:\n'
        '<pre>{code}</pre>\n'
        'Открой Mognu на сайте или в приложении, нажми «Продлить» и введи код при оплате — могнём, как раньше 👑')
SITE = 'https://mognu.app/login.html'
BUTTON_TEXT = '👑 Вернуться в Mognu'


def button(token):
    """Open the bot's own mini app (the «Меню» button URL) right in Telegram; plain site link as fallback."""
    try:
        r = json.load(urllib.request.urlopen(f'https://api.telegram.org/bot{token}/getChatMenuButton', timeout=20))
        url = r['result'].get('web_app', {}).get('url') if r['result'].get('type') == 'web_app' else None
    except Exception:  # noqa: BLE001
        url = None
    print('кнопка: мини-апп ' + url if url else 'кнопка: ссылка на сайт (мини-апп в «Меню» не найден)')
    b = {'text': BUTTON_TEXT, 'web_app': {'url': url}} if url else {'text': BUTTON_TEXT, 'url': SITE}
    return json.dumps({'inline_keyboard': [[b]]}, ensure_ascii=False)


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


def admin_users(db):
    ids = sorted(admin_ids())
    if not ids:
        return []
    marks = ','.join('?' * len(ids))
    return db.execute(f"SELECT id, telegram_id, 'админ' FROM users WHERE telegram_id IN ({marks})", ids).fetchall()


def push_sender():
    key = os.getenv('VAPID_PRIVATE_KEY')
    if not key:
        print('push: нет VAPID_PRIVATE_KEY в окружении — push пропускаю (Telegram и колокольчик уйдут)')
        return None
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        print('push: нет pywebpush — запусти через /root/pamir-vpn-miniapp/backend/venv/bin/python3')
        return None
    claim = os.getenv('VAPID_CLAIM_EMAIL', 'mailto:noreply@pamirlink.ru')

    def send(rw, uid, title, body):
        n = 0
        for sid, endpoint, p256dh, auth in rw.execute(
                'SELECT id, endpoint, p256dh, auth FROM push_subscriptions WHERE user_id = ?', (uid,)).fetchall():
            try:
                webpush(subscription_info={'endpoint': endpoint, 'keys': {'p256dh': p256dh, 'auth': auth}},
                        data=json.dumps({'title': title, 'body': body, 'url': '/login.html'}),
                        vapid_private_key=key, vapid_claims={'sub': claim})
                n += 1
            except WebPushException as e:
                if getattr(e.response, 'status_code', None) in (404, 410):  # same cleanup as the backend
                    rw.execute('DELETE FROM push_subscriptions WHERE id = ?', (sid,)); rw.commit()
            except Exception:  # noqa: BLE001
                pass
        return n
    return send


def code_exists(db, code):
    try:
        return db.execute('SELECT 1 FROM promo_codes WHERE upper(code) = upper(?)', (code,)).fetchone() is not None
    except sqlite3.Error:
        return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    send = '--send' in sys.argv
    test = '--test' in sys.argv
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
    todo = admin_users(db) if test else [r for r in recipients(db) if r[0] not in sent]
    pushable = {r[0] for r in db.execute('SELECT DISTINCT user_id FROM push_subscriptions')}
    print(('Тест — только админам: ' if test else 'Получателей: ') + f'{len(todo)}'
          + ('' if test else f' (уже получали раньше: {len(sent)})'))
    for uid, _tg, ended in todo:
        print(f'  user {uid}: ' + (ended if test else f'ключ закончился {ended}')
              + (', есть push' if uid in pushable else ''))
    if not (send or test):
        print('\nЭто проверка. Посмотреть на себе: --test. Отправить всем: --send')
        return
    token = bot_token()
    push = push_sender()
    markup = button(token)
    rw = sqlite3.connect(DB, timeout=15)
    ok = pushed = 0
    os.makedirs(os.path.dirname(SENT), exist_ok=True)
    for uid, tg, _ended in todo:
        line = f'  user {uid}:'
        data = urllib.parse.urlencode({'chat_id': tg, 'text': TEXT.format(code=code), 'parse_mode': 'HTML',
                                       'reply_markup': markup}).encode()
        try:
            urllib.request.urlopen(f'https://api.telegram.org/bot{token}/sendMessage', data, timeout=20).read()
            ok += 1; line += ' ✓ Telegram'
        except urllib.error.HTTPError as e:
            line += f' ✗ Telegram HTTP {e.code}' + (' (заблокировал бота)' if e.code == 403 else '')
        except Exception as e:  # noqa: BLE001
            line += f' ✗ Telegram {type(e).__name__}'
        body = PUSH_BODY.format(code=code)
        rw.execute('INSERT INTO app_notifications (user_id, title, body, url) VALUES (?, ?, ?, ?)',
                   (uid, PUSH_TITLE, body, '/login.html'))
        rw.commit(); line += ' ✓ колокольчик'
        if push and uid in pushable:
            n = push(rw, uid, PUSH_TITLE, body)
            pushed += bool(n); line += f' ✓ push ×{n}' if n else ' ✗ push'
        print(line)
        if not test:
            sent.add(uid)  # the bell is already written, so never repeat this person
            json.dump(sorted(sent), open(SENT, 'w', encoding='utf-8'))
        time.sleep(0.5)
    print(f'Telegram: {ok} из {len(todo)}, push: {pushed}, колокольчик: {len(todo)}')

if __name__ == '__main__':
    main()
