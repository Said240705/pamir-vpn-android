#!/usr/bin/env python3
"""Проверка из России: доходят ли люди до основного сервера. Ставится на российский VPS (AdminVPS, mognu.app).

Раз в минуту открывает соединение с портом 443 основного сервера (как приложение) и пингует его. Если порт не
отвечает 2 проверки подряд — пишет админу в Telegram; когда заработает — сколько длился сбой и был ли пинг.
Пинг есть, а порт нет — похоже на фильтрацию соединений; нет даже пинга — пропал маршрут до сервера.
Каждая проверка пишется в /var/log/mognu-probe.log, так что видны и короткие провалы, о которых не писали.
mognu_watch.py на основном сервере смотрит обратный путь (до mognu.app); этот скрипт — путь из России до сервера.

    python3 mognu_ru_probe.py            одна проверка (так её запускает таймер)
    python3 mognu_ru_probe.py status     проверить сейчас и показать провалы за сутки, ничего не отправлять
    python3 mognu_ru_probe.py test       отправить пробное сообщение админу
    python3 mognu_ru_probe.py install    поставить таймер systemd (каждую минуту)
    python3 mognu_ru_probe.py env        на ОСНОВНОМ сервере: вывести настройки бота для /etc/mognu-probe.env
                                         (токен и ID админов из /root/YadrenoVPN/config.py) — только в канал ssh

Настройки — /etc/mognu-probe.env: BOT_TOKEN=…, ADMIN_IDS=1,2, TARGETS="Испания=78.17.158.230:443" (через запятую).
"""
import datetime as dt
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

CONF = '/etc/mognu-probe.env'
STATE = '/var/lib/mognu-probe/state.json'
LOG = '/var/log/mognu-probe.log'
CONFIG_PY = '/root/YadrenoVPN/config.py'
DEFAULT_TARGETS = 'Испания=78.17.158.230:443'
FAILS_TO_ALERT = 2
TRIES, TIMEOUT, PAUSE = 3, 5, 5  # three connection attempts ~10 s apart: one lost packet is not an outage
MSK = ZoneInfo('Europe/Moscow')


def conf():
    c = {'TARGETS': DEFAULT_TARGETS, 'BOT_TOKEN': '', 'ADMIN_IDS': ''}
    try:
        for line in open(CONF, encoding='utf-8'):
            m = re.match(r'\s*([A-Z_]+)\s*=\s*"?([^"\n]*)"?', line)
            if m:
                c[m.group(1)] = m.group(2).strip()
    except OSError:
        pass
    return c


def targets(c):
    out = []
    for item in c['TARGETS'].split(','):
        name, _, addr = item.strip().rpartition('=')
        host, _, port = addr.rpartition(':')
        if host and port.isdigit():
            out.append((name or host, host, int(port)))
    return out


def send(c, text):
    token, ids = c['BOT_TOKEN'], re.findall(r'-?\d{5,}', c['ADMIN_IDS'])
    if not token or not ids:
        print('нет BOT_TOKEN или ADMIN_IDS в', CONF); return False
    ok = True
    for chat in ids:
        data = urllib.parse.urlencode({'chat_id': chat, 'text': text, 'parse_mode': 'HTML'}).encode()
        try:
            urllib.request.urlopen(f'https://api.telegram.org/bot{token}/sendMessage', data, timeout=20).read()
        except Exception as e:  # noqa: BLE001
            print('не отправлено админу:', type(e).__name__); ok = False
    return ok


def tcp_ok(host, port):
    for i in range(TRIES):
        try:
            t0 = time.monotonic()
            with socket.create_connection((host, port), timeout=TIMEOUT):
                return True, int((time.monotonic() - t0) * 1000)
        except OSError:
            if i < TRIES - 1:
                time.sleep(PAUSE)
    return False, None


def ping_ok(host):
    try:
        return subprocess.run(['ping', '-c', '2', '-W', '3', host], capture_output=True, timeout=15).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return None


def msk(iso):
    try:
        return dt.datetime.fromisoformat(iso).astimezone(MSK).strftime('%d.%m %H:%M')
    except (TypeError, ValueError):
        return '?'


def load():
    try:
        return json.load(open(STATE, encoding='utf-8'))
    except Exception:  # noqa: BLE001
        return {}


def save(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, 'w', encoding='utf-8'), ensure_ascii=False)


def log(line):
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass


def step(s, name, ok, ping, now):
    """Advance one target's state by one check; return the message to send, if any."""
    s['fails'] = 0 if ok else s.get('fails', 0) + 1
    if not ok:
        s.setdefault('first_fail', now.isoformat(timespec='seconds'))
        s['ping_seen'] = s.get('ping_seen', False) or bool(ping)
    if not ok and not s.get('down') and s['fails'] >= FAILS_TO_ALERT:
        s['down'] = True
        return (f'🔴 <b>{name}</b> недоступен из России с {msk(s["first_fail"])} МСК (порт 443 не отвечает; '
                f'пинг {"проходит — похоже на фильтрацию соединений" if ping else "тоже не проходит — пропал маршрут"}).\n'
                'Сам сервер может работать: проверь, видят ли его из других стран, на check-host.net.')
    if ok:
        msg = None
        if s.get('down'):
            mins = max(1, round((now - dt.datetime.fromisoformat(s['first_fail'])).total_seconds() / 60))
            msg = (f'🟢 <b>{name}</b> снова доступен из России. Сбой {msk(s["first_fail"])}–{now.astimezone(MSK):%H:%M} МСК, '
                   f'около {mins} мин; пинг {"проходил" if s.get("ping_seen") else "не проходил"}.')
        for k in ('down', 'first_fail', 'ping_seen'):
            s.pop(k, None)
        return msg
    return None


def run(dry=False):
    c, st = conf(), load()
    now = dt.datetime.now(dt.timezone.utc)
    pending = st.get('pending', [])
    for name, host, port in targets(c):
        ok, ms = tcp_ok(host, port)
        ping = None if ok else ping_ok(host)
        log(f'{now:%Y-%m-%dT%H:%M:%SZ} {name} tcp={"ok " + str(ms) + "ms" if ok else "fail"}'
            + ('' if ok else f' ping={"ok" if ping else "fail"}'))
        if dry:
            print(f'  {"✓" if ok else "✗"} {name}: порт {port} ' + (f'отвечает за {ms} мс' if ok else
                  f'не отвечает, пинг {"есть" if ping else "нет"}'))
            continue
        msg = step(st.setdefault(name, {}), name, ok, ping, now)
        if msg:
            pending.append(msg)
    if dry:
        blips()
        return
    # Telegram may be unreachable from Russia for a while: keep undelivered messages and retry next minute
    st['pending'] = [m for m in pending[-20:] if not send(c, m)]
    save(st)


def blips():
    """Failed checks in the last 24 h, grouped into runs of consecutive minutes."""
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
    bad = []
    try:
        for line in open(LOG, encoding='utf-8'):
            ts, _, rest = line.partition(' ')
            if 'tcp=fail' in rest and ts >= f'{since:%Y-%m-%dT%H:%M:%SZ}':
                bad.append(ts)
    except OSError:
        pass
    print(f'  провалов за сутки: {len(bad)}' + (f' (последний {msk(bad[-1].replace("Z", "+00:00"))} МСК)' if bad else ''))


def install():
    me = os.path.abspath(__file__)
    open('/etc/systemd/system/mognu-probe.service', 'w').write(
        f'[Unit]\nDescription=Mognu probe: main server reachable from Russia\n\n'
        f'[Service]\nType=oneshot\nExecStart=/usr/bin/python3 {me}\n')
    open('/etc/systemd/system/mognu-probe.timer', 'w').write(
        '[Unit]\nDescription=Mognu probe every minute\n\n[Timer]\nOnBootSec=1min\nOnUnitActiveSec=1min\nAccuracySec=5s\n\n'
        '[Install]\nWantedBy=timers.target\n')
    open('/etc/logrotate.d/mognu-probe', 'w').write(f'{LOG} {{\n  weekly\n  rotate 8\n  compress\n  missingok\n  notifempty\n}}\n')
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'mognu-probe.timer'], check=True)
    print('Таймер поставлен: проверка каждую минуту. Журнал проверок —', LOG)


def export_env():
    try:
        text = open(CONFIG_PY, encoding='utf-8').read()
    except OSError:
        sys.exit(f'нет {CONFIG_PY} — команду env запускают на основном сервере')
    tok = re.search(r'^\s*(?:BOT_TOKEN|TELEGRAM_BOT_TOKEN|TOKEN)\s*=\s*["\']([0-9]+:[A-Za-z0-9_-]+)', text, re.M)
    ids = re.search(r'ADMIN_IDS\s*=\s*\[([^\]]*)\]', text, re.S)
    if not tok or not ids:
        sys.exit('в config.py не найден токен бота или ADMIN_IDS')
    if sys.stdout.isatty():
        sys.exit('это вывод с токеном — передавай его только через ssh: python3 mognu_ru_probe.py env | ssh …')
    admins = ','.join(re.findall(r'-?\d{5,}', ids.group(1)))
    print(f'BOT_TOKEN={tok.group(1)}\nADMIN_IDS={admins}\nTARGETS="{DEFAULT_TARGETS}"')


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'run'
    if mode == 'status':
        run(dry=True)
    elif mode == 'test':
        print('отправлено' if send(conf(), '👑 Проверка из России подключена: напишу, если основной сервер '
                                           'станет недоступен из России, и когда он вернётся.') else 'не отправлено')
    elif mode == 'install':
        install(); run(dry=True)
    elif mode == 'env':
        export_env()
    else:
        run()
