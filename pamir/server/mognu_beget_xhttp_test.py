#!/usr/bin/env python3
"""Проверка xhttp через Beget CDN с разной «набивкой» (padding), без панели и без ключей людей.

Защита Beget отвечает 403 на Referer с параметрами (а стандартный xhttp кладёт туда ?x_padding=XXXX) и на заголовки
из одинаковых символов. Xray 26 умеет класть набивку в другое место (xPaddingPlacement) и делать её из случайных
символов (xPaddingMethod: tokenish). Скрипт поднимает ВРЕМЕННЫЙ Xray-сервер на 127.0.0.1:2058 (туда nginx уже
отправляет /api/stream/ для o-bg.pamirlink.ru; вход 2058 в панели должен быть выключен — порт свободен) и временный
клиент через Beget, с одноразовым ключом, и для каждого варианта открывает YouTube и качает 5 МБ. Потом всё гасит.

    python3 mognu_beget_xhttp_test.py                    адрес CDN из «Hosts» панели (вход 2058)
    python3 mognu_beget_xhttp_test.py ADDRESS            другой адрес CDN
"""
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid

XRAY = '/usr/local/x-ui/bin/xray-linux-amd64'
DB = '/etc/x-ui/x-ui.db'
PORT = 2058
SOCKS = 10898

VARIANTS = [
    ('A как сейчас: набивка в Referer (?x_padding=XXX)', {}),
    ('B набивка в своём заголовке, случайные символы',
     {'xPaddingObfsMode': True, 'xPaddingPlacement': 'header', 'xPaddingHeader': 'X-Request-Pad', 'xPaddingMethod': 'tokenish'}),
    ('C набивка в cookie, случайные символы',
     {'xPaddingObfsMode': True, 'xPaddingPlacement': 'cookie', 'xPaddingKey': 'sid', 'xPaddingMethod': 'tokenish'}),
]


def cdn_address():
    if len(sys.argv) > 1:
        return sys.argv[1]
    db = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    inb = db.execute('select id from inbounds where port=?', (PORT,)).fetchone()
    row = db.execute('select * from hosts where inbound_id=? order by id limit 1', (inb[0],)).fetchone() if inb else None
    vals = [v for v in (row or []) if isinstance(v, str)]
    addr = next((v for v in vals if '.' in v and '/' not in v and ' ' not in v and not v.startswith('[')), None)
    if not addr:
        sys.exit('не нашёл адрес CDN в «Hosts» для входа 2058 — передай его аргументом')
    return addr


def port_free(port):
    s = socket.socket()
    try:
        return s.connect_ex(('127.0.0.1', port)) != 0
    finally:
        s.close()


def run_variant(addr, name, extra):
    uid = str(uuid.uuid4())
    xs = {'path': '/api/stream/', 'mode': 'packet-up', **extra}
    server = {
        'log': {'loglevel': 'warning'},
        'inbounds': [{'listen': '127.0.0.1', 'port': PORT, 'protocol': 'vless',
                      'settings': {'clients': [{'id': uid}], 'decryption': 'none'},
                      'streamSettings': {'network': 'xhttp', 'xhttpSettings': xs}}],
        'outbounds': [{'protocol': 'freedom'}],
    }
    client = {
        'log': {'loglevel': 'warning'},
        'inbounds': [{'listen': '127.0.0.1', 'port': SOCKS, 'protocol': 'socks', 'settings': {'udp': False}}],
        'outbounds': [{'protocol': 'vless', 'settings': {'vnext': [{'address': addr, 'port': 443,
                       'users': [{'id': uid, 'encryption': 'none'}]}]},
                       'streamSettings': {'network': 'xhttp', 'xhttpSettings': {**xs, 'host': addr}, 'security': 'tls',
                                          'tlsSettings': {'serverName': addr, 'alpn': ['h2', 'http/1.1'], 'fingerprint': 'chrome'}}}],
    }
    files = []
    procs = []
    try:
        for cfg in (server, client):
            f = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False)
            json.dump(cfg, f); f.close(); files.append(f.name)
        for path in files:
            procs.append(subprocess.Popen([XRAY, 'run', '-c', path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True))
        time.sleep(2)
        for p in procs:
            if p.poll() is not None:
                return f'❌ {name}: Xray не запустился — {p.communicate()[0].strip()[-200:]}'
        sx = f'127.0.0.1:{SOCKS}'
        out = []
        pings = []
        for _ in range(4):
            r = subprocess.run(['curl', '-s', '-o', '/dev/null', '--max-time', '10', '--socks5-hostname', sx, '-w', '%{http_code} %{time_total}',
                                'https://www.google.com/generate_204'], capture_output=True, text=True)
            code, t = (r.stdout.split() + ['000', '0'])[:2]
            if code == '204':
                pings.append(float(t) * 1000)
        out.append(f'пинг {sorted(pings)[len(pings) // 2]:.0f} мс' if pings else 'пинг: нет ответа')
        for label, url in (('YouTube', 'https://www.youtube.com/'), ('5 МБ', 'https://speed.cloudflare.com/__down?bytes=5000000')):
            r = subprocess.run(['curl', '-s', '-o', '/dev/null', '--max-time', '30', '--socks5-hostname', sx, '-w', '%{http_code} %{speed_download}', url],
                               capture_output=True, text=True)
            code, sp = (r.stdout.split() + ['000', '0'])[:2]
            mbit = float(sp) * 8 / 1e6 if code == '200' else 0
            out.append(f'{label} {code}' + (f' ({mbit:.1f} Мбит/с)' if label == '5 МБ' and code == '200' else ''))
        ok = all(' 200' in o for o in out if o.startswith(('YouTube', '5 МБ')))
        return f'{"✅" if ok else "❌"} {name}: ' + ' · '.join(out)
    finally:
        for p in procs:
            p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
        for path in files:
            os.unlink(path)


def main():
    addr = cdn_address()
    if not port_free(PORT):
        sys.exit(f'порт {PORT} занят — выключи вход 2058 в панели (LTE Обход 3) и запусти снова')
    print(f'CDN: {addr} → o-bg.pamirlink.ru → временный Xray на 127.0.0.1:{PORT}\n', flush=True)
    for name, extra in VARIANTS:
        print(run_variant(addr, name, extra), flush=True)
        time.sleep(3)
    print('\nВсё временное выключено и удалено. Панель и ключи людей не трогались.')


if __name__ == '__main__':
    main()
