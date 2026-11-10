#!/usr/bin/env python3
"""LTE Обход: отправка с телефона обрывалась на CDN Яндекса.

Данные от телефона идут в заголовках GET-запроса (uplinkDataPlacement=header), по умолчанию до 1 МБ за раз
(~1,3 МБ заголовков) — столько CDN не пропускает: большие отправки (вход на сайт, фото, формы) рвались, страница
висела. Проверка mognu_cdn_test.py 2056 --chunks: при 32 КБ за раз отдача 1 МБ проходит (4,3 Мбит/с), сайты
открываются так же.

Скрипт ставит scMaxEachPostBytes = 32000 во входах LTE (2056, 2058). Это настройка и сервера (больше не примет),
и клиента — телефоны получают её с подпиской (в ссылке, в параметре extra), если панель её туда кладёт:
после применения скрипт проверяет подписку тестового клиента.

Копия базы — /etc/x-ui/x-ui.db.bak-lte-chunks. Повторный запуск ничего не дублирует.

    python3 patch_lte_chunks.py            показать
    python3 patch_lte_chunks.py --apply    применить (панель перезапускается — запускать через nohup)
    python3 patch_lte_chunks.py --check    есть ли настройка в подписке тестового клиента (и что в extra)
    python3 patch_lte_chunks.py --apply --value 1000000   вернуть серверу прежний лимит
"""
import base64
import json
import shutil
import sqlite3
import subprocess
import sys
import urllib.parse

DB = "/etc/x-ui/x-ui.db"
PORTS = (2056, 2058)
VALUE = int(sys.argv[sys.argv.index("--value") + 1]) if "--value" in sys.argv else 32000


def check():
    ro = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    sid = None
    for (st,) in ro.execute("SELECT settings FROM inbounds WHERE port = 2056"):
        sid = next((c.get("subId") for c in json.loads(st or "{}").get("clients", [])
                    if "test" in (c.get("email") or "").lower() and c.get("subId")), None)
    ro.close()
    if not sid:
        return print("проверка подписки: у тестового клиента нет subId на входе 2056")
    r = subprocess.run(["curl", "-s", "-m", "10", "https://mognu.app/sub/" + sid], capture_output=True, text=True)
    try:
        body = base64.b64decode(r.stdout.strip() + "=" * (-len(r.stdout.strip()) % 4)).decode("utf-8", "replace")
    except Exception:
        body = r.stdout
    found = False
    for line in body.splitlines():
        if "type=xhttp" not in line:
            continue
        name = urllib.parse.unquote(line.split("#", 1)[-1])
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(line.split("#", 1)[0]).query)
        extra = q.get("extra", [""])[0]
        has = "scMaxEachPostBytes" in extra
        found = found or has
        print(f"подписка: {name.strip()}: extra {'есть' if extra else 'нет'}, scMaxEachPostBytes {'есть' if has else 'нет'}")
        if extra and "--check" in sys.argv:
            print("   extra:", extra[:400])
    if not found:
        print("В подписке настройки нет — телефоны её не получат; пришлите этот вывод.")


if "--check" in sys.argv:
    check()
    sys.exit(0)

ro = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
rows = ro.execute(f"SELECT id, port, remark, stream_settings FROM inbounds WHERE port IN ({','.join('?' * len(PORTS))})", PORTS).fetchall()
ro.close()
changes = []
for iid, port, remark, st in rows:
    s = json.loads(st or "{}")
    x = s.get("xhttpSettings")
    if s.get("network") != "xhttp" or x is None:
        continue
    cur = x.get("scMaxEachPostBytes")
    print(f"вход {port} ({remark.strip()}): scMaxEachPostBytes {cur or 'по умолчанию 1000000'} → {VALUE}")
    if str(cur) != str(VALUE):
        x["scMaxEachPostBytes"] = VALUE
        changes.append((json.dumps(s, ensure_ascii=False, indent=2), iid))
if not changes:
    print("Менять нечего — уже так.")
    check()
    sys.exit(0)
if "--apply" not in sys.argv:
    sys.exit("\nЭто проверка. Применить: nohup python3 patch_lte_chunks.py --apply > /root/lte-chunks.log 2>&1 &")

shutil.copy2(DB, DB + ".bak-lte-chunks")
subprocess.run(["systemctl", "stop", "x-ui"], check=True)
try:
    c = sqlite3.connect(DB)
    c.executemany("UPDATE inbounds SET stream_settings = ? WHERE id = ?", changes)
    c.commit()
    c.close()
finally:
    subprocess.run(["systemctl", "start", "x-ui"], check=True)
print(f"Готово: {VALUE} байт за раз во входах LTE")
import time
time.sleep(5)
check()
