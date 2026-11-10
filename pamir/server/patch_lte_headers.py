#!/usr/bin/env python3
"""LTE Обход вылетал: сервер отклонял часть запросов с данными от телефона.

В LTE (xhttp packet-up, uplinkDataPlacement=header) данные от телефона идут в заголовках GET-запроса
кусками по 3–4 КБ, а одна отправка может занимать до ~1 МБ. Лимиты сервера были меньше:
  • Xray: serverMaxHeaderBytes по умолчанию 8192 (+4096 у Go) → ответ 431, соединение у человека обрывается;
  • nginx: large_client_header_buffers по умолчанию 4×8k = 32 КБ → ответ 400.
В журнале nginx — около 40 таких отказов за 20 минут. Скрипт поднимает оба лимита; телефонам ничего обновлять не надо.

  • входы LTE (2056, 2058): xhttpSettings.serverMaxHeaderBytes = 2000000 (только для сервера);
  • nginx: /etc/nginx/conf.d/mognu-lte-headers.conf — large_client_header_buffers 256 8k (память берётся по мере надобности).

Копия базы — /etc/x-ui/x-ui.db.bak-lte-headers; nginx — новый файл (откат: удалить его), nginx -t с откатом.
Повторный запуск ничего не дублирует.

    python3 patch_lte_headers.py            показать, что изменится
    python3 patch_lte_headers.py --apply    применить (панель перезапускается — запускать через nohup)
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys

DB = "/etc/x-ui/x-ui.db"
PORTS = (2056, 2058)
MAX_HDR = 2000000
NGX = "large_client_header_buffers 256 8k;"
APPLY = "--apply" in sys.argv

# --- Xray: входы LTE
ro = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
rows = ro.execute(f"SELECT id, port, remark, stream_settings FROM inbounds WHERE port IN ({','.join('?' * len(PORTS))})", PORTS).fetchall()
ro.close()
db_changes = []
for iid, port, remark, st in rows:
    s = json.loads(st or "{}")
    x = s.get("xhttpSettings")
    if s.get("network") != "xhttp" or x is None:
        print(f"вход {port}: не xhttp — пропускаю")
        continue
    cur = x.get("serverMaxHeaderBytes", 0)
    print(f"вход {port} ({remark.strip()}): serverMaxHeaderBytes {cur or 'по умолчанию 8192'} → {MAX_HDR}")
    if cur != MAX_HDR:
        x["serverMaxHeaderBytes"] = MAX_HDR
        db_changes.append((json.dumps(s, ensure_ascii=False, indent=2), iid))

# --- nginx: на уровне http (conf.d) — так лимит действует при любом имени сервера (SNI CDN и Host могут различаться)
CONF = "/etc/nginx/conf.d/mognu-lte-headers.conf"
ngx_changes = []
if not os.path.exists(CONF):
    inc = subprocess.run(["grep", "-q", "conf.d/\\*.conf", "/etc/nginx/nginx.conf"]).returncode == 0
    if not inc:
        sys.exit("nginx.conf не подключает conf.d/*.conf — ничего не меняю. Пришлите: grep -n include /etc/nginx/nginx.conf")
    print(f"nginx: + {CONF}: {NGX}")
    ngx_changes.append((CONF, "# mognu: данные LTE (xhttp) идут в заголовках; было 4×8k → ответ 400\n" + NGX + "\n"))
else:
    print(f"nginx: {CONF} уже есть")

if not db_changes and not ngx_changes:
    sys.exit("Менять нечего — уже так.")
if not APPLY:
    sys.exit("\nЭто проверка. Применить: nohup python3 patch_lte_headers.py --apply > /root/lte-headers.log 2>&1 &")

# nginx — сначала: не требует перезапуска и сразу проверяется
for path, new in ngx_changes:
    open(path, "w", encoding="utf-8").write(new)
t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
if t.returncode != 0:
    for path, _ in ngx_changes:
        os.remove(path)
    print("\n".join(l for l in t.stderr.splitlines() if "emerg" in l or "error" in l)[:600])
    sys.exit("nginx -t не прошёл — вернул файлы, ничего не изменено.")
if ngx_changes:
    subprocess.run(["systemctl", "reload", "nginx"], check=True)
    print("nginx: готово")

if db_changes:
    shutil.copy2(DB, DB + ".bak-lte-headers")
    subprocess.run(["systemctl", "stop", "x-ui"], check=True)
    try:
        c = sqlite3.connect(DB)
        c.executemany("UPDATE inbounds SET stream_settings = ? WHERE id = ?", db_changes)
        c.commit()
        c.close()
    finally:
        subprocess.run(["systemctl", "start", "x-ui"], check=True)
    print("Xray: готово")
print("Готово: лимиты для LTE подняты")
