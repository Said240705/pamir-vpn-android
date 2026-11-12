#!/usr/bin/env python3
"""Новая локация на узле: копия входа другого узла (по умолчанию «🇩🇪 Германия - 1», порт 443) — те же
протокол, Reality и клиенты, но на другом узле и порту. Строки в «Hosts» входа-образца тоже копируются.
Основная панель после перезапуска сама отправляет вход на узел (синхронизация «Все инбаунды»).

Копия базы — /etc/x-ui/x-ui.db.bak-clone-<порт>. Всё в одной транзакции; повторный запуск ничего не дублирует.

    python3 clone_node_inbound.py --node Польша --port 47443 --remark "🇵🇱 Польша"            показать
    python3 clone_node_inbound.py --node Польша --port 47443 --remark "🇵🇱 Польша" --apply    создать (через nohup)
    python3 clone_node_inbound.py --port 47443 --apply --undo                               убрать
"""
import json
import shutil
import sqlite3
import subprocess
import sys
import time

DB = "/etc/x-ui/x-ui.db"


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


SRC_PORT = int(arg("--from", 443))
PORT = int(arg("--port", 0))
NODE = arg("--node")
REMARK = arg("--remark")
APPLY, UNDO = "--apply" in sys.argv, "--undo" in sys.argv
if not PORT:
    sys.exit("Укажите --port")

ro = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
ro.row_factory = sqlite3.Row
exist = ro.execute("SELECT id, remark FROM inbounds WHERE port = ?", (PORT,)).fetchone()
if UNDO:
    if not exist:
        sys.exit(f"Входа :{PORT} нет — убирать нечего.")
    print(f"уберу вход :{PORT} «{exist['remark']}» (id {exist['id']}), его привязки клиентов и Hosts")
else:
    if exist:
        sys.exit(f"Порт {PORT} уже занят входом «{exist['remark']}» — ничего не меняю.")
    if not NODE or not REMARK:
        sys.exit("Укажите --node и --remark")
    node = ro.execute("SELECT id, name, status, address FROM nodes WHERE name = ?", (NODE,)).fetchone()
    if not node:
        sys.exit(f"Нет узла «{NODE}» — сначала добавьте его в панели (Узлы).")
    src = ro.execute("SELECT * FROM inbounds WHERE port = ?", (SRC_PORT,)).fetchone()
    if not src:
        sys.exit(f"Нет входа-образца :{SRC_PORT}")
    src_node = ro.execute("SELECT address FROM nodes WHERE id = ?", (src["node_id"],)).fetchone() if src["node_id"] else None
    old_addr = src_node["address"] if src_node else None
    links = ro.execute("SELECT * FROM client_inbounds WHERE inbound_id = ?", (src["id"],)).fetchall()
    hosts = ro.execute("SELECT * FROM hosts WHERE inbound_id = ?", (src["id"],)).fetchall()
    print(f"копия «{src['remark'].strip()}» (:{SRC_PORT}, узел {src['node_id']}) → «{REMARK}» (:{PORT}, узел «{node['name']}» id {node['id']}, {node['status']})")
    print(f"клиентов: {len(links)}, строк в Hosts: {len(hosts)}; адрес {old_addr} → {node['address']}")
    ep = json.loads(src["stream_settings"] or "{}").get("externalProxy") or []
    print("External proxy образца:", [f"{p.get('dest')}:{p.get('port')}" for p in ep] or "нет")
ro.close()
if not APPLY:
    sys.exit("Это проверка. Применить: добавьте --apply (через nohup — панель перезапускается)")

shutil.copy2(DB, f"{DB}.bak-clone-{PORT}")
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
            tag = f"in-{PORT}-tcp"
            row.update(port=PORT, tag=tag, remark=REMARK, node_id=node["id"], up=0, down=0)
            if "last_traffic_reset_time" in row:
                row["last_traffic_reset_time"] = 0
            st = json.loads(row["stream_settings"] or "{}")
            for p in st.get("externalProxy") or []:   # адрес для приложений — новый узел и свой порт
                p["port"] = PORT
                if old_addr and p.get("dest") == old_addr:
                    p["dest"] = node["address"]
            row["stream_settings"] = json.dumps(st, ensure_ascii=False, indent=2)
            ks = list(row)
            iid = c.execute(f"INSERT INTO inbounds ({','.join(ks)}) VALUES ({','.join('?' * len(ks))})", [row[k] for k in ks]).lastrowid
            now = int(time.time() * 1000)
            for ln in links:
                d = dict(ln)
                d["inbound_id"] = iid
                if "created_at" in d:
                    d["created_at"] = now
                ks = list(d)
                c.execute(f"INSERT INTO client_inbounds ({','.join(ks)}) VALUES ({','.join('?' * len(ks))})", [d[k] for k in ks])
            for h in hosts:
                d = dict(h)
                d.pop("id")
                d.update(inbound_id=iid, remark=REMARK, created_at=now, updated_at=now)
                if d.get("port") == SRC_PORT:
                    d["port"] = PORT
                for k in ("address", "sni", "host_header"):
                    if old_addr and d.get(k) == old_addr:
                        d[k] = node["address"]
                ks = list(d)
                c.execute(f"INSERT INTO hosts ({','.join(ks)}) VALUES ({','.join('?' * len(ks))})", [d[k] for k in ks])
    c.close()
finally:
    subprocess.run(["systemctl", "start", "x-ui"], check=True)
print("Готово:", f"вход :{PORT} убран" if UNDO else f"«{REMARK}» на :{PORT}, узел «{NODE}», клиентов {len(links)}")
