#!/usr/bin/env python3
"""Вход 2058 (🇷🇺 LTE Обход 3) — на xhttp, который проходит через Beget CDN (вариант C из mognu_beget_xhttp_test.py).

Beget режет UUID с дефисами где угодно, случайные части пути, параметры в Referer и данные в адресе, но пропускает
32 hex-символа в cookie, случайную набивку в заголовке и отдаёт длинный ответ по частям. Поэтому: packet-up, номер
сессии — 32 hex в cookie «sid», номер куска — в cookie «seq», набивка — в заголовке, отправка — обычным POST.
Остальные настройки входа (xmux, размеры кусков) остаются как были. Ключи людей не меняются.

Панель держит базу открытой, поэтому на пару секунд останавливаем x-ui (Xray перезапустится — у всех переподключение),
правим базу и запускаем. Перед этим конфиг проверяется самим Xray, а база копируется в /root.

    python3 setup_beget_inbound.py          применить и включить вход
    python3 setup_beget_inbound.py --link   показать, что получают клиенты в подписке (ключ скрыт)
    python3 setup_beget_inbound.py --undo   вернуть базу из последней копии
"""
import glob
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

DB = '/etc/x-ui/x-ui.db'
XRAY = '/usr/local/x-ui/bin/xray-linux-amd64'
PORT = 2058
BAK = '/root/x-ui.db.bak-beget-'

BEGET = {
    'mode': 'packet-up',
    'xPaddingObfsMode': True, 'xPaddingPlacement': 'header', 'xPaddingHeader': 'X-Request-Pad', 'xPaddingMethod': 'tokenish',
    'sessionIDPlacement': 'cookie', 'sessionIDKey': 'sid', 'sessionIDTable': 'hex', 'sessionIDLength': 32,
    'seqPlacement': 'cookie', 'seqKey': 'seq',
    'uplinkDataPlacement': 'body',
}
# uplinkHTTPMethod GET is not what passed through Beget (POST did); the query padding key is unused with header placement
DROP = ('uplinkHTTPMethod', 'xPaddingKey')


def sh(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def restart_with(apply):
    """Stop the panel, run apply(), start it again — and start it again even if apply() fails."""
    if sh('systemctl', 'stop', 'x-ui').returncode != 0:
        sys.exit('не смог остановить x-ui')
    try:
        apply()
    finally:
        sh('systemctl', 'start', 'x-ui')
    for _ in range(20):
        time.sleep(1)
        if sh('ss', '-ltn', f'sport = :{PORT}').stdout.count('LISTEN'):
            return True
    return False


def undo():
    baks = sorted(glob.glob(BAK + '*'))
    if not baks:
        sys.exit('нет копии базы')
    restart_with(lambda: shutil.copy2(baks[-1], DB))
    print(f'Вернул базу из {baks[-1]}.')


def check_with_xray(xs):
    """Xray itself must accept these settings (server side) before the panel gets them."""
    cfg = {'log': {'loglevel': 'warning'},
           'inbounds': [{'listen': '127.0.0.1', 'port': 1, 'protocol': 'vless',
                         'settings': {'clients': [{'id': '00000000-0000-4000-8000-000000000000'}], 'decryption': 'none'},
                         'streamSettings': {'network': 'xhttp', 'xhttpSettings': xs}}],
           'outbounds': [{'protocol': 'freedom'}]}
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
        json.dump(cfg, f)
    try:
        r = sh(XRAY, 'run', '-test', '-c', f.name)
    finally:
        os.unlink(f.name)
    if r.returncode != 0:
        sys.exit('Xray не принял настройки, ничего не менял:\n' + (r.stdout + r.stderr)[-600:])


def show_link():
    """What clients get for this host in the subscription: the vless link with the key masked, and its xhttp extra.
    Uses the subscription of the first client of the inbound, fetched locally from the panel's sub server."""
    import base64
    import re
    import ssl
    import urllib.parse
    import urllib.request
    db = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    st = dict(db.execute("select key, value from settings where key like 'sub%'").fetchall())
    settings = json.loads(db.execute('select settings from inbounds where port=?', (PORT,)).fetchone()[0])
    db.close()
    sub_id = next((c.get('subId') for c in settings.get('clients', []) if c.get('subId')), None)
    if not sub_id:
        sys.exit('у клиентов входа нет subId')
    scheme = 'https' if st.get('subCertFile') else 'http'
    path = st.get('subPath') or '/sub/'
    url = f'{scheme}://127.0.0.1:{st.get("subPort", "2096")}{path if path.endswith("/") else path + "/"}{sub_id}'
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    try:
        body = urllib.request.urlopen(url, context=ctx, timeout=10).read().decode('utf-8', 'replace')
    except Exception as e:
        sys.exit(f'не смог получить подписку с {scheme}://127.0.0.1:{st.get("subPort")}{path}… — {e}')
    try:
        body = base64.b64decode(body.strip() + '==').decode('utf-8', 'replace')
    except Exception:
        pass
    lines = [l for l in body.splitlines() if 'begetcdn' in l]
    if not lines:
        sys.exit('в подписке нет ссылки на begetcdn — хост выключен или скрыт')
    for l in lines:
        masked = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '***', l)
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(masked).query)
        print('ссылка:', masked.split('?')[0] + '?…')
        print('  type/mode/path:', q.get('type'), q.get('mode'), q.get('path'))
        extra = json.loads(q['extra'][0]) if 'extra' in q else {}
        print('  extra:', json.dumps(extra, ensure_ascii=False))
        missing = [k for k in ('sessionIDPlacement', 'sessionIDTable', 'sessionIDLength', 'seqPlacement', 'xPaddingPlacement') if k not in extra]
        print('  ✅ всё нужное для Beget есть в ссылке' if not missing else f'  ❌ в ссылке нет: {", ".join(missing)} — клиент пойдёт со старыми настройками')


def main():
    if '--undo' in sys.argv:
        return undo()
    if '--link' in sys.argv:
        return show_link()
    db = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    row = db.execute('select id, remark, stream_settings, enable from inbounds where port=?', (PORT,)).fetchone()
    db.close()
    if not row:
        sys.exit(f'нет входа на порту {PORT}')
    inb_id, remark, stream_raw, enabled = row
    stream = json.loads(stream_raw)
    if stream.get('network') != 'xhttp':
        sys.exit(f'вход {PORT} не xhttp ({stream.get("network")}) — ничего не меняю, пришли вывод Claude')
    xs = {k: v for k, v in stream.get('xhttpSettings', {}).items() if k not in DROP}
    xs.update(BEGET)
    stream['xhttpSettings'] = xs
    check_with_xray(xs)

    bak = BAK + time.strftime('%Y%m%d-%H%M%S')
    def apply():
        shutil.copy2(DB, bak)
        w = sqlite3.connect(DB)
        with w:
            w.execute('update inbounds set stream_settings=?, enable=1 where id=?', (json.dumps(stream, ensure_ascii=False), inb_id))
        w.close()
    listening = restart_with(apply)
    print(f'Вход {PORT} ({remark}): xhttp для Beget, включён. Копия базы: {bak}')
    print('xhttpSettings:', json.dumps(xs, ensure_ascii=False))
    print('Xray слушает порт 2058 ✅' if listening else '!! порт 2058 не слушается — пришли `systemctl status x-ui` Claude (откат: --undo)')


if __name__ == '__main__':
    main()
