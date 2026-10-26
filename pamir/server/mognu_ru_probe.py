#!/usr/bin/env python3
"""Проверка из России: доходят ли люди до основного сервера. Две половины в одном файле.

На российском VPS (AdminVPS, mognu.app) — проверка: раз в минуту открывает соединение с портом 443 основного
сервера (как приложение) и пингует его. Порт не отвечает 2 проверки подряд — сбой; после восстановления — сколько
длился и был ли пинг (пинг есть, порт нет — похоже на фильтрацию; нет даже пинга — пропал маршрут). Каждая проверка
пишется в /var/log/mognu-probe.log, так что видны и короткие провалы. Telegram из России не открывается, поэтому
сообщения публикуются в https://mognu.app/.well-known/acme-challenge/mognu-probe.json (там уже лежит папка для
сертификатов, которую nginx отдаёт сам; внутри только время и состояние, без адресов людей и секретов).

На основном сервере — пересылка: раз в минуту забирает этот файл и шлёт новые сообщения админу в Telegram. Если
файл не открывается 2 раза подряд — связь между сервером и Россией пропала, об этом пишет сам основной сервер.
Если файл давно не обновлялся — проверка на VPS остановилась. mognu_watch.py смотрит сайт; это — путь до VPN.

    на российском VPS:   python3 mognu_ru_probe.py               одна проверка (так её запускает таймер)
                         python3 mognu_ru_probe.py status        проверить сейчас и показать провалы за сутки
                         python3 mognu_ru_probe.py install       таймер systemd (каждую минуту)
    на основном сервере: python3 mognu_ru_probe.py relay         одна пересылка (так её запускает таймер)
                         python3 mognu_ru_probe.py relay-status  что видно сейчас, ничего не отправлять
                         python3 mognu_ru_probe.py test          пробное сообщение админу
                         python3 mognu_ru_probe.py install-relay таймер systemd (каждую минуту)

Цели проверки — /etc/mognu-probe.env на VPS (необязательно): TARGETS="Испания=78.17.158.230:443" (через запятую).
Токен бота и ID админов пересылка берёт из /root/YadrenoVPN/config.py, как mognu_watch.py; в вывод не попадают.
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
RELAY_STATE = '/var/lib/mognu-probe/relay.json'
LOG = '/var/log/mognu-probe.log'
PUBLIC = '/var/www/acme/.well-known/acme-challenge/mognu-probe.json'
PUBLIC_URL = 'https://mognu.app/.well-known/acme-challenge/mognu-probe.json'
CONFIG_PY = '/root/YadrenoVPN/config.py'
DEFAULT_TARGETS = 'Испания=78.17.158.230:443'
FAILS_TO_ALERT = 2
TRIES, TIMEOUT, PAUSE = 3, 5, 5  # three connection attempts ~10 s apart: one lost packet is not an outage
STALE_MIN = 5                    # the VPS publishes every minute; older than this means its timer stopped
KEEP_EVENTS = 30
MSK = ZoneInfo('Europe/Moscow')


def conf():
    c = {'TARGETS': DEFAULT_TARGETS}
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


def msk(iso):
    try:
        return dt.datetime.fromisoformat(iso).astimezone(MSK).strftime('%d.%m %H:%M')
    except (TypeError, ValueError):
        return '?'


def load(path):
    try:
        return json.load(open(path, encoding='utf-8'))
    except Exception:  # noqa: BLE001
        return {}


def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    json.dump(data, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)  # the relay must never read a half-written file


# ---------- проверка (российский VPS) ----------

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


def log(line):
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass


def step(s, name, ok, ping, now):
    """Advance one target's state by one check; return the message to publish, if any."""
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
    c, st = conf(), load(STATE)
    now = dt.datetime.now(dt.timezone.utc)
    events = st.get('events', [])
    for name, host, port in targets(c):
        ok, ms = tcp_ok(host, port)
        ping = None if ok else ping_ok(host)
        log(f'{now:%Y-%m-%dT%H:%M:%SZ} {name} tcp={"ok " + str(ms) + "ms" if ok else "fail"}'
            + ('' if ok else f' ping={"ok" if ping else "fail"}'))
        if dry:
            print(f'  {"✓" if ok else "✗"} {name}: порт {port} ' + (f'отвечает за {ms} мс' if ok else
                  f'не отвечает, пинг {"есть" if ping else "нет"}'))
            continue
        msg = step(st.setdefault('targets', {}).setdefault(name, {}), name, ok, ping, now)
        if msg:
            st['seq'] = st.get('seq', 0) + 1
            events.append({'id': st['seq'], 'at': now.isoformat(timespec='seconds'), 'text': msg})
    if dry:
        blips()
        return
    st['events'] = events[-KEEP_EVENTS:]
    save(STATE, st)
    # what the relay on the main server reads: no client addresses, only check times and outage messages
    save(PUBLIC, {'updated': now.isoformat(timespec='seconds'), 'events': st['events'],
                  'down': sorted(n for n, s in st.get('targets', {}).items() if s.get('down'))})


def blips():
    """Failed checks in the last 24 h."""
    since = f'{dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1):%Y-%m-%dT%H:%M:%SZ}'
    bad = []
    try:
        for line in open(LOG, encoding='utf-8'):
            ts, _, rest = line.partition(' ')
            if 'tcp=fail' in rest and ts >= since:
                bad.append(ts)
    except OSError:
        pass
    print(f'  провалов за сутки: {len(bad)}' + (f' (последний {msk(bad[-1].replace("Z", "+00:00"))} МСК)' if bad else ''))


# ---------- пересылка (основной сервер) ----------

def bot():
    try:
        text = open(CONFIG_PY, encoding='utf-8').read()
    except OSError:
        return None, []
    tok = re.search(r'^\s*(?:BOT_TOKEN|TELEGRAM_BOT_TOKEN|TOKEN)\s*=\s*["\']([0-9]+:[A-Za-z0-9_-]+)', text, re.M)
    ids = re.search(r'ADMIN_IDS\s*=\s*\[([^\]]*)\]', text, re.S)
    return (tok.group(1) if tok else None), (re.findall(r'-?\d{5,}', ids.group(1)) if ids else [])


def send(text):
    token, ids = bot()
    if not token or not ids:
        print('нет токена бота или ADMIN_IDS в', CONFIG_PY); return False
    ok = True
    for chat in ids:
        data = urllib.parse.urlencode({'chat_id': chat, 'text': text, 'parse_mode': 'HTML'}).encode()
        try:
            urllib.request.urlopen(f'https://api.telegram.org/bot{token}/sendMessage', data, timeout=20).read()
        except Exception as e:  # noqa: BLE001
            print('не отправлено админу:', type(e).__name__); ok = False
    return ok


def fetch():
    req = urllib.request.Request(PUBLIC_URL, headers={'User-Agent': 'mognu-probe-relay/1', 'Cache-Control': 'no-cache'})
    for i in range(2):
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode()), None
        except urllib.error.HTTPError as e:
            return None, f'HTTP {e.code}'  # the VPS answered: the link is up, the file is missing
        except Exception as e:  # noqa: BLE001
            err = type(e).__name__
            if i == 0:
                time.sleep(5)
    return None, err


def relay_step(rs, pub, err, now):
    """Advance the relay state by one fetch; return messages to send (oldest first)."""
    out = []
    link_lost = pub is None and not (err or '').startswith('HTTP')
    rs['fails'] = rs.get('fails', 0) + 1 if link_lost else 0
    if link_lost:
        rs.setdefault('first_fail', now.isoformat(timespec='seconds'))
        if not rs.get('link_down') and rs['fails'] >= FAILS_TO_ALERT:
            rs['link_down'] = True
            out.append(f'🔴 Основной сервер не достаёт до российского сервера (mognu.app) с {msk(rs["first_fail"])} МСК '
                       f'({err}). Похоже, пропала связь между сервером и Россией — у людей из России VPN может не '
                       'подключаться. Подробности пришлю, когда связь вернётся.')
        return out
    if rs.get('link_down'):
        mins = max(1, round((now - dt.datetime.fromisoformat(rs['first_fail'])).total_seconds() / 60))
        out.append(f'🟢 Связь с российским сервером вернулась. Не было с {msk(rs["first_fail"])} до '
                   f'{now.astimezone(MSK):%H:%M} МСК, около {mins} мин.')
    for k in ('link_down', 'first_fail'):
        rs.pop(k, None)
    if pub is None:  # HTTP error: the file is not published, so the probe on the VPS is not running
        if not rs.get('stale_warned'):
            rs['stale_warned'] = True
            out.append(f'🟡 Проверка из России не публикует результаты ({err}). На российском сервере: '
                       '<code>systemctl status mognu-probe.timer</code>')
        return out
    first = 'last_id' not in rs
    last = rs.get('last_id', 0)
    for ev in pub.get('events', []):
        if ev.get('id', 0) > last:
            if not first:  # on the first run only remember where the feed is, do not replay old outages
                out.append(ev['text'])
            rs['last_id'] = ev['id']
    rs.setdefault('last_id', 0)
    try:
        age = (now - dt.datetime.fromisoformat(pub['updated'])).total_seconds() / 60
    except (KeyError, TypeError, ValueError):
        age = None
    if age is not None and age > STALE_MIN:
        if not rs.get('stale_warned'):
            rs['stale_warned'] = True
            out.append(f'🟡 Проверка из России остановилась: последняя была {msk(pub["updated"])} МСК. На российском '
                       'сервере: <code>systemctl status mognu-probe.timer</code>')
    elif age is not None:
        rs.pop('stale_warned', None)
    return out


def relay(dry=False):
    rs = load(RELAY_STATE)
    now = dt.datetime.now(dt.timezone.utc)
    pub, err = fetch()
    if dry:
        if pub is None:
            print(f'  ✗ {PUBLIC_URL}: {err}')
        else:
            print(f'  ✓ проверка из России обновлялась {msk(pub.get("updated"))} МСК; '
                  f'сейчас недоступно: {", ".join(pub.get("down", [])) or "ничего"}; сообщений в ленте: {len(pub.get("events", []))}')
        return
    msgs = rs.get('pending', []) + relay_step(rs, pub, err, now)
    rs['pending'] = [m for m in msgs[-20:] if not send(m)]
    save(RELAY_STATE, rs)


def install(relay_side):
    me = os.path.abspath(__file__)
    unit, what, arg = ('mognu-probe-relay', 'relay from the RU probe to Telegram', ' relay') if relay_side else \
        ('mognu-probe', 'main server reachable from Russia', '')
    open(f'/etc/systemd/system/{unit}.service', 'w').write(
        f'[Unit]\nDescription=Mognu probe: {what}\n\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 {me}{arg}\n')
    open(f'/etc/systemd/system/{unit}.timer', 'w').write(
        f'[Unit]\nDescription=Mognu probe ({unit}) every minute\n\n[Timer]\nOnBootSec=1min\nOnUnitActiveSec=1min\n'
        'AccuracySec=5s\n\n[Install]\nWantedBy=timers.target\n')
    if not relay_side:
        open('/etc/logrotate.d/mognu-probe', 'w').write(
            f'{LOG} {{\n  weekly\n  rotate 8\n  compress\n  missingok\n  notifempty\n}}\n')
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', f'{unit}.timer'], check=True)
    print(f'Таймер {unit} поставлен: каждую минуту.')


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'run'
    if mode == 'status':
        run(dry=True)
    elif mode == 'install':
        install(False); run(); run(dry=True)
    elif mode == 'relay':
        relay()
    elif mode == 'relay-status':
        relay(dry=True)
    elif mode == 'install-relay':
        install(True); relay(dry=True)
    elif mode == 'test':
        print('отправлено' if send('👑 Проверка из России подключена: напишу, если основной сервер станет '
                                   'недоступен из России или пропадёт связь с российским сервером.') else 'не отправлено')
    else:
        run()
