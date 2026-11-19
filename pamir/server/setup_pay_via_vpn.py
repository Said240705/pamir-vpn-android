#!/usr/bin/env python3
"""Оплата СБП/картой (ЮKassa) с основного сервера — через VPN-выход другой локации (по умолчанию «Польша»).

С 19.11 20:12 сеть Сбера (ЮKassa, sberbank.ru) не пускает российский сервер, и цепочка setup_pay_via_relay.sh
(основной → Финляндия → российский → ЮKassa) порвалась. router_linktest.py --yookassa показал: выход «Польши»
ЮKassa пускает. Поэтому основной сервер ходит в ЮKassa как обычный клиент VPN:
  · служба mognu-pay-xray — отдельный Xray из панели (/usr/local/x-ui/bin) с одним входом 127.0.0.1:PORT, который
    всё принятое отправляет на api.yookassa.ru:443 через ссылку тестового ключа на нужной локации;
  · iptables OUTPUT: соединения основного сервера с адресами ЮKassa:443 → 127.0.0.1:PORT (REDIRECT).
TLS, сертификат и имя сайта не меняются — бот ничего не замечает. Пересылка через Финляндию (mognu-pay-via-relay)
выключается — её правила перехватили бы те же соединения. Переживает перезагрузку. Ссылку, UUID и адреса не печатает;
конфиг с ключом — /etc/mognu-pay/xray.json (только root).

Запуск — Python'ом бота (нужна база бота и router_links.py рядом):
    cd /root/YadrenoVPN && venv/bin/python /root/setup_pay_via_vpn.py            показать
    cd /root/YadrenoVPN && venv/bin/python /root/setup_pay_via_vpn.py --apply    включить
    cd /root/YadrenoVPN && venv/bin/python /root/setup_pay_via_vpn.py --undo     убрать (вернуть Финляндию — bash setup_pay_via_relay.sh)
Другая локация: LOCATION=Германия ... --apply. Если ЮKassa сменит адреса — перезапустить с --apply.
"""
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.parse

ROOT = os.getenv("PAMIR_BOT_ROOT", "/root/YadrenoVPN")
DB = os.path.join(ROOT, "database", "vpn_bot.db")
HERE = os.path.dirname(os.path.abspath(__file__))
TEST_EMAIL = "test@pamirlink.ru"
LOCATION = os.getenv("LOCATION", "Польша")
PORT = int(os.getenv("PORT", "18443"))
HOST = "api.yookassa.ru"
CONF_DIR = "/etc/mognu-pay"
CONF = f"{CONF_DIR}/xray.json"
UNIT = "/etc/systemd/system/mognu-pay-xray.service"
RULES = "/usr/local/sbin/mognu-pay-xray-rules.sh"
sys.path.insert(0, HERE)


def sh(*cmd, check=False):
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def yookassa_ips():
    return sorted({a[4][0] for a in socket.getaddrinfo(HOST, 443, socket.AF_INET, socket.SOCK_STREAM)})


def rules_script(ips, op):
    lines = ["#!/bin/sh", "# Mognu: ЮKassa → локальный Xray (setup_pay_via_vpn.py)"]
    for ip in ips:
        spec = f"OUTPUT -p tcp -d {ip} --dport 443 -j REDIRECT --to-ports {PORT}"
        if op == "add":
            lines.append(f"iptables -t nat -C {spec} 2>/dev/null || iptables -t nat -A {spec}")
        else:
            lines.append(f"while iptables -t nat -C {spec} 2>/dev/null; do iptables -t nat -D {spec}; done")
    return "\n".join(lines) + "\n"


def current_rule_ips():
    out = sh("iptables", "-t", "nat", "-S", "OUTPUT").stdout
    return sorted({p.split()[p.split().index("-d") + 1].split("/")[0] for p in out.splitlines()
                   if f"--to-ports {PORT}" in p and "-d" in p.split()})


def undo():
    ips = current_rule_ips()
    subprocess.run(["sh", "-c", rules_script(ips, "del")])
    sh("systemctl", "disable", "--now", "mognu-pay-xray")
    for f in (UNIT, RULES, CONF):
        if os.path.exists(f):
            os.remove(f)
    sh("systemctl", "daemon-reload")
    print("Убрано. Вернуть цепочку через Финляндию: bash /root/setup_pay_via_relay.sh")


if "--undo" in sys.argv:
    undo()
    sys.exit(0)

from router_links import build_links  # noqa: E402

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
user = conn.execute("SELECT id FROM users WHERE lower(email) = ?", (TEST_EMAIL,)).fetchone()
key = user and conn.execute("""SELECT id, panel_email, expires_at FROM vpn_keys WHERE user_id = ? AND expires_at > datetime('now')
                               AND panel_email IS NOT NULL ORDER BY id DESC""", (user["id"],)).fetchone()
conn.close()
if not key:
    sys.exit(f"Нет активного ключа у {TEST_EMAIL} — ничего не делаю.")
link = next((l for l in build_links(key["panel_email"]) if LOCATION.lower() in l["location"].lower()), None)
if not link:
    sys.exit(f"У тестового ключа нет локации «{LOCATION}» — ничего не делаю.")
xray = next((os.path.join("/usr/local/x-ui/bin", f) for f in sorted(os.listdir("/usr/local/x-ui/bin")) if f.startswith("xray-linux")), None)
if not xray:
    sys.exit("Не нашёл xray в /usr/local/x-ui/bin — ничего не делаю.")
ips = yookassa_ips()

u = urllib.parse.urlsplit(link["link"])
q = dict(urllib.parse.parse_qsl(u.query))
vuser = {"id": urllib.parse.unquote(u.username), "encryption": "none"}
if q.get("flow"):
    vuser["flow"] = q["flow"]
cfg = {"log": {"loglevel": "warning"},
       "inbounds": [{"listen": "127.0.0.1", "port": PORT, "protocol": "dokodemo-door",
                     "settings": {"address": HOST, "port": 443, "network": "tcp"}}],
       "outbounds": [{"protocol": "vless", "settings": {"vnext": [{"address": u.hostname, "port": u.port, "users": [vuser]}]},
                      "streamSettings": {"network": "tcp", "security": "reality", "realitySettings": {
                          "serverName": q.get("sni", ""), "fingerprint": q.get("fp", "chrome"), "publicKey": q.get("pbk", ""),
                          "shortId": q.get("sid", ""), "spiderX": q.get("spx", "")}}}]}

print(f"выход: {link['location']} (тестовый ключ ID {key['id']}, действует до {key['expires_at']})")
print(f"адреса ЮKassa: {', '.join(ips)} → 127.0.0.1:{PORT}")
relay_on = sh("systemctl", "is-enabled", "mognu-pay-via-relay").stdout.strip() == "enabled"
if relay_on:
    print("пересылка через Финляндию (mognu-pay-via-relay) будет выключена")
if "--apply" not in sys.argv:
    sys.exit("Это проверка. Включить: cd /root/YadrenoVPN && venv/bin/python /root/setup_pay_via_vpn.py --apply")

os.makedirs(CONF_DIR, mode=0o700, exist_ok=True)
fd = os.open(CONF, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    json.dump(cfg, f)
r = sh(xray, "run", "-test", "-c", CONF)
if r.returncode != 0:
    os.remove(CONF)
    sys.exit("Xray не принял конфиг — ничего не включаю: " + (r.stdout + r.stderr).strip().splitlines()[-1][:160])

old = current_rule_ips()
with open(RULES, "w") as f:
    f.write(rules_script(old, "del") + "\n".join(rules_script(ips, "add").splitlines()[2:]) + "\n")
os.chmod(RULES, 0o755)
with open(UNIT, "w") as f:
    f.write(f"""[Unit]
Description=Mognu: payment API via VPN exit ({LOCATION})
After=network-online.target
Wants=network-online.target
[Service]
ExecStartPre=/bin/sh -c 'ls /usr/local/x-ui/bin/xray-linux-* >/dev/null'
ExecStart=/bin/sh -c 'exec $(ls /usr/local/x-ui/bin/xray-linux-* | head -1) run -c {CONF}'
ExecStartPost=/bin/sh {RULES}
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
""")
if relay_on:
    relay = "/root/setup_pay_via_relay.sh" if os.path.exists("/root/setup_pay_via_relay.sh") else "/usr/local/sbin/mognu-pay-via-relay.sh"
    sh("bash", relay, "--undo")
sh("systemctl", "daemon-reload")
sh("systemctl", "enable", "mognu-pay-xray")
sh("systemctl", "restart", "mognu-pay-xray", check=True)
time.sleep(3)
print("служба:", sh("systemctl", "is-active", "mognu-pay-xray").stdout.strip(), "| правил:", len(current_rule_ips()))
r = sh("curl", "-s", "-o", "/dev/null", "-m", "15", "-w", "%{http_code} за %{time_total}s", f"https://{HOST}/v3/payments")
print(f"проверка: {HOST} → {r.stdout or '000'} (401 — ЮKassa отвечает, оплата работает)")
