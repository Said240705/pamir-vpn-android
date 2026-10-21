// Тесты разбора подписки и сборки настроек Xray. Запуск: node --test desktop/test/
// Ключи и адреса здесь выдуманные. Если рядом лежит xray (XRAY_BIN), каждый собранный конфиг проверяется им самим.
import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { parseLink, parseSubscription, buildConfig, outbound, cleanName, isLte, isStub } from "../ui/xray.js";

const ID = "11111111-2222-4333-8444-555555555555";
const PORTS = { socks: 10808, http: 10809 };

const REALITY = `vless://${ID}@203.0.113.10:443?type=tcp&security=reality&pbk=AbCdEfGhIjKlMnOpQrStUvWxYz0123456789-_abcde&fp=chrome&sni=www.amazon.com&sid=6ba85179e30d4fc2&spx=%2F&flow=xtls-rprx-vision&encryption=none#%F0%9F%87%AA%F0%9F%87%B8%20%D0%98%D1%81%D0%BF%D0%B0%D0%BD%D0%B8%D1%8F%20-1%20user_test01%20%7C%2042%20%D0%B4%D0%BD%D0%B5%D0%B9`;
const EXTRA = JSON.stringify({
  xPaddingObfsMode: true, xPaddingPlacement: "header", xPaddingHeader: "X-Request-Pad", xPaddingMethod: "tokenish",
  sessionIDPlacement: "cookie", sessionIDKey: "sid", sessionIDTable: "hex", sessionIDLength: "32-32",
  seqPlacement: "cookie", seqKey: "seq", uplinkDataPlacement: "body",
});
const XHTTP = `vless://${ID}@cdn.example.net:443?type=xhttp&path=%2Fapi%2Fstream%2F&host=cdn.example.net&mode=packet-up&extra=${encodeURIComponent(EXTRA)}&security=tls&sni=cdn.example.net&fp=chrome&alpn=h2%2Chttp%2F1.1#%F0%9F%87%B7%F0%9F%87%BA%20LTE%20%D0%9E%D0%B1%D1%85%D0%BE%D0%B4%203`;
const WS = `vless://${ID}@ws.example.net:443?type=ws&path=%2Fapi%2Fsync%2F&host=ws.example.net&security=tls&sni=ws.example.net#%F0%9F%87%B7%F0%9F%87%BA%20LTE%20%D0%9E%D0%B1%D1%85%D0%BE%D0%B4`;
const VMESS = "vmess://" + Buffer.from(JSON.stringify({ v: "2", ps: "vm", add: "198.51.100.7", port: "8443", id: ID, aid: "0", scy: "auto", net: "grpc", path: "svc", tls: "tls", sni: "g.example.net" })).toString("base64");
const TROJAN = "trojan://secret@198.51.100.8:443?type=tcp&sni=t.example.net#tr";
const SS = "ss://" + Buffer.from("chacha20-ietf-poly1305:pw").toString("base64") + "@198.51.100.9:8388#ss";
const STUB = `vless://${ID}@127.0.0.1:1?type=tcp#%E2%9B%94%20%D0%9B%D0%B8%D0%BC%D0%B8%D1%82%20%D1%83%D1%81%D1%82%D1%80%D0%BE%D0%B9%D1%81%D1%82%D0%B2`;

test("reality: поля как в Android", () => {
  const p = parseLink(REALITY);
  assert.equal(p.address, "203.0.113.10");
  assert.equal(p.port, 443);
  assert.equal(p.id, ID);
  const o = outbound(p);
  assert.equal(o.settings.vnext[0].users[0].flow, "xtls-rprx-vision");
  assert.equal(o.streamSettings.security, "reality");
  assert.deepEqual(o.streamSettings.realitySettings, {
    serverName: "www.amazon.com", fingerprint: "chrome", publicKey: "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789-_abcde", shortId: "6ba85179e30d4fc2", spiderX: "/",
  });
  assert.deepEqual(cleanName(p.name), { flag: "🇪🇸", name: "Испания 1" });
  assert.equal(isLte(p), false);
});

test("xhttp через Beget: extra целиком уходит в xhttpSettings", () => {
  const p = parseLink(XHTTP);
  const o = outbound(p);
  assert.equal(o.streamSettings.network, "xhttp");
  assert.equal(o.streamSettings.xhttpSettings.mode, "packet-up");
  assert.equal(o.streamSettings.xhttpSettings.path, "/api/stream/");
  assert.deepEqual(o.streamSettings.xhttpSettings.extra, JSON.parse(EXTRA));
  assert.deepEqual(o.streamSettings.tlsSettings.alpn, ["h2", "http/1.1"]);
  assert.equal(isLte(p), true);
});

test("ws, vmess/grpc, trojan, shadowsocks", () => {
  const ws = outbound(parseLink(WS));
  assert.deepEqual(ws.streamSettings.wsSettings, { host: "ws.example.net", path: "/api/sync/" });
  const vm = outbound(parseLink(VMESS));
  assert.equal(vm.streamSettings.grpcSettings.serviceName, "svc");
  assert.equal(vm.streamSettings.tlsSettings.serverName, "g.example.net");
  const tr = outbound(parseLink(TROJAN));
  assert.equal(tr.settings.servers[0].password, "secret");
  assert.equal(tr.streamSettings.security, "tls");
  const ss = parseLink(SS);
  assert.equal(ss.method, "chacha20-ietf-poly1305");
  assert.equal(ss.password, "pw");
});

test("подписка base64 и заглушка", () => {
  const body = Buffer.from([REALITY, XHTTP, "мусор", STUB].join("\n")).toString("base64");
  const list = parseSubscription(body);
  assert.equal(list.length, 3);
  assert.equal(isStub(list[2]), true);
  assert.equal(parseSubscription([WS, TROJAN].join("\r\n")).length, 2);
});

test("полный конфиг проверяет сам xray", { skip: !process.env.XRAY_BIN && "XRAY_BIN не задан" }, () => {
  const dir = mkdtempSync(join(tmpdir(), "mognu-"));
  for (const [i, link] of [REALITY, XHTTP, WS, VMESS, TROJAN, SS].entries()) {
    const f = join(dir, `c${i}.json`);
    writeFileSync(f, JSON.stringify(buildConfig(parseLink(link), PORTS)));
    const out = execFileSync(process.env.XRAY_BIN, ["run", "-test", "-c", f], { encoding: "utf8" });
    assert.match(out, /Configuration OK/, link.slice(0, 20));
  }
});

test("режим «весь трафик»: вход TUN, xray принимает", () => {
  const cfg = buildConfig(parseLink(REALITY), PORTS, { tun: true });
  assert.equal(cfg.inbounds[0].protocol, "tun");
  assert.deepEqual(cfg.inbounds[0].settings.autoSystemRoutingTable, ["0.0.0.0/0", "::/0"]);
  assert.equal(cfg.dns.queryStrategy, "UseIPv4");
  assert.equal(cfg.routing.rules[0].outboundTag, "dns-out");
  if (!process.env.XRAY_BIN) return;
  const f = join(mkdtempSync(join(tmpdir(), "mognu-")), "tun.json");
  writeFileSync(f, JSON.stringify(cfg));
  assert.match(execFileSync(process.env.XRAY_BIN, ["run", "-test", "-c", f], { encoding: "utf8" }), /Configuration OK/);
});
