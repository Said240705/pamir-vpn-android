// Mognu для компьютера: вход, ключи, серверы и подключение. Сеть и ядро — через команды Rust (src-tauri/src/main.rs).
import { parseSubscription, buildConfig, cleanName, isLte, isStub } from "./xray.js";

const invoke = (cmd, args) => window.__TAURI__.core.invoke(cmd, args);
const $ = (id) => document.getElementById(id);
const SITE = "https://mognu.app";

// ── хранилище (localStorage окна; живёт в папке программы) ───────────────────
const store = {
  get(k, d = null) { try { const v = localStorage.getItem("mognu_" + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("mognu_" + k, JSON.stringify(v)); } catch (e) {} },
  del(k) { try { localStorage.removeItem("mognu_" + k); } catch (e) {} },
};

// Номер установки — как x-hwid у Android: подписка считает компьютер отдельным устройством
function hwid() {
  let id = store.get("hwid");
  if (!id) {
    id = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
    store.set("hwid", id);
  }
  return id;
}

// ── состояние ────────────────────────────────────────────────────────────────
const S = {
  version: "",
  keys: [],
  keyId: store.get("key"),
  servers: [],
  pings: {},
  down: {},
  selected: store.get("server"),
  state: "off", // off | busy | on
  ports: null,
  // proxy — системный прокси (браузеры и большинство программ); tun — весь трафик через адаптер Mognu (нужны права)
  mode: store.get("mode") === "tun" ? "tun" : "proxy",
  launch: { elevated: false, handoff: false },
};

// ── API кабинета: зеркала по очереди, как PamirHosts в Android ───────────────
const HOSTS = ["https://mognu.app", "https://mognu.net", "https://app.pamirlink.ru"];
function hosts() {
  const good = store.get("host_good");
  const all = [...new Set([...HOSTS, ...(store.get("hosts_extra") || [])])];
  return good && all.includes(good) ? [good, ...all.filter((h) => h !== good)] : all;
}

async function http(url, { method = "GET", headers = {}, body, timeout = 15000 } = {}) {
  return invoke("http", { req: { url, method, headers, body, proxy: S.state === "on" && S.ports ? S.ports.http : null, timeout_ms: timeout } });
}

class ApiError extends Error { constructor(status, msg) { super(msg); this.status = status; } }

async function api(path, { method = "GET", body, auth = true } = {}) {
  const headers = { Accept: "application/json", "User-Agent": "Mognu-Desktop/" + S.version };
  const token = store.get("token");
  if (auth && token) headers.Authorization = "Bearer " + token;
  if (body) headers["Content-Type"] = "application/json; charset=utf-8";
  let last;
  for (const h of hosts()) {
    let r;
    try { r = await http(h + "/api" + path, { method, headers, body: body ? JSON.stringify(body) : undefined }); }
    catch (e) { last = e; continue; }
    // не наш API (страница оператора или CDN) — следующее зеркало
    if (r.body.trimStart().startsWith("<")) { last = new Error("not api " + r.status); continue; }
    store.set("host_good", h);
    let data = {};
    try { data = r.body ? JSON.parse(r.body) : {}; } catch (e) { data = { result: r.body }; }
    if (r.status < 200 || r.status > 299) {
      const d = data && data.detail;
      throw new ApiError(r.status, typeof d === "string" ? d : Array.isArray(d) ? "Проверь введённые данные" : "Ошибка сервера (" + r.status + ")");
    }
    return data;
  }
  throw new ApiError(0, "Нет связи с сервером. Проверь интернет");
}

// Новые зеркала с сервера (hosts.json), раз при запуске
async function refreshHosts() {
  for (const h of hosts()) {
    try {
      const r = await http(h + "/hosts.json", { timeout: 8000 });
      const list = (JSON.parse(r.body).hosts || []).filter((x) => /^https:\/\/[a-z0-9.-]+\.[a-z]{2,}$/.test(x) && !HOSTS.includes(x)).slice(0, 8);
      store.set("hosts_extra", list);
      return;
    } catch (e) { /* следующее зеркало */ }
  }
}

// ── мелочи интерфейса ────────────────────────────────────────────────────────
let toastTimer = 0;
function toast(msg) {
  const t = $("toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), 3200);
}
function show(id) { for (const s of ["login", "home"]) $(s).hidden = s !== id; }
function plural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100;
  return m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? few : many;
}
// Windows не рисует эмодзи флагов (вместо 🇪🇸 — буквы «ES»), поэтому флаги наших стран — свои маленькие SVG
const FLAGS = {
  RU: ["h", "#fff", "#1C57D5", "#E4202C"], DE: ["h", "#111", "#DD1C1C", "#FFCE00"], NL: ["h", "#AE1C28", "#fff", "#21468B"],
  ES: ["es"], FR: ["v", "#1F3E8F", "#fff", "#E1262D"], IT: ["v", "#159A48", "#fff", "#D8262C"], PL: ["h2", "#fff", "#DC143C"],
  FI: ["x", "#fff", "#1A4FA0"], SE: ["x", "#1F5DA8", "#FECB00"], NO: ["x", "#BA0C2F", "#00205B"], DK: ["x", "#C8102E", "#fff"],
  EE: ["h", "#0072CE", "#111", "#fff"], LV: ["lv"], LT: ["h", "#FDB913", "#006A44", "#C1272D"], KZ: ["k"], TR: ["k2"], US: ["us"], GB: ["gb"],
};
function flagSvg(code) {
  const f = FLAGS[code];
  if (!f) return `<span class="flag-code">${code || "🌐"}</span>`;
  const r = (x, y, w, h, c) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${c}"/>`;
  let body = "";
  if (f[0] === "h") body = r(0, 0, 24, 6, f[1]) + r(0, 6, 24, 6, f[2]) + r(0, 12, 24, 6, f[3]);
  else if (f[0] === "h2") body = r(0, 0, 24, 9, f[1]) + r(0, 9, 24, 9, f[2]);
  else if (f[0] === "v") body = r(0, 0, 8, 18, f[1]) + r(8, 0, 8, 18, f[2]) + r(16, 0, 8, 18, f[3]);
  else if (f[0] === "x") body = r(0, 0, 24, 18, f[1]) + r(7, 0, 3, 18, f[2]) + r(0, 7.5, 24, 3, f[2]);
  else if (f[0] === "es") body = r(0, 0, 24, 18, "#C60B1E") + r(0, 4.5, 24, 9, "#FFC400");
  else if (f[0] === "lv") body = r(0, 0, 24, 18, "#9E3039") + r(0, 7.2, 24, 3.6, "#fff");
  else if (f[0] === "k") body = r(0, 0, 24, 18, "#00AFCA") + '<circle cx="12" cy="8.5" r="3.4" fill="#FEC50C"/>';
  else if (f[0] === "k2") body = r(0, 0, 24, 18, "#E30A17") + '<circle cx="10" cy="9" r="4.4" fill="#fff"/><circle cx="11.2" cy="9" r="3.5" fill="#E30A17"/>';
  else if (f[0] === "us") body = r(0, 0, 24, 18, "#fff") + [0, 2.8, 5.5, 8.3, 11, 13.8, 16.5].map((y) => r(0, y, 24, 1.4, "#B22234")).join("") + r(0, 0, 10, 9.6, "#3C3B6E");
  else if (f[0] === "gb") body = r(0, 0, 24, 18, "#012169") + '<path d="M0 0L24 18M24 0L0 18" stroke="#fff" stroke-width="3.6"/><path d="M0 0L24 18M24 0L0 18" stroke="#C8102E" stroke-width="1.2"/>' + r(10, 0, 4, 18, "#fff") + r(0, 7, 24, 4, "#fff") + r(10.8, 0, 2.4, 18, "#C8102E") + r(0, 7.8, 24, 2.4, "#C8102E");
  return `<svg class="flag-svg" viewBox="0 0 24 18" aria-label="${code}"><clipPath id="fc${code}"><rect width="24" height="18" rx="3.5"/></clipPath><g clip-path="url(#fc${code})">${body}</g></svg>`;
}
// 🇪🇸 → "ES"
function flagCode(emoji) {
  const cps = Array.from(emoji || "").map((c) => c.codePointAt(0)).filter((c) => c >= 0x1F1E6 && c <= 0x1F1FF);
  return cps.length === 2 ? String.fromCharCode(cps[0] - 0x1F1E6 + 65, cps[1] - 0x1F1E6 + 65) : "";
}
const flagHtml = (emoji) => flagSvg(flagCode(emoji));

function esc(s) { return String(s).replace(/[&<>"']/g, (c) => "&#" + c.charCodeAt(0) + ";"); }
function openSite(path) { invoke("open_url", { url: SITE + path }).catch(() => toast("Не удалось открыть браузер")); }

document.addEventListener("click", (e) => {
  const a = e.target.closest("[data-open]");
  if (a) { e.preventDefault(); openSite(a.dataset.open); }
});

// ── вход ─────────────────────────────────────────────────────────────────────
function loginStatus(msg, error) { const s = $("login-status"); s.textContent = msg || ""; s.classList.toggle("error", !!error); }

let tgTimer = 0;
$("tg-login").onclick = async () => {
  loginStatus("Открываем Telegram…");
  try {
    const { token, deep_link } = await api("/auth/telegram/start", { method: "POST", auth: false });
    await invoke("open_url", { url: deep_link });
    loginStatus("Подтверди вход в Telegram — мы подождём здесь");
    let tries = 0;
    clearInterval(tgTimer);
    tgTimer = setInterval(async () => {
      if (++tries > 150) { clearInterval(tgTimer); loginStatus("Время ожидания вышло. Попробуй ещё раз", true); return; }
      try {
        const r = await api("/auth/telegram/poll?token=" + encodeURIComponent(token), { auth: false });
        if (r.status === "approved") { clearInterval(tgTimer); signedIn(r.access_token); }
      } catch (e) { /* ждём дальше */ }
    }, 2000);
  } catch (e) { loginStatus(e.message, true); }
};
$("email-open").onclick = () => { $("login-start").hidden = true; $("email-form").hidden = false; $("email").focus(); loginStatus(""); };
$("email-back").onclick = (e) => { e.preventDefault(); $("email-form").hidden = true; $("login-start").hidden = false; loginStatus(""); };
$("email-form").onsubmit = async (e) => {
  e.preventDefault();
  loginStatus("Входим…");
  try {
    const { access_token } = await api("/auth/email/login", { method: "POST", auth: false, body: { email: $("email").value.trim(), password: $("password").value } });
    signedIn(access_token);
  } catch (err) {
    loginStatus(err.status === 403 && err.message === "email_not_verified" ? "Почта не подтверждена — подтверди её на сайте" : err.message, true);
  }
};

function signedIn(token) {
  store.set("token", token);
  loginStatus("");
  startHome();
}

// ── ключи и подписка ─────────────────────────────────────────────────────────
function daysLeft(k) {
  if (!k || !k.expires_at) return null;
  const t = new Date(String(k.expires_at).replace(" ", "T") + (/[zZ+]/.test(k.expires_at) ? "" : "Z")).getTime();
  return Math.max(0, Math.ceil((t - Date.now()) / 864e5));
}
function currentKey() { return S.keys.find((k) => k.id === S.keyId) || S.keys[0] || null; }

async function loadKeys() {
  // проверочный запуск на GitHub (MOGNU_DEMO_SUB): без аккаунта, сразу с тестовой подпиской
  if (S.demo) {
    S.keys = [{ id: 1, display_name: "Тестовый ключ", is_active: true, expires_at: new Date(Date.now() + 30 * 864e5).toISOString(), subscription_url: S.demo.sub }];
    S.keyId = 1;
    renderKeys();
    return;
  }
  const r = await api("/auth/keys");
  const list = Array.isArray(r) ? r : r.keys || [];
  S.keys = list.filter((k) => k.is_active && String(k.subscription_url || "").startsWith("http"));
  if (!S.keys.find((k) => k.id === S.keyId)) S.keyId = S.keys[0] ? S.keys[0].id : null;
  store.set("key", S.keyId);
  renderKeys();
}

async function loadSubscription(force) {
  const k = currentKey();
  if (!k) { S.servers = []; renderServers(); return; }
  const cache = store.get("sub_" + k.id);
  if (cache && !force && Date.now() - cache.at < 6 * 3600e3) S.servers = parseSubscription(cache.body);
  else {
    try {
      const r = await http(k.subscription_url, { headers: {
        "User-Agent": "v2rayN/Mognu-Desktop " + S.version, "x-hwid": hwid(), "x-device-os": "Windows",
        "x-ver-os": (/Windows NT ([\d.]+)/.exec(navigator.userAgent) || [])[1] || "", "x-device-model": "PC",
      } });
      if (r.status !== 200) throw new Error("подписка: " + r.status);
      S.servers = parseSubscription(r.body);
      store.set("sub_" + k.id, { at: Date.now(), body: r.body });
    } catch (e) {
      if (cache) S.servers = parseSubscription(cache.body);
      toast("Не удалось обновить серверы — показываю сохранённые");
    }
  }
  renderServers();
  await pingAll();
  loadStatus();
}

// статус локаций со страницы статуса: «перебои» помечаем, как в Android
const norm = (s) => String(s).toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
async function loadStatus() {
  try {
    const r = await api("/topup/public/server-status", { auth: false });
    S.down = {};
    for (const p of S.servers) {
      const n = norm(p.name);
      let best = null;
      for (const s of r.servers || []) { const k = norm(s.name); if (k && n.includes(k) && (!best || k.length > norm(best.name).length)) best = s; }
      if (best && best.status === "down") S.down[keyOf(p)] = true;
    }
    renderServers();
  } catch (e) { /* без статуса — просто без пометок */ }
}

async function pingAll() {
  await Promise.all(S.servers.filter((p) => !isStub(p)).map(async (p) => {
    S.pings[keyOf(p)] = await invoke("tcp_ping", { host: p.address, port: p.port }).catch(() => null);
  }));
  renderServers();
}

// ── отрисовка ────────────────────────────────────────────────────────────────
const keyOf = (p) => p.address + ":" + p.port + ":" + p.name;
function selectedServer() {
  const usable = S.servers.filter((p) => !isStub(p));
  return usable.find((p) => keyOf(p) === S.selected) || null;
}
// лучший обычный сервер по пингу (LTE — только если выбрать вручную)
function bestServer() {
  const normal = S.servers.filter((p) => !isStub(p) && !isLte(p) && !S.down[keyOf(p)]);
  const pinged = normal.filter((p) => S.pings[keyOf(p)]).sort((a, b) => S.pings[keyOf(a)] - S.pings[keyOf(b)]);
  return pinged[0] || normal[0] || S.servers.find((p) => !isStub(p)) || null;
}

function renderKeys() {
  const el = $("keys");
  el.hidden = S.keys.length < 2;
  el.innerHTML = S.keys.map((k) => `<button data-key="${k.id}" class="${k.id === S.keyId ? "on" : ""}">${esc(k.display_name || "Ключ")}</button>`).join("");
  const d = daysLeft(currentKey()), pill = $("days");
  pill.hidden = d === null;
  if (d !== null) {
    pill.textContent = d + " " + plural(d, "день", "дня", "дней");
    pill.className = "pill" + (d <= 3 ? " danger" : d <= 7 ? " warn" : "");
    pill.title = "Продлить в личном кабинете";
  }
}
$("keys").onclick = async (e) => {
  const b = e.target.closest("[data-key]");
  if (!b || +b.dataset.key === S.keyId) return;
  if (S.state !== "off") await disconnect();
  S.keyId = +b.dataset.key; store.set("key", S.keyId);
  renderKeys(); loadSubscription();
};
$("days").onclick = () => openSite("/?screen=subscriptions");

function row(p) {
  const k = keyOf(p), { flag, name } = cleanName(p.name), ping = S.pings[k];
  const cls = ping == null ? "" : ping < 150 ? "good" : ping < 400 ? "mid" : "bad";
  const sub = S.down[k] ? "<small>Перебои — лучше выбрать другой</small>" : "";
  const on = (selectedServer() || bestServer()) === p;
  return `<button class="srv ${on ? "on" : ""}" data-srv="${esc(k)}"><span class="flag">${flagHtml(flag)}</span><span class="name">${esc(name)}${sub}</span>` +
    `<span class="ping ${cls}">${ping == null ? (k in S.pings ? "—" : "…") : ping + " мс"}</span></button>`;
}

function renderServers() {
  const usable = S.servers.filter((p) => !isStub(p));
  const normal = usable.filter((p) => !isLte(p)), lte = usable.filter(isLte);
  const notice = $("notice");
  if (!S.keys.length) {
    notice.hidden = false;
    notice.innerHTML = 'Нет активной подписки. <button class="btn primary" data-open="/?screen=balance">Купить подписку</button>';
  } else if (S.servers.length && !usable.length) {
    notice.hidden = false;
    notice.innerHTML = 'Подписка не активна или достигнут лимит устройств. <button class="btn primary" data-open="/?screen=subscriptions">Открыть кабинет</button>';
  } else notice.hidden = true;
  $("server-list").innerHTML = normal.length ? normal.map(row).join("") : '<div class="empty">Серверов пока нет</div>';
  $("lte-wrap").hidden = !lte.length;
  $("lte-list").innerHTML = lte.map(row).join("");
}

document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-srv]");
  if (!b) return;
  S.selected = b.dataset.srv; store.set("server", S.selected);
  renderServers();
  if (S.state === "on") { await disconnect(true); connect(); }
});

function renderMode() {
  for (const b of $("mode").querySelectorAll("button")) {
    b.classList.toggle("on", b.dataset.mode === S.mode);
    b.setAttribute("aria-checked", b.dataset.mode === S.mode);
    b.disabled = S.state === "busy";
  }
  $("foot").textContent = S.mode === "tun"
    ? "Весь трафик компьютера идёт через Mognu: игры, Discord и любые программы."
    : "Браузеры, Telegram и большинство программ идут через Mognu (системный прокси Windows).";
}

// Перезапуск с правами администратора: Windows спросит разрешение; новая копия подключится сама
async function elevate() {
  const ok = await invoke("relaunch_elevated").catch((e) => { toast(String(e)); return false; });
  if (!ok) { S.mode = "proxy"; store.set("mode", "proxy"); renderMode(); toast("Без разрешения Windows режим «Весь трафик» не включить"); }
}

$("mode").onclick = async (e) => {
  const b = e.target.closest("[data-mode]");
  if (!b || b.disabled || b.dataset.mode === S.mode) return;
  if (b.dataset.mode === "tun" && !S.launch.elevated) { $("tun-ask").hidden = false; return; }
  S.mode = b.dataset.mode; store.set("mode", S.mode); renderMode();
  if (S.state === "on") { await disconnect(true); connect(); }
};
$("tun-no").onclick = () => ($("tun-ask").hidden = true);
$("tun-yes").onclick = async () => {
  $("tun-ask").hidden = true;
  S.mode = "tun"; store.set("mode", "tun"); renderMode();
  if (S.state !== "off") await disconnect(true);
  elevate();
};

function renderPower() {
  const p = $("power"), title = $("state-title"), sub = $("state-sub");
  p.dataset.state = S.state;
  renderMode();
  $("power-mascot").src = "assets/mascot-" + (S.state === "on" ? "on" : S.state === "busy" ? "busy" : "off") + ".svg";
  p.setAttribute("aria-label", S.state === "on" ? "Отключить" : "Подключить");
  const srv = selectedServer() || bestServer(), label = srv ? flagHtml(cleanName(srv.name).flag) + " " + esc(cleanName(srv.name).name) : "";
  title.classList.toggle("on", S.state === "on");
  if (S.state === "on") { title.textContent = "Подключено"; sub.innerHTML = label; }
  else if (S.state === "busy") { title.textContent = "Подключаем…"; sub.innerHTML = label; }
  else { title.textContent = "Не подключено"; sub.textContent = "Нажми на Могну, чтобы подключиться"; }
  // значок в трее повторяет состояние: салатовый и сервер в подсказке — подключено
  const plain = srv ? cleanName(srv.name).name : "";
  invoke("tray_state", { connected: S.state === "on", label: plain }).catch(() => {});
}

// ── подключение ──────────────────────────────────────────────────────────────
async function verify(port) {
  for (const url of ["https://www.gstatic.com/generate_204", "https://cp.cloudflare.com/generate_204"]) {
    try {
      const r = await invoke("http", { req: { url, proxy: port, timeout_ms: 9000 } });
      if (r.status === 204 || r.status === 200) return true;
    } catch (e) { /* следующий адрес */ }
  }
  return false;
}

async function connect() {
  const srv = selectedServer() || bestServer();
  if (!srv) { toast(S.keys.length ? "Нет доступных серверов" : "Нет активной подписки"); return; }
  // режим «весь трафик» без прав администратора — сначала перезапуск через окно Windows, подключится новая копия
  if (S.mode === "tun" && !S.launch.elevated) { elevate(); return; }
  const tun = S.mode === "tun";
  S.state = "busy"; renderPower();
  try {
    const ports = await invoke("free_ports");
    await invoke("core_start", { config: JSON.stringify(buildConfig(srv, ports, { tun })) });
    if (!(await verify(ports.http))) throw new Error("Сервер не отвечает — попробуй другой");
    // в режиме «весь трафик» системный прокси не нужен: трафик и так идёт через адаптер Mognu
    if (!tun) await invoke("proxy_set", { port: ports.http });
    S.ports = ports; S.state = "on";
    store.set("server", keyOf(srv)); S.selected = keyOf(srv);
  } catch (e) {
    await invoke("core_stop").catch(() => {});
    S.state = "off"; S.ports = null;
    toast(String(e.message || e).split("\n")[0].slice(0, 140));
  }
  renderPower(); renderServers();
}

async function disconnect(quiet) {
  await invoke("core_stop").catch(() => {});
  S.state = "off"; S.ports = null;
  if (!quiet) renderPower();
}

$("power").onclick = () => { if (S.state === "busy") return; if (S.state === "on") disconnect(); else connect(); };
// «Подключить / Отключить» из меню значка в трее; до входа в аккаунт пункт ничего не делает
window.__TAURI__.event.listen("tray-toggle", () => { if (!$("home").hidden) $("power").click(); });
$("refresh").onclick = () => loadSubscription(true);

// ── настройки ────────────────────────────────────────────────────────────────
$("settings-open").onclick = async () => {
  $("settings").hidden = false;
  try { const me = await api("/auth/me"); $("account").textContent = me.email || (me.username ? "@" + me.username : "") || ""; } catch (e) {}
};
$("settings-close").onclick = () => ($("settings").hidden = true);
$("settings").onclick = (e) => { if (e.target.id === "settings") $("settings").hidden = true; };
$("logout").onclick = async () => {
  await disconnect();
  for (const k of ["token", "key", "server"]) store.del(k);
  S.keys = []; S.servers = [];
  $("settings").hidden = true;
  show("login");
};
$("copy-log").onclick = async () => {
  const log = await invoke("core_log").catch(() => "");
  const text = `Mognu Desktop ${S.version}\n${navigator.userAgent}\n\n${log || "(журнал ядра пуст)"}`;
  try { await navigator.clipboard.writeText(text); toast("Журнал скопирован — вставь его в чат поддержки"); }
  catch (e) { toast("Не удалось скопировать"); }
};

// ── запуск ───────────────────────────────────────────────────────────────────
async function startHome() {
  show("home"); renderPower();
  try { await loadKeys(); }
  catch (e) {
    if (e.status === 401) { store.del("token"); show("login"); return; }
    toast(e.message);
  }
  await loadSubscription();
}

(async function boot() {
  try { S.version = await window.__TAURI__.app.getVersion(); } catch (e) { S.version = "0.1.0"; }
  $("version").textContent = "Mognu для Windows " + S.version;
  refreshHosts();
  S.launch = await invoke("launch_info").catch(() => S.launch);
  S.demo = await invoke("demo").catch(() => null);
  if (S.demo) {
    if (S.demo.tun) S.mode = "tun";
    await startHome();
    if (S.demo.connect) connect();
    return;
  }
  if (!store.get("token")) { show("login"); return; }
  await startHome();
  // перезапуск с правами ради «весь трафик» — подключаемся сразу, человек уже нажал «Подключить»
  if (S.launch.handoff) connect();
})();
