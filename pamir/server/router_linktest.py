#!/usr/bin/env python3
"""Живая проверка прямых ссылок для роутера на тестовом ключе (test@pamirlink.ru).

1. Собирает ссылки ключа так же, как их получит кабинет (router_links.py рядом).
2. На время проверки поднимает тестовому ключу лимит IP до 5 (иначе подключение с самого сервера засчиталось бы
   лишним устройством и панель могла бы его заблокировать), в конце ВСЕГДА возвращает прежний.
3. Для каждой ссылки запускает клиент Xray из панели (/usr/local/x-ui/bin) с локальным SOCKS и открывает через него
   страницу проверки связи. Печатает: локация, откуда взят адрес, ответ, время и страну выхода. Сами ссылки, UUID и
   адреса не печатает.

Запускать Python'ом бота:  cd /root/YadrenoVPN && <python бота> /root/router_linktest.py
"""
import asyncio
import glob
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse

ROOT = os.getenv("PAMIR_BOT_ROOT", "/root/YadrenoVPN")
DB = os.path.join(ROOT, "database", "vpn_bot.db")
HERE = os.path.dirname(os.path.abspath(__file__))
TEST_EMAIL = "test@pamirlink.ru"
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from router_links import build_links  # noqa: E402

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
user = conn.execute("SELECT id FROM users WHERE lower(email) = ?", (TEST_EMAIL,)).fetchone()
key = user and conn.execute("""SELECT id, server_id, panel_email FROM vpn_keys WHERE user_id = ? AND expires_at > datetime('now')
                               AND panel_email IS NOT NULL ORDER BY id DESC""", (user["id"],)).fetchone()
if not key:
    sys.exit(f"Нет активного ключа у {TEST_EMAIL} — ничего не делаю.")
server = dict(conn.execute("SELECT * FROM servers WHERE id = ?", (key["server_id"],)).fetchone())
conn.close()
EMAIL = key["panel_email"]
links = build_links(EMAIL)
print(f"Тестовый ключ ID {key['id']}: ссылок для роутера {len(links)}")
for l in links:
    print(f"  · {l['location']} (адрес из: {l['address_from']})")
if not links:
    sys.exit("Ссылок нет — смотреть router_links.py.")
xray = next(iter(sorted(glob.glob("/usr/local/x-ui/bin/xray-linux-*"))), None)
if not xray:
    sys.exit("Не нашёл xray в /usr/local/x-ui/bin — проверить подключение не могу (ссылки собраны).")


def outbound(link):
    u = urllib.parse.urlsplit(link)
    q = dict(urllib.parse.parse_qsl(u.query))
    user = {"id": urllib.parse.unquote(u.username), "encryption": "none"}
    if q.get("flow"):
        user["flow"] = q["flow"]
    return {"protocol": "vless", "settings": {"vnext": [{"address": u.hostname, "port": u.port, "users": [user]}]},
            "streamSettings": {"network": "tcp", "security": "reality", "realitySettings": {
                "serverName": q.get("sni", ""), "fingerprint": q.get("fp", "chrome"), "publicKey": q.get("pbk", ""),
                "shortId": q.get("sid", ""), "spiderX": q.get("spx", "")}}}


def check(link, port):
    cfg = {"log": {"loglevel": "warning"}, "inbounds": [{"listen": "127.0.0.1", "port": port, "protocol": "socks", "settings": {"udp": False}}],
           "outbounds": [outbound(link)]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(cfg, f)
        path = f.name
    proc = subprocess.Popen([xray, "run", "-c", path], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        time.sleep(1.5)
        if proc.poll() is not None:
            return "xray не запустился: " + proc.stderr.read().decode("utf-8", "replace").strip().splitlines()[-1][:120]
        tries = []
        for url in ("https://www.gstatic.com/generate_204", "https://cp.cloudflare.com/generate_204", "https://www.gstatic.com/generate_204"):
            r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code} %{time_total}", "--max-time", "15",
                                "--socks5-hostname", f"127.0.0.1:{port}", url], capture_output=True, text=True)
            code, _, sec = r.stdout.partition(" ")
            tries.append(f"{code or '—'}/{float(sec or 0):.1f}с")
        cc = subprocess.run(["curl", "-s", "--max-time", "10", "--socks5-hostname", f"127.0.0.1:{port}", "https://ipinfo.io/country"],
                            capture_output=True, text=True).stdout.strip()[:3]
        good = sum(t.startswith("204") for t in tries)
        verdict = "✅ работает" if good == len(tries) else "⚠️ с перебоями" if good else "❌ нет связи"
        return f"{verdict} (попытки: {', '.join(tries)}" + (f"; выход: {cc}" if cc else "") + ")"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        os.unlink(path)


async def main():
    from bot.services.panels.xui import XUIClient
    client = XUIClient(server)

    async def set_ip(value):
        rec = await client._get_client_record(EMAIL)
        cur, inbound_ids = client._split_record(rec)
        payload = client._client_payload(cur, email=EMAIL)
        payload["limitIp"] = int(value)
        ep = f"/panel/api/clients/update/{urllib.parse.quote(EMAIL, safe='')}"
        if inbound_ids:
            ep += "?inboundIds=" + ",".join(str(v) for v in sorted(inbound_ids))
        ok = lambda r: bool(r) and int(client._split_record(r)[0].get("limitIp") or 0) == int(value)  # noqa: E731
        if not ok(await client._write_with_state_check("POST", ep, data=payload, email=EMAIL, validator=ok)):
            raise RuntimeError("панель не подтвердила изменение лимита IP")

    try:
        before = client._split_record(await client._get_client_record(EMAIL))[0]
        old_ip = int(before.get("limitIp") or 0)
        print(f"\nлимит IP тестового ключа: {old_ip} → на время проверки 5")
        try:
            await set_ip(5)
            await asyncio.sleep(2)
            for i, l in enumerate(links):
                print(f"  {l['location']}: {check(l['link'], 20800 + i)}")
        finally:
            await set_ip(old_ip)
            after = client._split_record(await client._get_client_record(EMAIL))[0]
            print(f"вернул лимит IP: {after.get('limitIp')}")
    finally:
        if getattr(client, "close", None):
            await client.close()


asyncio.run(main())
