#!/usr/bin/env python3
"""«LTE (iPhone)»: вход 2059 через CDNvideo с обычными настройками xhttp — для приложений на ядре mihomo.

RabbitHole (iPhone, ядро mihomo) доходит через CDN до LTE Обход 1 и 2, но получает 400: особые настройки входов
(данные и заполнение в заголовках, сессия в cookie — параметр extra в ссылке) он не переносит и шлёт обычный xhttp.
Этот вход — копия LTE Обход 2 (2057) без особых настроек: сессия в пути, данные в теле POST, короткое заполнение
(CDNvideo не пропускает длинное). Путь /api/cvp/ на том же источнике o-bee (nginx → 127.0.0.1:2059).

Сначала только для тестовых клиентов (email содержит test): другие люди вход не видят. Когда проверим —
--all подключит всех клиентов LTE Обход 2.

Копии: база — /etc/x-ui/x-ui.db.bak-lteplain, сайт nginx — /root/<имя>.bak-lteplain. Повторный запуск ничего не
дублирует.

    python3 setup_lte_plain.py                    показать
    python3 setup_lte_plain.py --apply            создать (панель перезапускается — через nohup)
    python3 setup_lte_plain.py --apply --all      подключить всех клиентов LTE Обход 2
    python3 setup_lte_plain.py --apply --undo     убрать вход, строку Hosts и путь в nginx
"""
import glob
import json
import os
import random
import shutil
import sqlite3
import string
import subprocess
import sys
import time

DB = "/etc/x-ui/x-ui.db"
SRC_PORT, PORT = 2057, 2059
TAG = f"in-{PORT}-tcp"
REMARK = "🇷🇺 LTE (iPhone)"
SRC_PATH, PATH = "/api/cv/", "/api/cvp/"
APPLY, UNDO, ALL = "--apply" in sys.argv, "--undo" in sys.argv, "--all" in sys.argv
# остаются только обычные настройки; всё, что mihomo из ссылки не переносит, убираем
KEEP = ("path", "host", "mode", "xPaddingBytes", "scMaxEachPostBytes", "scMaxBufferedPosts",
        "scMinPostsIntervalMs", "serverMaxHeaderBytes", "noSSEHeader")


def site():
    for p in glob.glob("/etc/nginx/sites-enabled/*"):
        if "o-bee" in open(p, encoding="utf-8", errors="replace").read():
            return os.path.realpath(p)
    sys.exit("Не нашёл сайт o-bee в nginx — ничего не меняю.")


def block(text, path):
    """Текст блока «location <path> {…}» (с отступом и переводом строки) или None."""
    a = text.find(f"location {path} {{")
    if a < 0:
        return None
    a = text.rfind("\n", 0, a) + 1
    depth, i = 0, text.find("{", a)
    while i < len(text):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return text[a:text.find("\n", i) + 1]
        i += 1
    return None


ro = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
ro.row_factory = sqlite3.Row
exist = ro.execute("SELECT id FROM inbounds WHERE port = ?", (PORT,)).fetchone()
src = ro.execute("SELECT * FROM inbounds WHERE port = ?", (SRC_PORT,)).fetchone()
ci_cols = [r[1] for r in ro.execute("pragma table_info(client_inbounds)")]
key = next((c for c in ("client_id", "client_email", "email") if c in ci_cols), None)
if not key:
    sys.exit(f"client_inbounds устроена иначе ({ci_cols}) — ничего не меняю.")
test_ids = {r[0] for r in ro.execute(
    f"SELECT {'id' if key == 'client_id' else 'email'} FROM clients WHERE lower(email) LIKE '%test%'")}
P = site()
conf = open(P, encoding="utf-8").read()
src_block = block(conf, SRC_PATH)
have_block = block(conf, PATH)

if UNDO:
    if not exist and not have_block:
        sys.exit("Входа 2059 и пути в nginx нет — убирать нечего.")
    print(f"уберу вход {PORT}, его привязки, строку Hosts и путь {PATH} в nginx")
elif exist:
    n = ro.execute("SELECT count(*) FROM client_inbounds WHERE inbound_id = ?", (exist["id"],)).fetchone()[0]
    if not ALL:
        sys.exit(f"Вход {PORT} уже есть (id {exist['id']}, клиентов {n}). Подключить всех: --apply --all")
    links = ro.execute("SELECT * FROM client_inbounds WHERE inbound_id = ? AND " + key + " NOT IN "
                       "(SELECT " + key + " FROM client_inbounds WHERE inbound_id = ?)", (src["id"], exist["id"])).fetchall()
    print(f"подключу ко входу {PORT} ещё {len(links)} клиентов LTE Обход 2 (сейчас {n})")
else:
    if not src:
        sys.exit(f"Нет входа {SRC_PORT} — не с чего копировать.")
    if not src_block:
        sys.exit(f"Нет location {SRC_PATH} в {P} — не с чего копировать путь.")
    links = [ln for ln in ro.execute("SELECT * FROM client_inbounds WHERE inbound_id = ?", (src["id"],)).fetchall()
             if ln[key] in test_ids]
    if not links:
        sys.exit("У LTE Обход 2 нет тестового клиента (email с test) — не на ком проверять.")
    host = ro.execute("SELECT * FROM hosts WHERE inbound_id = ? ORDER BY id LIMIT 1", (src["id"],)).fetchone()
    if not host:
        sys.exit(f"У входа {SRC_PORT} нет строки в Hosts — не с чего копировать.")
    st = json.loads(src["stream_settings"])
    xs = {k: v for k, v in (st.get("xhttpSettings") or {}).items() if k in KEEP}
    xs["path"] = PATH
    st["xhttpSettings"] = xs
    print(f"копия «{src['remark'].strip()}» → «{REMARK}» (:{PORT}, {host['address']}{PATH}); тестовых клиентов: {len(links)}")
    print("xhttp:", json.dumps(xs, ensure_ascii=False))
ro.close()
if not APPLY:
    sys.exit("Это проверка. Применить: nohup python3 setup_lte_plain.py --apply > /root/lteplain.log 2>&1 &")

# nginx: путь /api/cvp/ → 2059 (копия блока /api/cv/), ставится перед ним
new_conf = conf
if UNDO and have_block:
    new_conf = conf.replace(have_block, "")
elif not UNDO and not have_block:
    new_conf = conf.replace(src_block, src_block.replace(SRC_PATH, PATH).replace(f":{SRC_PORT}", f":{PORT}") + src_block)
if new_conf != conf:
    bak = "/root/" + os.path.basename(P) + ".bak-lteplain"
    shutil.copy2(P, bak)
    open(P, "w", encoding="utf-8").write(new_conf)
    if subprocess.run(["nginx", "-t"], capture_output=True).returncode != 0:
        shutil.copy2(bak, P)
        sys.exit("nginx -t не прошёл — вернул сайт, база не тронута.")
    subprocess.run(["systemctl", "reload", "nginx"], check=True)
    print("nginx:", "путь убран" if UNDO else f"{PATH} → 127.0.0.1:{PORT}")

shutil.copy2(DB, DB + ".bak-lteplain")
subprocess.run(["systemctl", "stop", "x-ui"], check=True)
try:
    c = sqlite3.connect(DB)
    with c:
        now = int(time.time() * 1000)

        def add_links(iid, rows):
            for ln in rows:
                d = dict(ln)
                d.pop("id", None)
                d["inbound_id"] = iid
                if "created_at" in d:
                    d["created_at"] = now
                ks = list(d)
                c.execute(f"INSERT INTO client_inbounds ({','.join(ks)}) VALUES ({','.join('?' * len(ks))})", [d[k] for k in ks])

        if UNDO:
            if exist:
                iid = exist["id"]
                c.execute("DELETE FROM hosts WHERE inbound_id = ?", (iid,))
                c.execute("DELETE FROM client_inbounds WHERE inbound_id = ?", (iid,))
                c.execute("DELETE FROM inbounds WHERE id = ?", (iid,))
        elif exist:
            add_links(exist["id"], links)
        else:
            row = dict(src)
            row.pop("id")
            row.update(port=PORT, tag=TAG, remark=REMARK, up=0, down=0, stream_settings=json.dumps(st, ensure_ascii=False, indent=2))
            if "last_traffic_reset_time" in row:
                row["last_traffic_reset_time"] = 0
            ks = list(row)
            iid = c.execute(f"INSERT INTO inbounds ({','.join(ks)}) VALUES ({','.join('?' * len(ks))})", [row[k] for k in ks]).lastrowid
            add_links(iid, links)
            h = dict(host)
            h.pop("id")
            h.update(inbound_id=iid, remark=REMARK, path=PATH,
                     group_id="".join(random.choices(string.ascii_lowercase + string.digits, k=16)),
                     created_at=now, updated_at=now)
            ks = list(h)
            c.execute(f"INSERT INTO hosts ({','.join(ks)}) VALUES ({','.join('?' * len(ks))})", [h[k] for k in ks])
    c.close()
finally:
    subprocess.run(["systemctl", "start", "x-ui"], check=True)
print("Готово:", f"вход {PORT} убран" if UNDO else (f"подключено ещё {len(links)}" if exist else f"«{REMARK}» на :{PORT}, тестовых клиентов {len(links)}"))
