// Подписка → настройки Xray. Логика та же, что в Android (v2rayNG: fmt/*Fmt.kt и core/CoreOutboundBuilder.kt),
// чтобы один и тот же ключ работал на телефоне и на компьютере одинаково. Модуль без зависимостей:
// его подключает интерфейс (ui/app.js) и проверяют тесты в Node (desktop/test/xray.test.mjs).

// ── разбор подписки ──────────────────────────────────────────────────────────

function b64decode(s) {
  s = String(s).trim().replace(/\s+/g, "").replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  const bin = atob(s);
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

// %XX → символы; битая последовательность остаётся как есть (как Utils.decodeURIComponent в Android)
function dec(v) {
  try { return decodeURIComponent(v); } catch (e) { return v; }
}

function query(raw) {
  const out = {};
  if (!raw) return out;
  for (const part of raw.split("&")) {
    if (!part) continue;
    const i = part.indexOf("=");
    const k = i < 0 ? part : part.slice(0, i);
    out[k] = i < 0 ? "" : dec(part.slice(i + 1));
  }
  return out;
}

// scheme://userinfo@host:port?query#fragment — без URL(): ему не нравятся ни схемы vless/trojan, ни IPv6 без скобок
function splitLink(link) {
  const m = /^([a-z0-9]+):\/\/([^@]*)@(\[[^\]]+\]|[^:/?#]+):(\d+)\/?(?:\?([^#]*))?(?:#(.*))?$/i.exec(link.trim());
  if (!m) return null;
  return { scheme: m[1].toLowerCase(), user: dec(m[2]), host: m[3].replace(/^\[|\]$/g, ""), port: +m[4], q: query(m[5]), name: dec(m[6] || "") };
}

// Общие поля транспорта и шифрования (FmtBase.getItemFormQuery)
function fromQuery(p, q) {
  p.network = q.type || "tcp";
  p.headerType = q.headerType;
  p.host = q.host;
  p.path = q.path;
  p.mode = q.mode;
  p.serviceName = q.serviceName;
  p.authority = q.authority;
  p.xhttpExtra = q.extra;
  p.finalMask = q.fm;
  p.security = q.security === "tls" || q.security === "reality" ? q.security : "";
  p.insecure = ["insecure", "allowInsecure", "allow_insecure"].some((k) => q[k] === "1");
  p.sni = q.sni;
  p.fp = q.fp;
  p.alpn = q.alpn;
  p.ech = q.ech;
  p.pbk = q.pbk;
  p.sid = q.sid;
  p.spx = q.spx;
  p.pqv = q.pqv;
  p.flow = q.flow;
  return p;
}

function parseVless(link) {
  const u = splitLink(link);
  if (!u) return null;
  return fromQuery({ protocol: "vless", name: u.name || "none", address: u.host, port: u.port, id: u.user, encryption: u.q.encryption || "none" }, u.q);
}

function parseTrojan(link) {
  const u = splitLink(link);
  if (!u) return null;
  const p = fromQuery({ protocol: "trojan", name: u.name || "none", address: u.host, port: u.port, password: u.user }, u.q);
  if (!u.q.security) p.security = "tls";
  return p;
}

function parseVmess(link) {
  let j;
  try { j = JSON.parse(b64decode(link.slice("vmess://".length))); } catch (e) { return null; }
  if (!j || !j.add) return null;
  return {
    protocol: "vmess", name: j.ps || "none", address: j.add, port: +j.port, id: j.id, scy: j.scy || "auto",
    network: j.net || "tcp", headerType: j.type, host: j.host, path: j.path, serviceName: j.path, authority: j.authority, mode: j.mode,
    security: j.tls === "tls" || j.tls === "reality" ? j.tls : "", sni: j.sni, fp: j.fp, alpn: j.alpn, insecure: j.allowInsecure === "1" || j.allowInsecure === true,
  };
}

// ss://base64(method:password)@host:port#name (SIP002) или ss://base64(method:password@host:port)#name
function parseShadowsocks(link) {
  let u = splitLink(link);
  if (u) {
    let creds = u.user;
    if (!creds.includes(":")) { try { creds = b64decode(creds); } catch (e) { return null; } }
    const i = creds.indexOf(":");
    return { protocol: "shadowsocks", name: u.name || "none", address: u.host, port: u.port, method: creds.slice(0, i), password: creds.slice(i + 1), network: "tcp", security: "" };
  }
  const m = /^ss:\/\/([^#]+)(?:#(.*))?$/i.exec(link.trim());
  if (!m) return null;
  let plain;
  try { plain = b64decode(m[1]); } catch (e) { return null; }
  u = splitLink("ss://" + plain);
  if (!u) return null;
  const i = u.user.indexOf(":");
  return { protocol: "shadowsocks", name: dec(m[2] || "") || "none", address: u.host, port: u.port, method: u.user.slice(0, i), password: u.user.slice(i + 1), network: "tcp", security: "" };
}

export function parseLink(link) {
  const s = String(link).trim();
  const scheme = s.slice(0, s.indexOf("://")).toLowerCase();
  try {
    if (scheme === "vless") return parseVless(s);
    if (scheme === "vmess") return parseVmess(s);
    if (scheme === "trojan") return parseTrojan(s);
    if (scheme === "ss") return parseShadowsocks(s);
  } catch (e) { /* битая строка — пропускаем */ }
  return null;
}

// Тело подписки: base64 со списком ссылок по строкам или сразу текст со ссылками
export function parseSubscription(body) {
  let text = String(body || "").trim();
  if (!text.includes("://")) {
    try { text = b64decode(text); } catch (e) { return []; }
  }
  return text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean).map(parseLink).filter(Boolean);
}

// ── сборка исходящего соединения (CoreOutboundBuilder) ───────────────────────

function isDomain(s) { return !!s && /[a-z]/i.test(s) && !s.includes(":"); }
function clean(o) {
  for (const k of Object.keys(o)) if (o[k] === undefined || o[k] === null || o[k] === "") delete o[k];
  return o;
}
function parseJson(s) {
  if (!s) return undefined;
  try { return JSON.parse(s); } catch (e) { return undefined; }
}

function transport(p) {
  const ss = { network: p.network || "tcp" };
  let sni;
  switch (ss.network) {
    case "tcp":
    case "raw":
      ss.network = "tcp";
      if (p.headerType === "http") {
        const host = (p.host || "").split(",").map((h) => h.trim()).filter(Boolean);
        ss.tcpSettings = { header: { type: "http", request: { path: (p.path || "/").split(",").map((x) => x.trim()), headers: { Host: host } } } };
        sni = host[0];
      } else {
        ss.tcpSettings = { header: { type: "none" } };
        sni = p.host;
      }
      break;
    case "ws":
      ss.wsSettings = { host: p.host || "", path: p.path || "/" };
      sni = p.host;
      break;
    case "httpupgrade":
      ss.httpupgradeSettings = { host: p.host || "", path: p.path || "/" };
      sni = p.host;
      break;
    case "xhttp":
    case "splithttp":
      ss.network = "xhttp";
      ss.xhttpSettings = clean({ host: p.host || "", path: p.path || "/", mode: p.mode, extra: parseJson(p.xhttpExtra) });
      if (!ss.xhttpSettings.host) ss.xhttpSettings.host = "";
      sni = p.host;
      break;
    case "grpc":
      ss.grpcSettings = { multiMode: p.mode === "multi", serviceName: p.serviceName || "", authority: p.authority || "", idle_timeout: 60, health_check_timeout: 20 };
      sni = p.authority;
      break;
    case "h2":
    case "http": {
      ss.network = "h2";
      const host = (p.host || "").split(",").map((h) => h.trim()).filter(Boolean);
      ss.httpSettings = { host, path: p.path || "/" };
      sni = host[0];
      break;
    }
  }
  const fm = parseJson(p.finalMask);
  if (fm) ss.finalmask = fm;
  return { ss, sni };
}

function security(ss, p, sniExt) {
  if (!p.security) return;
  const sni = p.sni || (isDomain(sniExt) ? sniExt : isDomain(p.address) ? p.address : sniExt);
  const t = clean({
    allowInsecure: p.insecure || undefined,
    serverName: sni,
    fingerprint: p.fp,
    alpn: p.alpn ? p.alpn.split(",").map((a) => a.trim()).filter(Boolean) : undefined,
    echConfigList: p.ech,
    publicKey: p.pbk,
    shortId: p.sid,
    spiderX: p.spx,
    mldsa65Verify: p.pqv,
  });
  if (t.alpn && !t.alpn.length) delete t.alpn;
  ss.security = p.security;
  if (p.security === "tls") ss.tlsSettings = t;
  else ss.realitySettings = t;
}

export function outbound(p, tag = "proxy") {
  let settings;
  if (p.protocol === "vless") settings = { vnext: [{ address: p.address, port: p.port, users: [clean({ id: p.id, encryption: p.encryption || "none", flow: p.flow, level: 8 })] }] };
  else if (p.protocol === "vmess") settings = { vnext: [{ address: p.address, port: p.port, users: [{ id: p.id, security: p.scy || "auto", level: 8 }] }] };
  else if (p.protocol === "trojan") settings = { servers: [clean({ address: p.address, port: p.port, password: p.password, flow: p.flow, level: 8 })] };
  else if (p.protocol === "shadowsocks") settings = { servers: [{ address: p.address, port: p.port, method: p.method, password: p.password, level: 8 }] };
  else throw new Error("unsupported protocol " + p.protocol);
  const { ss, sni } = p.protocol === "shadowsocks" ? { ss: { network: "tcp" }, sni: undefined } : transport(p);
  security(ss, p, sni);
  return { tag, protocol: p.protocol, settings, streamSettings: ss, mux: { enabled: false, concurrency: -1 } };
}

// ── полный конфиг ────────────────────────────────────────────────────────────

// Локальные адреса и сам компьютер — всегда напрямую. Без geoip.dat: явные диапазоны.
const PRIVATE_IP = ["127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "100.64.0.0/10", "::1/128", "fc00::/7", "fe80::/10"];

/**
 * profile — сервер из parseSubscription; ports — {socks, http} свободные порты на 127.0.0.1 (их выбирает Rust).
 * Режим «системный прокси»: браузеры и программы, которые его уважают, идут через socks/http-вход.
 */
export function buildConfig(profile, ports) {
  return {
    log: { loglevel: "warning" },
    inbounds: [
      { tag: "socks", listen: "127.0.0.1", port: ports.socks, protocol: "socks", settings: { auth: "noauth", udp: true },
        sniffing: { enabled: true, destOverride: ["http", "tls", "quic"], routeOnly: true } },
      { tag: "http", listen: "127.0.0.1", port: ports.http, protocol: "http", settings: {},
        sniffing: { enabled: true, destOverride: ["http", "tls"], routeOnly: true } },
    ],
    outbounds: [
      outbound(profile, "proxy"),
      { tag: "direct", protocol: "freedom", settings: {} },
      { tag: "block", protocol: "blackhole", settings: {} },
    ],
    routing: {
      domainStrategy: "AsIs",
      rules: [
        { type: "field", ip: PRIVATE_IP, outboundTag: "direct" },
        { type: "field", domain: ["localhost"], outboundTag: "direct" },
      ],
    },
  };
}

// Как в Android (PamirActivity.reloadServers, PamirWatch.cleanName): флаг и короткое имя из remarks,
// LTE — для белых списков, заглушка (127.x — «подписка не активна / лимит устройств») — не сервер.
export function cleanName(remarks) {
  let s = String(remarks || "").split("|")[0].trim();
  s = s.replace(/-?\s*user_[^\s|]*/g, "");
  const m = /^((?:\uD83C[\uDDE6-\uDDFF]){2})/.exec(s);
  const flag = m ? m[1] : "🌐";
  if (m) s = s.slice(m[1].length);
  s = s.replace(/\s*-\s*(\d+)/g, " $1").replace(/\s{2,}/g, " ").trim().replace(/^-+|-+$/g, "").trim();
  return { flag, name: s || "Сервер" };
}
export function isLte(p) { return /lte/i.test(cleanName(p.name).name) || p.network === "xhttp"; }
export function isStub(p) { return /^127\./.test(p.address) || p.address === "localhost"; }
