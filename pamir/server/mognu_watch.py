#!/usr/bin/env python3
"""Сторож Mognu: раз в 5 минут проверяет путь людей до сайта и пишет админу в Telegram только при изменении
(упало / восстановилось), плюс напоминает об оплате российского сервера-посредника.

Проверки (через обычный DNS, как у людей; mognu.app ведёт на VPS AdminVPS):
  • mognu.app — страница и API;   • mognu.net — страница;
  • сертификат mognu.app на VPS — предупредить, если осталось меньше 10 дней.
Сбой считается сбоем после 2 неудачных проверок подряд (чтобы не будить из-за одной потерянной секунды).

    python3 mognu_watch.py            одна проверка (так её запускает таймер)
    python3 mognu_watch.py status     показать результат проверок, ничего не отправлять
    python3 mognu_watch.py test       отправить пробное сообщение админу
    python3 mognu_watch.py install    поставить таймер systemd (каждые 5 минут)

Настройки — /etc/mognu-watch.env (необязательно): VPS_PAY_DAY=12 (день месяца оплаты AdminVPS), VPS_NAME=AdminVPS.
Токен бота и ID админов берутся из /root/YadrenoVPN/config.py, как у pamir_monitor.py; в вывод не попадают.
"""
import datetime as dt
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import urllib.parse
import urllib.request

STATE = '/var/lib/mognu-watch/state.json'
CONF = '/etc/mognu-watch.env'
CONFIG_PY = '/root/YadrenoVPN/config.py'
CHECKS = [
    ('site', 'mognu.app — сайт', 'https://mognu.app/welcome.html'),
    ('api', 'mognu.app — API (вход, оплата)', 'https://mognu.app/api/topup/public/server-status'),
    ('net', 'mognu.net — запасной сайт', 'https://mognu.net/welcome.html'),
]
FAILS_TO_ALERT = 2


def conf():
    c = {'VPS_PAY_DAY': '12', 'VPS_NAME': 'AdminVPS'}
    try:
        for line in open(CONF, encoding='utf-8'):
            m = re.match(r'\s*([A-Z_]+)\s*=\s*"?([^"\n]*)"?', line)
            if m:
                c[m.group(1)] = m.group(2).strip()
    except OSError:
        pass
    return c


def bot_token():
    try:
        for line in open(CONFIG_PY, encoding='utf-8'):
            m = re.match(r'\s*(BOT_TOKEN|TELEGRAM_BOT_TOKEN|TOKEN)\s*=\s*["\']([0-9]+:[A-Za-z0-9_-]+)', line)
            if m:
                return m.group(2)
    except OSError:
        pass
    return None


def admin_ids():
    try:
        m = re.search(r'ADMIN_IDS\s*=\s*\[([^\]]*)\]', open(CONFIG_PY, encoding='utf-8').read(), re.S)
        return [int(x) for x in re.findall(r'-?\d{5,}', m.group(1))] if m else []
    except OSError:
        return []


def send(text):
    token = bot_token()
    if not token:
        print('нет токена бота — сообщение не отправлено'); return False
    ok = True
    for chat in admin_ids():
        data = urllib.parse.urlencode({'chat_id': chat, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': 'true'}).encode()
        try:
            urllib.request.urlopen(f'https://api.telegram.org/bot{token}/sendMessage', data, timeout=20).read()
        except Exception as e:  # noqa: BLE001
            print('не отправлено админу:', type(e).__name__); ok = False
    return ok


def http_ok(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'mognu-watch/1', 'Cache-Control': 'no-cache'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200, f'HTTP {r.status}'
    except urllib.error.HTTPError as e:
        return False, f'HTTP {e.code}'
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__


def cert_days(host='mognu.app'):
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=15) as s, ctx.wrap_socket(s, server_hostname=host) as t:
            end = dt.datetime.strptime(t.getpeercert()['notAfter'], '%b %d %H:%M:%S %Y %Z')
            return (end - dt.datetime.utcnow()).days
    except Exception:  # noqa: BLE001
        return None


def load():
    try:
        return json.load(open(STATE, encoding='utf-8'))
    except Exception:  # noqa: BLE001
        return {}


def save(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, 'w', encoding='utf-8'), ensure_ascii=False)


def run(dry=False):
    st = load(); c = conf(); now = dt.datetime.now()
    for key, name, url in CHECKS:
        ok, why = http_ok(url)
        s = st.setdefault(key, {'down': False, 'fails': 0})
        s['fails'] = 0 if ok else s['fails'] + 1
        if dry:
            print(f"  {'✓' if ok else '✗'} {name}: {why}"); continue
        if not ok and not s['down'] and s['fails'] >= FAILS_TO_ALERT:
            s['down'] = True; s['since'] = now.isoformat(timespec='minutes')
            send(f'🔴 <b>{name}</b> не отвечает ({why}).\n'
                 + ('Скорее всего, проблема с сервером-посредником AdminVPS (185.198.152.202): проверь, что он '
                    'включён и оплачен. Быстрый обход — в Cloudflare вернуть A-запись mognu.app на 78.17.158.230.'
                    if key in ('site', 'api') else 'Проверь сайт на основном сервере.'))
        elif ok and s['down']:
            s['down'] = False
            send(f'🟢 <b>{name}</b> снова работает (не работал с {s.get("since", "?").replace("T", " ")}).')
    days = cert_days()
    if dry:
        print(f'  сертификат mognu.app: {days if days is not None else "?"} дн.')
    elif days is not None and days < 10 and st.get('cert_warned') != now.strftime('%Y-%m-%d'):
        st['cert_warned'] = now.strftime('%Y-%m-%d')
        send(f'🟡 Сертификат mognu.app заканчивается через {days} дн. На VPS: <code>certbot renew && systemctl reload nginx</code>')
    # monthly reminder to pay the proxy VPS: 3 days before and on the day
    try:
        day = int(c['VPS_PAY_DAY'])
    except ValueError:
        day = 12
    due = now.replace(day=min(day, 28), hour=0, minute=0, second=0, microsecond=0)
    if due.date() < now.date():
        nxt = (due.replace(day=1) + dt.timedelta(days=32)).replace(day=min(day, 28))
        due = nxt
    left = (due.date() - now.date()).days
    if dry:
        print(f'  оплата {c["VPS_NAME"]}: {due:%d.%m}, через {left} дн.')
    elif left in (3, 0) and now.hour >= 10:
        tag = f'pay-{due:%Y-%m}-{left}'
        if st.get('pay_warned') != tag:
            st['pay_warned'] = tag
            send(('💳 Сегодня' if left == 0 else '💳 Через 3 дня') +
                 f' нужно оплатить сервер {c["VPS_NAME"]} для mognu.app (≈394 ₽). Если не оплатить, сайт перестанет '
                 'открываться без VPN на мобильном интернете.')
    if not dry:
        save(st)


def install():
    me = os.path.abspath(__file__)
    open('/etc/systemd/system/mognu-watch.service', 'w').write(
        f'[Unit]\nDescription=Mognu watch (site via the RU proxy, certificate, VPS payment)\n\n'
        f'[Service]\nType=oneshot\nExecStart=/usr/bin/python3 {me}\n')
    open('/etc/systemd/system/mognu-watch.timer', 'w').write(
        '[Unit]\nDescription=Mognu watch every 5 minutes\n\n[Timer]\nOnBootSec=2min\nOnUnitActiveSec=5min\n\n'
        '[Install]\nWantedBy=timers.target\n')
    if not os.path.exists(CONF):
        open(CONF, 'w').write('# день месяца, когда платить AdminVPS за сервер-посредник mognu.app\nVPS_PAY_DAY=12\nVPS_NAME=AdminVPS\n')
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'mognu-watch.timer'], check=True)
    print('Таймер поставлен: каждые 5 минут. День оплаты VPS — в', CONF)


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'run'
    if mode == 'status':
        run(dry=True)
    elif mode == 'test':
        print('отправлено' if send('👑 Сторож Mognu подключён: напишу, если mognu.app перестанет открываться, '
                                   'и напомню об оплате сервера-посредника.') else 'не отправлено')
    elif mode == 'install':
        install(); run(dry=True)
    else:
        run()
