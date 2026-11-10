#!/usr/bin/env python3
"""Проверка «как телефон через Испанию»: прямо на основном сервере поднимается временный клиент Xray
с ТЕСТОВЫМ клиентом (почта содержит «test») и через вход «Испании» открываются Google, кабинет и админка.
Печатаются только коды ответов и время — ключи, почты и адреса людей не выводятся. Ничего не меняет:
клиент живёт ~30 секунд во временной папке и удаляется.

    python3 test_spain_path.py            оба входа «Испании» (65535 и 4443)
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time

DB = "/etc/x-ui/x-ui.db"
BIN_DIR = "/usr/local/x-ui/bin"
URLS = ["https://www.google.com/generate_204", "https://mognu.app/", "https://mognu.app/admin/login.html"]

xray = next((os.path.join(BIN_DIR, f) for f in sorted(os.listdir(BIN_DIR)) if f.startswith("xray-linux")), None)
if not xray:
    sys.exit("Не нашёл программу xray в " + BIN_DIR)

ro = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
rows = ro.execute("SELECT port, protocol, settings, stream_settings FROM inbounds WHERE port IN (65535, 4443) ORDER BY port DESC").fetchall()
ro.close()


def outbound(port, protocol, settings, stream):
    st = json.loads(stream or "{}")
    clients = json.loads(settings or "{}").get("clients", [])
    c = next((c for c in clients if "test" in (c.get("email") or "").lower()), None)
    if not c:
        return None, "нет тестового клиента"
    if protocol != "vless":
        return None, "протокол " + protocol + " — проверка умеет только vless"
    user = {"id": c["id"], "encryption": "none"}
    if c.get("flow"):
        user["flow"] = c["flow"]
    ss = {"network": st.get("network", "tcp"), "security": st.get("security", "none")}
    net = ss["network"]
    if st.get(net + "Settings"):
        ns = dict(st[net + "Settings"])
        ns.pop("acceptProxyProtocol", None)
        ss[net + "Settings"] = ns
    if ss["security"] == "reality":
        r = st.get("realitySettings", {})
        ss["realitySettings"] = {
            "serverName": (r.get("serverNames") or [""])[0],
            "publicKey": r.get("settings", {}).get("publicKey", ""),
            "shortId": (r.get("shortIds") or [""])[0],
            "fingerprint": r.get("settings", {}).get("fingerprint") or "chrome",
            "spiderX": r.get("settings", {}).get("spiderX", ""),
        }
    elif ss["security"] == "tls":
        t = st.get("tlsSettings", {})
        ss["tlsSettings"] = {"serverName": t.get("serverName", ""), "allowInsecure": True,
                             "fingerprint": t.get("settings", {}).get("fingerprint") or "chrome"}
    return {"protocol": "vless", "settings": {"vnext": [{"address": "127.0.0.1", "port": port, "users": [user]}]},
            "streamSettings": ss}, None


for port, protocol, settings, stream in rows:
    out, err = outbound(port, protocol, settings, stream)
    name = "Испания-1" if port == 65535 else "Испания-2"
    if err:
        print(f"{name} ({port}): {err}")
        continue
    socks = 10800 + port % 100
    cfg = {"log": {"loglevel": "error"},
           "inbounds": [{"listen": "127.0.0.1", "port": socks, "protocol": "socks", "settings": {"udp": False}}],
           "outbounds": [out]}
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "c.json")
        with open(path, "w") as f:
            json.dump(cfg, f)
        os.chmod(path, 0o600)
        p = subprocess.Popen([xray, "run", "-c", path], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        time.sleep(1.5)
        print(f"{name} ({port}), {out['streamSettings']['network']}/{out['streamSettings']['security']}:")
        for u in URLS:
            # --socks5-hostname: имя сайта узнаёт сервер (как в телефоне через VPN)
            r = subprocess.run(["curl", "-so", "/dev/null", "-m", "10", "--socks5-hostname", f"127.0.0.1:{socks}",
                                "-w", "%{http_code} %{time_total}s", u], capture_output=True, text=True)
            print(f"   {r.stdout or '000'}  {u}")
        p.terminate()
        try:
            e = p.communicate(timeout=5)[1]
        except subprocess.TimeoutExpired:
            p.kill()
            e = ""
        e = "\n".join(l for l in (e or "").splitlines() if "uuid" not in l.lower())[:300]
        if e.strip():
            print("   ошибки клиента:", e)
