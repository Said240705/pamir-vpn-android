#!/usr/bin/env python3
"""Проверка из России: доходят ли люди до основного сервера. Две половины в одном файле.

На российском VPS (AdminVPS, mognu.app) — проверка: раз в минуту открывает соединение с портом 443 основного
сервера (как приложение) и пингует его. Порт не отвечает 2 проверки подряд — сбой; после восстановления — сколько
длился и был ли пинг (пинг есть, порт нет — похоже на фильтрацию; нет даже пинга — пропал маршрут). Каждая проверка
пишется в /var/log/mognu-probe.log, так что видны и короткие провалы.

Telegram из России не открывается, а 443 на VPS целиком уходит на основной сервер, поэтому результат после каждой
проверки отправляется на основной сервер по ssh. Ключ там ограничен: с ним можно только передать результат
(command=… ingest, restrict) — ни входа, ни команд.

На основном сервере — пересылка: раз в минуту смотрит последний результат и шлёт новые сообщения админу в Telegram.
Результаты не приходят дольше 3 минут — пишет, что Россия молчит (пропала связь или остановилась проверка), и потом,
когда снова пришли. Неотправленное во время сбоя VPS досылает, как только связь вернётся.

    на российском VPS:   python3 mognu_ru_probe.py               одна проверка (так её запускает таймер)
                         python3 mognu_ru_probe.py status        проверить сейчас и показать провалы за сутки
                         python3 mognu_ru_probe.py install       ключ ssh (спросит пароль основного сервера один раз)
                                                                 и таймер systemd (каждую минуту)
    на основном сервере: python3 mognu_ru_probe.py relay         одна пересылка (так её запускает таймер)
                         python3 mognu_ru_probe.py relay-status  что пришло из России, ничего не отправлять
                         python3 mognu_ru_probe.py test          пробное сообщение админу
                         python3 mognu_ru_probe.py install-relay таймер systemd (каждую минуту)
                         python3 mognu_ru_probe.py ingest        принять результат (его вызывает ssh-ключ VPS)

Настройки VPS — /etc/mognu-probe.env (необязательно): TARGETS="Испания=78.17.158.230:443" (через запятую),
PUSH=root@78.17.158.230. Токен бота и ID админов пересылка берёт из /root/YadrenoVPN/config.py; в вывод не попадают.
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
FEED = '/var/lib/mognu-probe/feed.json'
RELAY_STATE = '/var/lib/mognu-probe/relay.json'
LOG = '/var/log/mognu-probe.log'
KEY = '/root/.ssh/mognu_probe'
CONFIG_PY = '/root/YadrenoVPN/config.py'
DEFAULT_TARGETS = 'Испания=78.17.158.230:443'
DEFAULT_PUSH = 'root@78.17.158.230'
FAILS_TO_ALERT = 2
TRIES, TIMEOUT, PAUSE = 3, 5, 5  # three connection attempts ~10 s apart: one lost packet is not an outage
SILENT_MIN = 3                   # the VPS reports every minute; silence this long means the link (or the probe) is down
KEEP_EVENTS = 30
MSK = ZoneInfo('Europe/Moscow')


def conf():
    c = {'TARGETS': DEFAULT_TARGETS, 'PUSH': DEFAULT_PUSH}
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
    """Advance one target's state by one check; return the message to report, if any."""
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


def push(c, report):
    """Hand the report to the main server; the key there only runs `ingest`. True when delivered."""
    try:
        r = subprocess.run(['ssh', '-i', KEY, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                            '-o', 'StrictHostKeyChecking=accept-new', c['PUSH'], 'ingest'],
                           input=json.dumps(report, ensure_ascii=False).encode(), capture_output=True, timeout=40)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


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
        print(f'  передача на основной сервер: {"работает" if push(c, {"ping": True}) else "НЕ работает"}')
        return
    st['events'] = events[-KEEP_EVENTS:]
    save(STATE, st)
    # events stay in the report until they age out, so whatever was missed during an outage arrives with the next push
    push(c, {'checked': now.isoformat(timespec='seconds'), 'events': st['events'],
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


def setup_key(c):
    """Create the push key and register it on the main server, restricted to `ingest` (asks the password once)."""
    if not os.path.exists(KEY):
        os.makedirs(os.path.dirname(KEY), mode=0o700, exist_ok=True)
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'mognu-probe', '-f', KEY], check=True)
    if push(c, {'ping': True}):
        print('Ключ уже работает.'); return
    pub = open(KEY + '.pub', encoding='utf-8').read().strip()
    line = f'command="/usr/bin/python3 /root/mognu-probe/mognu_ru_probe.py ingest",restrict {pub}'
    remote = ("umask 077; mkdir -p ~/.ssh; grep -qF '" + pub.split()[1] + "' ~/.ssh/authorized_keys 2>/dev/null"
              " || echo '" + line.replace("'", "'\\''") + "' >> ~/.ssh/authorized_keys")
    print(f'Добавляю ключ на {c["PUSH"]} (с ним можно только передавать результат) — введи пароль основного сервера:')
    subprocess.run(['ssh', '-o', 'StrictHostKeyChecking=accept-new', c['PUSH'], remote], check=True)
    print('Ключ работает.' if push(c, {'ping': True}) else 'Ключ не сработал — проверь, что скрипт лежит на основном '
          'сервере в /root/mognu-probe/mognu_ru_probe.py.')


# ---------- пересылка (основной сервер) ----------

def ingest():
    """Called by the VPS key: read one report from stdin and keep it with the time it arrived."""
    try:
        data = json.loads(sys.stdin.buffer.read(200_000).decode())
    except (ValueError, UnicodeDecodeError):
        sys.exit(1)
    if not isinstance(data, dict) or data.get('ping'):
        return
    events = [e for e in data.get('events', []) if isinstance(e, dict) and isinstance(e.get('id'), int)
              and isinstance(e.get('text'), str)][-KEEP_EVENTS:]
    save(FEED, {'received': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
                'checked': str(data.get('checked', '')), 'events': events,
                'down': [str(x) for x in data.get('down', [])][:10]})


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


def relay_step(rs, feed, now):
    """Advance the relay state by one look at the feed; return messages to send (oldest first)."""
    if not feed:
        return []  # nothing has arrived yet: the VPS side is not installed
    out = []
    received = dt.datetime.fromisoformat(feed['received'])
    silent = (now - received).total_seconds() / 60 > SILENT_MIN
    if silent and not rs.get('silent'):
        rs['silent'] = True
        rs['silent_since'] = feed['received']
        out.append(f'🔴 Проверка из России молчит с {msk(feed["received"])} МСК. Похоже, пропала связь между Россией '
                   'и сервером — у людей из России VPN может не подключаться (или остановилась проверка на российском '
                   'сервере: <code>systemctl status mognu-probe.timer</code>). Подробности пришлю, когда связь вернётся.')
    elif not silent and rs.get('silent'):
        mins = max(1, round((received - dt.datetime.fromisoformat(rs['silent_since'])).total_seconds() / 60))
        out.append(f'🟢 Проверка из России снова на связи. Молчала с {msk(rs["silent_since"])} до '
                   f'{received.astimezone(MSK):%H:%M} МСК, около {mins} мин.')
        rs.pop('silent', None); rs.pop('silent_since', None)
    first = 'last_id' not in rs
    for ev in feed.get('events', []):
        if ev['id'] > rs.get('last_id', 0):
            if not first:  # on the first run only remember where the feed is, do not replay old outages
                out.append(ev['text'])
            rs['last_id'] = ev['id']
    rs.setdefault('last_id', 0)
    return out


def relay(dry=False):
    rs, feed = load(RELAY_STATE), load(FEED)
    now = dt.datetime.now(dt.timezone.utc)
    if dry:
        if not feed:
            print('  ✗ из России ещё ничего не приходило — поставь проверку на российском сервере (install)')
        else:
            print(f'  ✓ последний результат из России: {msk(feed["received"])} МСК; '
                  f'сейчас недоступно: {", ".join(feed.get("down", [])) or "ничего"}; сообщений в ленте: {len(feed.get("events", []))}')
        return
    msgs = rs.get('pending', []) + relay_step(rs, feed, now)
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
    if mode == 'ingest':
        ingest()
    elif mode == 'status':
        run(dry=True)
    elif mode == 'install':
        setup_key(conf()); install(False); run(); run(dry=True)
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
