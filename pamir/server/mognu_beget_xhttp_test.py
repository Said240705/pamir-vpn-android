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
        line = f'{"✅" if ok else "❌"} {name}: ' + ' · '.join(out)
        if not ok:
            line += '\n' + diagnostics(procs, uid)
        return line
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()
        for path in files:
            os.unlink(path)


def diagnostics(procs, uid):
    """Why a variant failed: the last lines of both Xray logs and what nginx saw on /api/stream/ for this run."""
    lines = []
    for label, p in (('сервер', procs[0]), ('клиент', procs[1])):
        p.terminate()
        try:
            log = p.communicate(timeout=3)[0]
        except subprocess.TimeoutExpired:
            p.kill(); log = ''
        tail = [l[-170:] for l in log.splitlines() if l.strip()][-4:]
        lines.append(f'    Xray {label}: ' + ('\n      '.join(tail) if tail else 'пусто'))
    seen = []
    try:
        with open('/var/log/nginx/access.log', 'rb') as fh:
            fh.seek(0, os.SEEK_END); fh.seek(max(0, fh.tell() - 4 * 1024 * 1024))
            for l in fh.read().decode('utf-8', 'replace').splitlines():
                if '/api/stream/' in l and time.strftime('%d/%b/%Y') in l:
                    parts = l.split('"')
                    if len(parts) > 2:
                        seen.append(f'{parts[1][:70]} → {" ".join(parts[2].split()[:2])}')
    except OSError:
        pass
    lines.append('    nginx (/api/stream/, последние): ' + ('\n      '.join(seen[-6:]) if seen else 'ни одного запроса не дошло'))
    return '\n'.join(lines)


def stream_check(addr):
    """Does Beget pass a long answer bit by bit? A tiny local server sends 5 chunks a second apart."""
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Transfer-Encoding', 'chunked')
            self.send_header('X-Accel-Buffering', 'no')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            for i in range(5):
                part = f'chunk{i}\n'.encode()
                self.wfile.write(f'{len(part):x}\r\n'.encode() + part + b'\r\n'); self.wfile.flush()
                time.sleep(1)
            self.wfile.write(b'0\r\n\r\n')

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(('127.0.0.1', PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = subprocess.run(['curl', '-sN', '--max-time', '15', '-w', '\n%{time_starttransfer} %{time_total}',
                            f'https://{addr}/api/stream/streamtest{int(time.time())}'], capture_output=True, text=True)
        body = r.stdout.strip().splitlines()
        first, total = (body[-1].split() + ['?', '?'])[:2] if body else ('?', '?')
        chunks = sum(1 for b in body if b.startswith('chunk'))
        return f'первый байт через {first} с, всё за {total} с, частей {chunks}/5'
    finally:
        srv.shutdown()


def main():
    addr = cdn_address()
    if not port_free(PORT):
        sys.exit(f'порт {PORT} занят — выключи вход 2058 в панели (LTE Обход 3) и запусти снова')
    print(f'CDN: {addr} → o-bg.pamirlink.ru → временный Xray на 127.0.0.1:{PORT}\n', flush=True)
    print('Поток через Beget (5 частей по секунде): ' + stream_check(addr), flush=True)
    print('   ≈1 с до первого байта — Beget отдаёт по частям (хорошо); ≈5 с — копит весь ответ (для туннеля плохо)\n', flush=True)
    for name, extra in VARIANTS:
        print(run_variant(addr, name, extra), flush=True)
        time.sleep(3)
    print('\nВсё временное выключено и удалено. Панель и ключи людей не трогались.')


if __name__ == '__main__':
    main()
