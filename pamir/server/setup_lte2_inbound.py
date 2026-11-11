#!/usr/bin/env python3
"""LTE Обход 2 (CDNvideo): вход 2057 — копия «LTE Обход» (2056) с путём /api/cv/, те же клиенты, и строка
в «Hosts» с адресом CDN — так LTE 2 появляется в подписке у тех же людей, что и LTE 1.

Источник для CDN — o-bee.pamirlink.ru (setup_lte2_origin.sh: nginx /api/cv/ → 127.0.0.1:2057).
Копия базы — /etc/x-ui/x-ui.db.bak-lte2. Всё в одной транзакции; повторный запуск ничего не дублирует.

    python3 setup_lte2_inbound.py                 показать
    python3 setup_lte2_inbound.py --apply         создать (панель перезапускается — через nohup)
    python3 setup_lte2_inbound.py --apply --undo  убрать вход 2057 и его строку в Hosts
"""
import json
import random
import shutil
import sqlite3
import string
import subprocess
import sys
import time

DB = "/etc/x-ui/x-ui.db"
SRC_PORT, PORT = 2056, 2057
TAG = "in-2057-tcp"
REMARK = "🇷🇺 LTE Обход 2"
PATH = "/api/cv/"
CDN = "9yy3u3u15o.a.trbcdn.net"
APPLY, UNDO = "--apply" in sys.argv, "--undo" in sys.argv


def cols(c, t):
    return [r[1] for r in c.execute(f"pragma table_info({t})")]


ro = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
ro.row_factory = sqlite3.Row
exist = ro.execute("SELECT id FROM inbounds WHERE port = ?", (PORT,)).fetchone()
src = ro.execute("SELECT * FROM inbounds WHERE port = ?", (SRC_PORT,)).fetchone()
if UNDO:
    if not exist:
        sys.exit("Входа 2057 нет — убирать нечего.")
    print(f"уберу вход {PORT} (id {exist['id']}), его клиентов-привязки и строку в Hosts")
elif exist:
    sys.exit(f"Вход {PORT} уже есть (id {exist['id']}) — ничего не меняю.")
else:
    if not src:
        sys.exit(f"Нет входа {SRC_PORT} — не с чего копировать.")
    links = ro.execute("SELECT * FROM client_inbounds WHERE inbound_id = ?", (src["id"],)).fetchall()
    host = ro.execute("SELECT * FROM hosts WHERE inbound_id = ? ORDER BY id LIMIT 1", (src["id"],)).fetchone()
    if not host:
        sys.exit(f"У входа {SRC_PORT} нет строки в Hosts — не с чего копировать.")
    st = json.loads(src["stream_settings"])
    if st.get("network") != "xhttp":
        sys.exit("Вход 2056 не xhttp — ничего не меняю.")
    print(f"копия «{src['remark'].strip()}» (:{SRC_PORT}) → «{REMARK}» (:{PORT}), путь {PATH}; клиентов: {len(links)}")
    print(f"Hosts: {CDN}{PATH} (как у «{host['remark'].strip()}»)")
ro.close()
if not APPLY:
    sys.exit("Это проверка. Применить: nohup python3 setup_lte2_inbound.py --apply > /root/lte2.log 2>&1 &")

shutil.copy2(DB, DB + ".bak-lte2")
subprocess.run(["systemctl", "stop", "x-ui"], check=True)
try:
    c = sqlite3.connect(DB)
    with c:
        if UNDO:
            iid = exist["id"]
            c.execute("DELETE FROM hosts WHERE inbound_id = ?", (iid,))
            c.execute("DELETE FROM client_inbounds WHERE inbound_id = ?", (iid,))
            c.execute("DELETE FROM inbounds WHERE id = ?", (iid,))
        else:
            row = dict(src)
            row.pop("id")
            st["xhttpSettings"]["path"] = PATH
            row.update(port=PORT, tag=TAG, remark=REMARK, up=0, down=0, stream_settings=json.dumps(st, ensure_ascii=False, indent=2))
            if "last_traffic_reset_time" in row:
                row["last_traffic_reset_time"] = 0
            ks = list(row)
            cur = c.execute(f"INSERT INTO inbounds ({','.join(ks)}) VALUES ({','.join('?' * len(ks))})", [row[k] for k in ks])
            iid = cur.lastrowid
            now = int(time.time() * 1000)
            for ln in links:
                d = dict(ln)
                d["inbound_id"] = iid
                if "created_at" in d:
                    d["created_at"] = now
                ks = list(d)
                c.execute(f"INSERT INTO client_inbounds ({','.join(ks)}) VALUES ({','.join('?' * len(ks))})", [d[k] for k in ks])
            h = dict(host)
            h.pop("id")
            h.update(inbound_id=iid, remark=REMARK, address=CDN, sni=CDN, host_header=CDN, path=PATH,
                     group_id="".join(random.choices(string.ascii_lowercase + string.digits, k=16)),
                     created_at=now, updated_at=now)
            ks = list(h)
            c.execute(f"INSERT INTO hosts ({','.join(ks)}) VALUES ({','.join('?' * len(ks))})", [h[k] for k in ks])
    c.close()
finally:
    subprocess.run(["systemctl", "start", "x-ui"], check=True)
print("Готово:", f"вход {PORT} убран" if UNDO else f"«{REMARK}» на :{PORT} ({CDN}{PATH}), клиентов {len(links)}")
