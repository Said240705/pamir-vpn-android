#!/usr/bin/env python3
"""Что режет Beget CDN: несколько помеченных запросов через CDN и проверка, какие из них дошли до нашего nginx.

Берёт адрес CDN и путь из «Hosts» панели для входа 2058 (LTE Обход 3). Шлёт по одному запросу каждого вида —
обычная страница, GET и POST на путь xhttp разного размера и с разными заголовками — и печатает код ответа,
кто ответил (заголовок Server) и дошёл ли запрос до нас (метка в /var/log/nginx/access.log). Ничего не меняет,
Xray и ключи клиентов не трогает. Запросов мало и с паузами, чтобы Beget не принял их за атаку.

    python3 mognu_beget_probe.py            через CDN из «Hosts»
    python3 mognu_beget_probe.py ADDRESS    через другой адрес CDN
"""
import glob
import json
import os
import secrets
import socket
import sqlite3
import ssl
import sys
import time

DB = '/etc/x-ui/x-ui.db'
PORT = 2058


def host_row():
    db = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    cur = db.execute('select id from inbounds where port=?', (PORT,))
    inb = cur.fetchone()
    if not inb:
        sys.exit(f'нет входа на порту {PORT}')
    cur = db.execute('select * from hosts where inbound_id=? order by id limit 1', (inb[0],))
    row = cur.fetchone()
    if not row:
        sys.exit('у входа нет записи в Hosts')
    vals = [v for v in row if isinstance(v, str)]
    addr = next((v for v in vals if '.' in v and '/' not in v and ' ' not in v and not v.startswith('[')), None)
    path = next((v for v in vals if v.startswith('/')), '/api/stream/')
    return addr, path


def request(addr, method, path, headers=None, body=b''):
    """One raw HTTPS request (HTTP/1.1, our own bytes — no library rewriting headers); status, Server, first bytes."""
    ctx = ssl.create_default_context()
    raw = socket.create_connection((addr, 443), timeout=10)
    s = ctx.wrap_socket(raw, server_hostname=addr)
    lines = [f'{method} {path} HTTP/1.1', f'Host: {addr}', 'User-Agent: Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126 Mobile Safari/537.36',
             'Accept: */*', 'Connection: close']
    for k, v in (headers or {}).items():
        lines.append(f'{k}: {v}')
    if method == 'POST':
        lines.append(f'Content-Length: {len(body)}')
    s.sendall(('\r\n'.join(lines) + '\r\n\r\n').encode() + body)
    data = b''
    s.settimeout(8)
    try:
        while len(data) < 4096:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
    except socket.timeout:
        pass
    s.close()
    head = data.split(b'\r\n\r\n', 1)[0].decode('latin-1')
    status = head.split('\r\n', 1)[0]
    server = next((l.split(':', 1)[1].strip() for l in head.split('\r\n') if l.lower().startswith('server:')), '?')
    body_start = data.split(b'\r\n\r\n', 1)[1][:80].decode('utf-8', 'replace').replace('\n', ' ') if b'\r\n\r\n' in data else ''
    return status, server, body_start


def find_in_logs(markers):
    """{marker: 'file: request → status'} from every nginx log (port 80 and 443 servers may log separately).
    Only the tail of each file is read — the logs are big and the probe's requests are the newest lines."""
    found = {}
    for f in sorted(glob.glob('/var/log/nginx/*.log')):
        try:
            with open(f, 'rb') as fh:
                fh.seek(0, os.SEEK_END)
                fh.seek(max(0, fh.tell() - 8 * 1024 * 1024))
                tail = fh.read().decode('utf-8', 'replace')
        except OSError:
            continue
        for line in tail.splitlines():
            for m in markers:
                if m in line and m not in found:
                    parts = line.split('"')
                    req = parts[1][:60] if len(parts) > 1 else ''
                    code = parts[2].split()[0] if len(parts) > 2 and parts[2].split() else '?'
                    found[m] = f'{os.path.basename(f)}: {req} → {code}'
    return found


def main():
    addr, path = host_row()
    if len(sys.argv) > 1:
        addr = sys.argv[1]
    path = path if path.endswith('/') else path + '/'
    print(f'CDN: {addr}  путь: {path}')
    sid = secrets.token_hex(8)
    # (что проверяем, метод, путь, заголовки, тело); метка в пути — sid + буква, по ней ищем запрос в журнале nginx
    tests = [
        ('главная страница, GET /', 'GET', f'/?probe={sid}a', {}, b''),
        ('путь xhttp, GET (как скачивание)', 'GET', f'{path}{sid}b', {}, b''),
        ('путь xhttp, POST 100 байт', 'POST', f'{path}{sid}c/0', {'Content-Type': 'application/octet-stream'}, os.urandom(100)),
        ('путь xhttp, POST 100 байт как форма', 'POST', f'{path}{sid}d/0', {'Content-Type': 'application/x-www-form-urlencoded'}, b'a=' + secrets.token_hex(49).encode()),
        ('путь xhttp, POST 64 КБ', 'POST', f'{path}{sid}e/0', {'Content-Type': 'application/octet-stream'}, os.urandom(65536)),
        ('путь xhttp, GET + длинный Referer (padding)', 'GET', f'{path}{sid}f', {'Referer': f'https://{addr}{path}?x_padding=' + 'X' * 800}, b''),
        ('путь xhttp, GET + данные в заголовке', 'GET', f'{path}{sid}g/0', {'X-Data': secrets.token_urlsafe(600)}, b''),
        ('другой путь, POST 100 байт', 'POST', f'/upload/{sid}h', {'Content-Type': 'application/octet-stream'}, os.urandom(100)),
    ]
    out = []
    for i, (name, method, p, h, body) in enumerate(tests):
        try:
            status, server, start = request(addr, method, p, h, body)
        except Exception as e:
            status, server, start = f'ошибка: {e}', '-', ''
        out.append((name, status, server, start, sid + 'abcdefgh'[i]))
        print(f'  {i + 1}/{len(tests)} {name}: {status}', flush=True)
        time.sleep(3)
    time.sleep(2)
    print('ищу запросы в журналах nginx…', flush=True)
    seen = find_in_logs([o[4] for o in out])
    print()
    for name, status, server, start, marker in out:
        where = seen.get(marker, '')
        got = f'ДОШЁЛ до нас ({where})' if where else 'не дошёл'
        print(f'• {name}\n    ответ: {status} · Server: {server} · {got}\n    начало ответа: {start[:70]}')
    print('\nКак читать: «не дошёл» + 403 — режет сам Beget (WAF/правила CDN); «дошёл» + 403/4xx — отвечает наш nginx/Xray.')


if __name__ == '__main__':
    main()
