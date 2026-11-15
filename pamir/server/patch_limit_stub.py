#!/usr/bin/env python3
"""Заглушка «лимит устройств» в подписке: понятный текст и отдельный журнал отказов.

Когда все места на ключе заняты, nginx (блок @pamir_limit в pamir-sub-proxy.conf) отдаёт вместо серверов
заглушку. Прежний текст предлагал только купить место за 50 ₽ или продлить ключ — про то, что старое
устройство можно отключить бесплатно, там не было. А чаще всего место занято именно старым приложением:
Incy убрали из App Store, человек ставит OneXray, а единственное место всё ещё за Incy.

Теперь:
1. Заглушка и объявление говорят, что старое приложение можно отключить: ключ → «Устройства».
2. Каждый отказ дополнительно пишется в /var/log/nginx/pamir_limit.log (время, путь подписки, приложение) —
   по нему кабинет присылает владельцу ключа сообщение со списком устройств (admin_mognu.py, limit_notify).
   Общий журнал pamir_sub.log пишется как раньше.

Копия файла — /root/pamir-sub-proxy.conf.bak-limitstub; nginx -t — при ошибке файл возвращается.
Повторный запуск ничего не меняет.

    python3 patch_limit_stub.py            показать тексты
    python3 patch_limit_stub.py --apply    применить (nginx reload, соединения не рвутся)
"""
import base64
import os
import shutil
import subprocess
import sys
import urllib.parse

P = os.path.realpath("/etc/nginx/sites-enabled/pamir-sub-proxy.conf")
BAK = "/root/pamir-sub-proxy.conf.bak-limitstub"   # не рядом: nginx читает все файлы из sites-enabled
BOT = "@pamirlink_bot"
TITLE = "Mognu VPN · все места заняты"
ANNOUNCE = ("❌ Все места на ключе заняты.\n"   # Happ показывает объявление до 200 символов
            "🗑 Старое приложение (Incy, Happ) не нужно? Отключите бесплатно: бот или mognu.app → ключ → «Устройства».\n"
            f"➕ Или добавьте место за 50 ₽ — {BOT}")
SERVERS = ["❌ Все места на ключе заняты",
           "🗑 Отключите старое: ключ → «Устройства»",
           f"➕ Добавить место — {BOT}",
           "🔑 Или ключ неактивен — продлите в боте"]
LOG_FORMAT = "log_format pamir_limit_log '$msec $uri $http_user_agent';"


def b64(text):
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


body = "\n".join(f"vless://00000000-0000-0000-0000-00000000000{i}@127.0.0.1:1?encryption=none&type=tcp#"
                 + urllib.parse.quote(name, safe="") for i, name in enumerate(SERVERS))
BLOCK = f'''location @pamir_limit {{
        default_type text/plain;
        access_log /var/log/nginx/pamir_sub.log pamir_sub_log;
        access_log /var/log/nginx/pamir_limit.log pamir_limit_log;  # mognu: отказы — для сообщения владельцу ключа
        add_header announce "base64:{b64(ANNOUNCE)}" always;
        add_header profile-title "base64:{b64(TITLE)}" always;
        add_header support-url "https://t.me/{BOT[1:]}" always;
        add_header profile-update-interval "1" always;
        return 200 "{b64(body)}";'''

s = open(P, encoding="utf-8").read()
a = s.find("location @pamir_limit")
if a < 0:
    sys.exit("Блока @pamir_limit нет — ничего не меняю.")
b = s.find("\n    }", a)
if b < 0:
    sys.exit("Не нашёл конец блока @pamir_limit — ничего не меняю.")
new = s[:a] + BLOCK + s[b:]
if LOG_FORMAT not in new:
    first = new.find("log_format pamir_sub_log")
    if first < 0:
        sys.exit("Нет log_format pamir_sub_log — файл устроен иначе, ничего не меняю.")
    new = new[:first] + LOG_FORMAT + "\n" + new[first:]
print("название:", TITLE)
print("объявление:", ANNOUNCE.replace("\n", " / "), f"({len(ANNOUNCE)} символов)")
print("«серверы»:", " / ".join(SERVERS))
if new == s:
    sys.exit("Уже так — менять нечего.")
if "--apply" not in sys.argv:
    sys.exit("Это проверка. Применить: python3 patch_limit_stub.py --apply")
shutil.copy2(P, BAK)
open(P, "w", encoding="utf-8").write(new)
t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
if t.returncode != 0:
    shutil.copy2(BAK, P)
    print("\n".join(l for l in t.stderr.splitlines() if "emerg" in l or "error" in l)[:600])
    sys.exit("nginx -t не прошёл — вернул файл, ничего не изменено. Пришлите строки выше.")
subprocess.run(["systemctl", "reload", "nginx"], check=True)
print("Готово. Копия:", BAK)
