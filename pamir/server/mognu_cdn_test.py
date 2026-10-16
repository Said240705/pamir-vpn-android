#!/usr/bin/env python3
"""Сквозная проверка LTE-сервера через CDN прямо с сервера: поднимает временный клиент Xray с настройками,
которые получает телефон (адрес/SNI/путь из «Hosts» панели, xhttp из входа), и открывает через него YouTube.
Второй прогон — те же настройки, но мимо CDN, напрямую на наш вход (o-ya/o-bee/o-bg): если он работает,
а через CDN нет — дело в CDN; если не работает и он — дело в нашем сервере или настройках входа.
Ничего не меняет: временные файлы в /tmp, клиент Xray убивается после проверки.

    python3 mognu_cdn_test.py            вход 2056 (LTE Обход, Яндекс)
    python3 mognu_cdn_test.py 2057       вход 2057 (LTE Обход 2, Билайн)
    python3 mognu_cdn_test.py 2056 --tune   сравнить через CDN текущие настройки клиента с ускоренными (xmux, интервал)
Трафик проверки (~5 МБ на прогон) засчитается первому активному клиенту этого входа.
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time

DB = '/etc/x-ui/x-ui.db'
XRAY = '/usr/local/x-ui/bin/xray-linux-amd64'
ARGS = [a for a in sys.argv[1:] if not a.startswith('--')]
TUNE = '--tune' in sys.argv
PORT = int(ARGS[0]) if ARGS else 2056
ORIGIN = {2056: 'o-ya.pamirlink.ru', 2057: 'o-bee.pamirlink.ru', 2058: 'o-bg.pamirlink.ru'}


def row(db, sql, *a):
    cur = db.execute(sql, a)
    r = cur.fetchone()
    return dict(zip([c[0] for c in cur.description], r)) if r else None


db = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
inb = row(db, 'select id, remark, stream_settings from inbounds where port=?', PORT)
if not inb:
    sys.exit(f'нет входа на порту {PORT}')
host = row(db, 'select * from hosts where inbound_id=? order by id limit 1', inb['id'])
if not host:
    sys.exit(f'у входа {inb["remark"]} нет записи в Hosts')
cli = row(db, 'select c.uuid from clients c join client_inbounds ci on ci.client_id=c.id '
              'where ci.inbound_id=? and c.enable=1 and c.uuid<>"" limit 1', inb['id'])
if not cli:
    sys.exit('нет активного клиента на этом входе')
ss = json.loads(inb['stream_settings'])
xs = dict(ss.get('xhttpSettings') or {})
vals = [v for v in host.values() if isinstance(v, str)]
addr = next((v for v in vals if '.' in v and '/' not in v and ' ' not in v and not v.startswith('[')), None)
path = next((v for v in vals if v.startswith('/')), xs.get('path', '/'))
alpn = next((json.loads(v) for v in vals if v.startswith('["h')), ['h2', 'http/1.1'])
fp = next((v for v in vals if v in ('chrome', 'firefox', 'safari', 'edge', 'ios', 'android', 'random', 'randomized')), 'chrome')
print(f'вход: {inb["remark"]} (:{PORT})  →  CDN {addr}{path}  alpn={",".join(alpn)} fp={fp}')
print(f'xhttp сервера: {json.dumps(xs, ensure_ascii=False)}')


def run(label, xhttp, addr=addr):
    cfg = {
        'log': {'loglevel': 'warning'},
        'inbounds': [{'listen': '127.0.0.1', 'port': 10899, 'protocol': 'socks', 'settings': {'udp': False}}],
        'outbounds': [{'protocol': 'vless', 'settings': {'vnext': [{'address': addr, 'port': 443,
                       'users': [{'id': cli['uuid'], 'encryption': 'none'}]}]},
                       'streamSettings': {'network': 'xhttp', 'xhttpSettings': xhttp, 'security': 'tls',
                                          'tlsSettings': {'serverName': addr, 'alpn': alpn, 'fingerprint': fp}}}],
    }
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
        json.dump(cfg, f)
    p = subprocess.Popen([XRAY, 'run', '-c', f.name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(1.5)
    out = []
    pings = []
    for _ in range(5):
        r = subprocess.run(['curl', '-s', '-o', '/dev/null', '--max-time', '10', '--socks5-hostname', '127.0.0.1:10899',
                            '-w', '%{time_total}', 'https://www.google.com/generate_204'], capture_output=True, text=True)
        try:
            pings.append(float(r.stdout) * 1000)
        except ValueError:
            pass
    pings.sort()
    out.append(f'пинг: {pings[len(pings) // 2]:.0f} мс (лучший {pings[0]:.0f})' if pings else 'пинг: 000 —')
    r = subprocess.run(['curl', '-s', '-o', '/dev/null', '--max-time', '25', '--socks5-hostname', '127.0.0.1:10899',
                        '--data-binary', '@-', '-w', '%{http_code} %{speed_upload}', 'https://speed.cloudflare.com/__up'],
                       input=b'0' * 1_000_000, capture_output=True)
    uc, us = (r.stdout.decode().split() + ['000', '0'])[:2]
    try:
        out.append(f'отдача: {uc} ({float(us) * 8 / 1e6:.1f} Мбит/с)')
    except ValueError:
        out.append(f'отдача: {uc}')
    for name, url in (('YouTube', 'https://www.youtube.com/'),
                      ('5 МБ', 'https://speed.cloudflare.com/__down?bytes=5000000')):
        r = subprocess.run(['curl', '-s', '-o', '/dev/null', '--max-time', '25', '--socks5-hostname', '127.0.0.1:10899',
                            '-w', '%{http_code} %{time_total}s %{speed_download}', url], capture_output=True, text=True)
        code, t, sp = (r.stdout.split() + ['000', '-', '0'])[:3]
        mbit = float(sp) * 8 / 1e6 if sp.replace('.', '', 1).isdigit() else 0
        out.append(f'{name}: {code} за {t}' + (f' ({mbit:.1f} Мбит/с)' if name == '5 МБ' and code == '200' else ''))
    p.terminate()
    try:
        log = p.communicate(timeout=3)[0]
    except subprocess.TimeoutExpired:
        p.kill(); log = ''
    os.unlink(f.name)
    ok = all(o.split(': ')[1].startswith('200') for o in out if o.split(': ')[0] in ('YouTube', '5 МБ'))
    print(f'{"✅" if ok else "❌"} {label}: ' + ' · '.join(out))
    errs = [l for l in log.splitlines() if 'failed' in l.lower() or 'error' in l.lower()]
    for l in errs[-3:]:
        print('    xray:', l[-180:])


run(f'через CDN {addr}', {**xs, 'path': path, 'host': addr})
if TUNE:
    XMUX = {'maxConcurrency': '16-32', 'maxConnections': 0, 'cMaxReuseTimes': 0,
            'hMaxRequestTimes': '600-900', 'hMaxReusableSecs': '1800-3000', 'hKeepAlivePeriod': 0}
    run('через CDN + xmux', {**xs, 'path': path, 'host': addr, 'xmux': XMUX})
    run('через CDN + xmux + интервал 10 мс', {**xs, 'path': path, 'host': addr, 'xmux': XMUX, 'scMinPostsIntervalMs': '10-20'})
    sys.exit(0)
if PORT in ORIGIN:
    o = ORIGIN[PORT]
    run(f'напрямую {o} (мимо CDN)', {**xs, 'path': path, 'host': o}, addr=o)
