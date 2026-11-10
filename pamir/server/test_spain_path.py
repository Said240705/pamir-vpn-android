#!/usr/bin/env python3
"""Проверка «как телефон через Испанию»: прямо на основном сервере поднимается временный клиент Xray
с ТЕСТОВЫМ клиентом (почта содержит «test») и через вход «Испании» открываются Google, кабинет и админка.
Печатаются только коды ответов и время — ключи, почты и адреса людей не выводятся. Ничего не меняет:
клиент живёт ~30 секунд во временной папке и удаляется.

    python3 test_spain_path.py            оба входа «Испании» (65535 и 4443)
    python3 test_spain_path.py --local    как Xray этого сервера открывает свой сайт: через 127.0.0.1
                                          и через собственный внешний адрес (временный Xray, без входов)
    python3 test_spain_path.py --mirror   копия рабочего Xray (вход «Испания-1», те же правила и исходящие)
                                          на 127.0.0.1:10865 с подробным журналом; рабочий Xray не трогается
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time

DB = "/etc/x-ui/x-ui.db"
BIN_DIR = "/usr/local/x-ui/bin"
URLS = ["https://www.google.com/generate_204", "https://mognu.app/", "https://mognu.app/admin/login.html", "http://mognu.app/"]

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


def run_xray(cfg, socks, urls, name):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "c.json")
        with open(path, "w") as f:
            json.dump(cfg, f)
        os.chmod(path, 0o600)
        # журнал Xray идёт в stdout
        p = subprocess.Popen([xray, "run", "-c", path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(1.5)
        print(name + ":", flush=True)
        for u in urls:
            r = subprocess.run(["curl", "-so", "/dev/null", "-m", "8", "--socks5-hostname", f"127.0.0.1:{socks}",
                                "-w", "%{http_code} %{time_total}s", u], capture_output=True, text=True)
            print(f"   {r.stdout or '000'}  {u}", flush=True)
        p.terminate()
        try:
            e = p.communicate(timeout=5)[0]
        except subprocess.TimeoutExpired:
            p.kill()
            e = ""
        keep = re.compile(r"freedom|redirect|block|reject|denied|fail|error|127\.0\.0\.1|:443", re.I)
        lines = [re.sub(r"\s+", " ", re.sub(r"email:.*", "", l))[:200] for l in (e or "").splitlines() if keep.search(l) and "uuid" not in l.lower()]
        if lines:
            print("   сообщения Xray:\n     " + "\n     ".join(lines[-int(os.environ.get("LINES_KEEP", "8")):]))


if "--local" in sys.argv:
    me = subprocess.run(["curl", "-s4", "-m", "5", "https://api.ipify.org"], capture_output=True, text=True).stdout.strip() or "78.17.158.230"
    for target in ("127.0.0.1", me):
        cfg = {"log": {"loglevel": "debug"},
               "inbounds": [{"listen": "127.0.0.1", "port": 10899, "protocol": "socks", "settings": {"udp": False}}],
               "outbounds": [{"protocol": "freedom", "settings": {"redirect": target + ":443"}}]}
        run_xray(cfg, 10899, ["https://mognu.app/admin/login.html"], "напрямую на " + ("127.0.0.1" if target == "127.0.0.1" else "свой внешний адрес"))
    sys.exit(0)

if "--mirror" in sys.argv:
    live = json.load(open(os.path.join(BIN_DIR, "config.json")))
    inb = next((i for i in live["inbounds"] if i.get("port") == 65535), None)
    row = next((r for r in rows if r[0] == 65535), None)
    if not inb or not row:
        sys.exit("Не нашёл вход 65535")
    out, err = outbound(*row)
    if err:
        sys.exit(err)
    srv = dict(inb, listen="127.0.0.1", port=10865)
    srv["settings"] = dict(srv["settings"])
    srv["settings"]["clients"] = [c for c in srv["settings"].get("clients", []) if "test" in (c.get("email") or "").lower()]
    rules = [r for r in live["routing"]["rules"] if r.get("outboundTag") != "api"]
    out["settings"]["vnext"][0]["port"] = 10865
    cfg = {"log": {"loglevel": "debug"},
           "inbounds": [srv, {"listen": "127.0.0.1", "port": 10898, "protocol": "socks", "settings": {"udp": False}, "tag": "test-socks"}],
           "outbounds": list(live["outbounds"]) + [dict(out, tag="test-client")],
           "routing": {"domainStrategy": live["routing"].get("domainStrategy", "AsIs"),
                       "rules": [{"type": "field", "inboundTag": ["test-socks"], "outboundTag": "test-client"}] + rules}}
    os.environ.setdefault("LINES_KEEP", "30")
    run_xray(cfg, 10898, ["https://www.google.com/generate_204", "https://mognu.app/admin/login.html"], "копия «Испании-1»")
    sys.exit(0)

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
