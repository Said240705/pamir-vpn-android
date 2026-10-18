#!/usr/bin/env python3
"""Вход 2058 (🇷🇺 LTE Обход 3) — на xhttp, который проходит через Beget CDN (вариант C из mognu_beget_xhttp_test.py).

Beget режет UUID с дефисами где угодно, случайные части пути, параметры в Referer и данные в адресе, но пропускает
32 hex-символа в cookie, случайную набивку в заголовке и отдаёт длинный ответ по частям. Поэтому: packet-up, номер
сессии — 32 hex в cookie «sid», номер куска — в cookie «seq», набивка — в заголовке, отправка — обычным POST.
Остальные настройки входа (xmux, размеры кусков) остаются как были. Ключи людей не меняются.

Панель держит базу открытой, поэтому на пару секунд останавливаем x-ui (Xray перезапустится — у всех переподключение),
правим базу и запускаем. Перед этим конфиг проверяется самим Xray, а база копируется в /root. Если SSH идёт через
этот же VPN, он оборвётся — скрипт это переживёт и доделает сам; итог — в /root/setup_beget_inbound.log.

    python3 setup_beget_inbound.py          применить и включить вход
    python3 setup_beget_inbound.py --undo   вернуть базу из последней копии
"""
import glob
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time

DB = '/etc/x-ui/x-ui.db'
XRAY = '/usr/local/x-ui/bin/xray-linux-amd64'
PORT = 2058
BAK = '/root/x-ui.db.bak-beget-'
LOG = '/root/setup_beget_inbound.log'

BEGET = {
    'mode': 'packet-up',
    'xPaddingObfsMode': True, 'xPaddingPlacement': 'header', 'xPaddingHeader': 'X-Request-Pad', 'xPaddingMethod': 'tokenish',
    'sessionIDPlacement': 'cookie', 'sessionIDKey': 'sid', 'sessionIDTable': 'hex', 'sessionIDLength': '32-32',
    'seqPlacement': 'cookie', 'seqKey': 'seq',
    'uplinkDataPlacement': 'body',
}
# sessionIDLength as a "from-to" string like the panel's other ranges: a plain number is dropped from the share link,
# and a client without it fails with "sessionIDTable or sessionIDLength is too small".
# uplinkHTTPMethod GET is not what passed through Beget (POST did); the query padding key is unused with header placement
DROP = ('uplinkHTTPMethod', 'xPaddingKey')


def sh(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def say(text):
    """Print, and keep a copy in LOG: the SSH session may already be gone (it can run through this very VPN)."""
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(time.strftime('%H:%M:%S ') + text + '\n')
    try:
        print(text, flush=True)
    except OSError:
        pass


def restart_with(apply):
    """Stop the panel, run apply(), start it again — and start it again even if apply() fails.
    Stopping the panel drops the VPN, and with it an SSH session that runs through it: the hangup must not kill us
    before the panel is back up."""
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    signal.signal(signal.SIGPIPE, signal.SIG_IGN)
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
    say(f'Вернул базу из {baks[-1]}.')


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


def main():
    if '--undo' in sys.argv:
        return undo()
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
    say(f'Вход {PORT} ({remark}): xhttp для Beget, включён. Копия базы: {bak}')
    say('xhttpSettings: ' + json.dumps(xs, ensure_ascii=False))
    say('Xray слушает порт 2058 ✅' if listening else '!! порт 2058 не слушается — пришли `systemctl status x-ui` Claude (откат: --undo)')


if __name__ == '__main__':
    main()
