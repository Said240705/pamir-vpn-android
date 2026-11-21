#!/usr/bin/env python3
"""Порт 8444 на основном сервере — только наши сайты, без маскировки VPN.

Хостинг Финляндии (TIHOST) запрещает маскировку под чужой сайт: на 443 Финляндии (пересылка на 443 основного) без
имени сайта отвечал Xray Reality с сертификатом amazon.com — сервер приостановили. Порт 443 на Финляндии закрыли, но
через него шли mognu.app (вход, оплата), источники CDN (o-ya, o-bee — LTE Обход и зеркало кабинета) и mognu.net.

Здесь в stream-блок nginx добавляется вход 8444 → 127.0.0.1:8443 (nginx с сайтами, мимо Xray), и в ufw он
открывается только для Финляндии. Финляндия пересылает свой 443 на 8444: сайты работают как раньше, а без имени
сайта или с чужим именем отвечает наш nginx со своим сертификатом — маскировки нет.

Копия конфига — <файл>.bak-sites8444; nginx -t не прошёл — файл возвращается. Повторный запуск ничего не меняет.
    python3 setup_sites_port.py            показать
    python3 setup_sites_port.py --apply    применить
"""
import glob
import shutil
import subprocess
import sys

PORT = 8444
RELAY = "31.77.6.71"
MARK = "# Mognu: сайты для Финляндии (setup_sites_port.py)"
BLOCK = f"""
    {MARK}
    server {{
        listen {PORT};
        proxy_pass 127.0.0.1:8443;
    }}
"""
ANCHOR = "proxy_pass $pamir_upstream;"

files = [f for f in ["/etc/nginx/nginx.conf"] + glob.glob("/etc/nginx/conf.d/*.conf") + glob.glob("/etc/nginx/modules-enabled/*.conf")
         if ANCHOR in open(f, encoding="utf-8").read()]
if len(files) != 1:
    sys.exit(f"Не нашёл единственный файл со stream-блоком ({files}) — ничего не меняю.")
F = files[0]
s = open(F, encoding="utf-8").read()
done = MARK in s
if not done:
    i = s.index(ANCHOR)
    j = s.index("}", i) + 1          # конец server { listen 443 ... }
    new = s[:j] + "\n" + BLOCK + s[j:]
ufw = subprocess.run(["ufw", "status"], capture_output=True, text=True).stdout
ufw_done = any(str(PORT) in l and RELAY in l for l in ufw.splitlines())
print(f"nginx ({F}): вход {PORT} → сайты — {'уже есть' if done else 'добавлю'}")
print(f"ufw: {PORT} только для {RELAY} — {'уже есть' if ufw_done else 'добавлю'}")
if "--apply" not in sys.argv:
    sys.exit("Это проверка. Применить: python3 setup_sites_port.py --apply")
if not done:
    shutil.copy2(F, F + ".bak-sites8444")
    open(F, "w", encoding="utf-8").write(new)
    t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
    if t.returncode != 0:
        shutil.copy2(F + ".bak-sites8444", F)
        sys.exit("nginx -t не прошёл — вернул файл:\n" + t.stderr.strip()[-400:])
    subprocess.run(["systemctl", "reload", "nginx"], check=True)
if not ufw_done:
    subprocess.run(["ufw", "allow", "from", RELAY, "to", "any", "port", str(PORT), "proto", "tcp"], check=True,
                   capture_output=True)
listening = f":{PORT} " in subprocess.run(["ss", "-ltn"], capture_output=True, text=True).stdout
print(f"Готово: nginx слушает {PORT}: {'да' if listening else 'НЕТ'}. Теперь на Финляндии: 443 → основной:{PORT}.")
