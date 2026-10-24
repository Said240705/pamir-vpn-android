"""Mognu: прямые ссылки vless:// ключа для роутера (тариф «На весь дом»).

Подписку панель без HWID не отдаёт (проверено router_subtest.py), а пакеты для роутеров HWID не шлют. Поэтому роутеру
даём сами ссылки на локации — собираем их из базы 3x-ui (только чтение): клиент ключа (по panel_email), его inbound'ы
VLESS + Reality по TCP (их понимают sing-box/Podkop, PassWall, HomeProxy), адрес подключения каждой локации.
Локации на XHTTP («LTE Обход») пропускаются: роутерные пакеты этот транспорт не поддерживают.

Только стандартная библиотека: файл кладётся рядом с роутером бэкенда (routers/pamir_router_links.py) и им же
пользуется проверка router_linktest.py.
"""
import json
import re
import sqlite3
from urllib.parse import quote, urlparse

XUI_DB = "/etc/x-ui/x-ui.db"


def _host(value):
    """Адрес без схемы, порта и пути: «https://a.b:123/x» → «a.b»."""
    v = str(value or "").strip()
    if not v:
        return ""
    if "://" not in v:
        v = "//" + v
    try:
        return urlparse(v).hostname or ""
    except ValueError:
        return ""


def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def build_links(panel_email, xui_db=XUI_DB):
    """→ [{"location", "link", "address_from", "inbound_id"}]; пусто, если клиента нет или он выключен."""
    conn = sqlite3.connect(f"file:{xui_db}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        settings = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")} if "settings" in tables else {}
        client = conn.execute("SELECT * FROM clients WHERE email = ?", (panel_email,)).fetchone() if "clients" in tables else None
        if client is not None and "enable" in client.keys() and not int(client["enable"] or 0):
            return []
        inbound_ids = None
        overrides = {}
        if client is not None and "client_inbounds" in tables:
            rows = conn.execute("SELECT inbound_id, flow_override FROM client_inbounds WHERE client_id = ?", (client["id"],)).fetchall()
            inbound_ids = {r["inbound_id"] for r in rows}
            overrides = {r["inbound_id"]: r["flow_override"] for r in rows if r["flow_override"]}
        nodes = {}
        if "nodes" in tables:
            for n in conn.execute("SELECT * FROM nodes"):
                nodes[n["id"]] = n
        hosts = {}
        if "hosts" in tables:
            hc = _cols(conn, "hosts")
            for h in conn.execute("SELECT * FROM hosts ORDER BY sort_order, id"):
                if ("is_disabled" in hc and int(h["is_disabled"] or 0)) or h["inbound_id"] in hosts:
                    continue
                hosts[h["inbound_id"]] = h
        out = []
        ic = _cols(conn, "inbounds")
        for ib in conn.execute("SELECT * FROM inbounds ORDER BY COALESCE(sub_sort_index, 0), id" if "sub_sort_index" in ic else "SELECT * FROM inbounds ORDER BY id"):
            if not int(ib["enable"] or 0) or ib["protocol"] != "vless":
                continue
            if inbound_ids is not None and ib["id"] not in inbound_ids:
                continue
            try:
                ss = json.loads(ib["stream_settings"] or "{}")
                st = json.loads(ib["settings"] or "{}")
            except ValueError:
                continue
            if ss.get("network") != "tcp" or ss.get("security") != "reality":
                continue
            cl = next((c for c in st.get("clients") or [] if c.get("email") == panel_email), None)
            uuid = (cl or {}).get("id") or (client["uuid"] if client is not None and "uuid" in client.keys() else "")
            if not uuid or (cl is not None and cl.get("enable") is False):
                continue
            flow = overrides.get(ib["id"]) or (cl or {}).get("flow") or (client["flow"] if client is not None and "flow" in client.keys() else "") or ""
            if "disable_flow" in ib.keys() and int(ib["disable_flow"] or 0):
                flow = ""
            rs = ss.get("realitySettings") or {}
            rset = rs.get("settings") or {}
            pbk = rset.get("publicKey") or rs.get("publicKey") or ""
            sni = (rs.get("serverNames") or [""])[0] or rset.get("serverName") or ""
            sid = next((s for s in rs.get("shortIds") or [] if s), "")
            fp = rset.get("fingerprint") or "chrome"
            spx = rset.get("spiderX") or ""
            port = ib["port"]
            # адрес: свой адрес у inbound'а → «хост» панели → адрес узла → домен подписки → listen
            host_row = hosts.get(ib["id"])
            address, source = "", ""
            if "share_addr" in ib.keys() and _host(ib["share_addr"]):
                address, source = _host(ib["share_addr"]), "share_addr"
            elif host_row is not None and _host(host_row["address"]):
                address, source = _host(host_row["address"]), "host"
                port = host_row["port"] or port
                sni = host_row["sni"] or sni
                fp = host_row["fingerprint"] or fp
            elif ib["node_id"] and ib["node_id"] in nodes and _host(nodes[ib["node_id"]]["address"]):
                address, source = _host(nodes[ib["node_id"]]["address"]), "node"
            elif _host(settings.get("subDomain")):
                address, source = _host(settings.get("subDomain")), "subDomain"
            elif _host(ib["listen"]) and ib["listen"] not in ("0.0.0.0", "::"):
                address, source = _host(ib["listen"]), "listen"
            if not address or not pbk:
                continue
            params = [("type", "tcp"), ("encryption", "none"), ("security", "reality"), ("pbk", pbk), ("fp", fp), ("sni", sni)]
            if sid:
                params.append(("sid", sid))
            if spx:
                params.append(("spx", spx))
            if flow:
                params.append(("flow", flow))
            header = ((ss.get("tcpSettings") or {}).get("header") or {}).get("type")
            if header and header != "none":
                continue  # HTTP-маскировка на TCP роутерам не нужна и поддерживается не везде
            location = re.sub(r"\s+", " ", str(ib["remark"] or f"Локация {ib['id']}")).strip()
            q = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params)
            host = f"[{address}]" if ":" in address else address
            out.append({"location": location, "inbound_id": ib["id"], "address_from": source,
                        "link": f"vless://{uuid}@{host}:{port}?{q}#{quote('Mognu ' + location, safe='')}"})
        return out
    finally:
        conn.close()
