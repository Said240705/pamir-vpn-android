// Mognu для компьютера: вход, ключи, серверы и подключение. Сеть и ядро — через команды Rust (src-tauri/src/main.rs).
import { parseSubscription, buildConfig, cleanName, isLte, isStub } from "./xray.js";
import { mountMascots, newYear } from "./mascot.js";

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
// сервер на экране: при подключении — тот, через который идём, иначе выбранный или самый быстрый
const current = () => (S.state !== "off" && S.active) || selectedServer() || bestServer();
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
  renderSubCard();
}
$("keys").onclick = async (e) => {
  const b = e.target.closest("[data-key]");
  if (!b || +b.dataset.key === S.keyId) return;
  if (S.state !== "off") await disconnect();
  S.keyId = +b.dataset.key; store.set("key", S.keyId);
  renderKeys(); loadSubscription();
};
$("days").onclick = () => openSite("/?screen=subscriptions");
// карточка подписки справа (в широком окне вместо значка с днями)
function renderSubCard() {
  const k = currentKey(), d = daysLeft(k), card = $("sub-card");
  card.hidden = !k;
  if (!k) return;
  $("sub-name").textContent = k.display_name || "Ключ";
  $("sub-num").textContent = d === null ? "∞" : d;
  $("sub-unit").textContent = d === null ? "" : plural(d, "день", "дня", "дней");
  const end = k.expires_at ? new Date(String(k.expires_at).replace(" ", "T") + (/[zZ+]/.test(k.expires_at) ? "" : "Z")) : null;
  $("sub-date").textContent = end ? "до " + end.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" }) : "бессрочно";
  $("sub-arc").style.strokeDashoffset = 169.6 * (1 - (d === null ? 1 : Math.min(d, 30) / 30));
  card.classList.toggle("warn", d !== null && d <= 7 && d > 3);
  card.classList.toggle("danger", d !== null && d <= 3);
}
$("sub-devices").onclick = () => openDevices();

const BARS = '<span class="bars" aria-hidden="true"><i></i><i></i><i></i></span>';
function pingHtml(k) {
  const ping = S.pings[k];
  const cls = ping == null ? "" : ping < 150 ? "good" : ping < 400 ? "mid" : "bad";
  return `<span class="ping ${cls}">${ping == null ? (k in S.pings ? "нет ответа" : "…") : ping + " мс"}${BARS}</span>`;
}

function row(p) {
  const k = keyOf(p), { flag, name } = cleanName(p.name);
  const sub = S.down[k] ? '<small class="warn">Перебои — лучше выбрать другой</small>' : "";
  const on = S.selected === k && selectedServer() === p;
  return `<button class="srv ${on ? "on" : ""}" data-srv="${esc(k)}"><span class="flag">${flagHtml(flag)}</span><span class="name">${esc(name)}${sub}</span>${pingHtml(k)}</button>`;
}

// «Самый быстрый»: сервер выбирается сам по пингу при каждом подключении
function autoRow() {
  const best = bestServer(), on = !selectedServer();
  const sub = best ? `Сейчас: ${esc(cleanName(best.name).name)}` : "По пингу при подключении";
  return `<button class="srv ${on ? "on" : ""}" data-srv=""><span class="flag"><span class="auto-ico"><svg viewBox="0 0 24 24"><path d="M13 2 4 14h7l-1 8 9-12h-7z"/></svg></span></span>` +
    `<span class="name">Самый быстрый<small>${sub}</small></span>${best ? pingHtml(keyOf(best)) : ""}</button>`;
}

function renderServers() {
  const usable = S.servers.filter((p) => !isStub(p));
  const normal = usable.filter((p) => !isLte(p)), lte = usable.filter(isLte);
  const notice = $("notice");
  if (!S.keys.length) {
    notice.hidden = false;
    notice.innerHTML = '<b>Нет активной подписки</b>Оформи её в личном кабинете — серверы появятся здесь сами.<button class="btn primary" data-open="/?screen=balance">Купить подписку</button>';
  } else if (S.servers.length && !usable.length) {
    // вместо серверов подписка прислала заглушки — почти всегда это занятые места для устройств на ключе
    notice.hidden = false;
    notice.innerHTML = '<b>Этот компьютер пока не подключён к ключу</b>Все места для устройств заняты. Освободи место или добавь ещё одно — серверы появятся сразу.' +
      '<button class="btn primary" id="notice-devices">Устройства на ключе</button>';
  } else notice.hidden = true;
  $("server-list").innerHTML = normal.length ? autoRow() + normal.map(row).join("") : '<div class="empty">Серверов пока нет</div>';
  $("lte-wrap").hidden = !lte.length;
  $("lte-list").innerHTML = lte.map(row).join("");
}

document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-srv]");
  if (!b) return;
  S.selected = b.dataset.srv || null; store.set("server", S.selected);
  renderServers();
  if (S.state === "on") { await disconnect(true); connect(); }
});

// ── устройства ключа (как в кабинете, cabinet-3.js): место для этого компьютера ─────────
const DEV_PHONE = '<svg viewBox="0 0 24 24"><rect x="5" y="2" width="14" height="20" rx="2.5"/><path d="M11 18h2"/></svg>';
const DEV_PC = '<svg viewBox="0 0 24 24"><rect x="2" y="4" width="20" height="13" rx="2"/><path d="M8 21h8M12 17v4"/></svg>';
const isPc = (d) => /windows|mac ?os|macos|linux|desktop|pc/i.test((d.device_os || "") + " " + (d.device_model || "")) && !/iphone|ipad|android/i.test(d.device_os || "");
function seen(ms) {
  const t = Number(ms);
  if (!t) return "";
  const min = Math.max(0, Date.now() - t) / 60000;
  if (min < 10) return "в сети недавно";
  if (min < 60) return "был " + Math.round(min) + " мин назад";
  if (min < 1440) return "был " + Math.round(min / 60) + " ч назад";
  return "был " + new Date(t).toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

async function openDevices() {
  const k = currentKey();
  if (!k) { toast("Нет активного ключа"); return; }
  $("settings").hidden = true;
  $("devices").hidden = false;
  const body = $("devices-body");
  body.innerHTML = '<p class="muted">Загружаем…</p>';
  let data;
  try { data = await api("/topup/devices?key_id=" + k.id); }
  catch (e) { body.innerHTML = `<p class="muted">Не удалось загрузить устройства: ${esc(e.message)}</p>`; return; }
  const list = (data.devices || []).slice().sort((a, b) => (Number(b.last_seen) || 0) - (Number(a.last_seen) || 0));
  const limit = Number(data.limit) || 0, used = list.length, full = limit > 0 && used >= limit;
  const meter = limit > 0 ? `<div class="dev-meter">${Array.from({ length: Math.min(limit, 6) }, (_, i) => `<span class="${i < used ? "on" : ""}"></span>`).join("")}</div>` : "";
  body.innerHTML =
    `<p class="muted small" style="margin:0">Ключ «${esc(k.display_name || "Ключ")}» · подключено ${used}${limit ? " из " + limit : ""}</p>${meter}` +
    (full ? '<p class="small" style="margin:6px 0 0">Чтобы подключить этот компьютер, отключи устройство, которым больше не пользуешься, или добавь место.</p>' : "") +
    `<div class="dev-list">${list.map((d) =>
      `<div class="dev"><span class="dev-ico">${isPc(d) ? DEV_PC : DEV_PHONE}</span><span class="dev-info"><b>${esc(d.device_model || "Устройство")}</b>` +
      `<span>${esc([d.device_os, d.os_version].filter(Boolean).join(" "))}${d.last_seen ? " · " + seen(d.last_seen) : ""}</span></span>` +
      `<button class="dev-off" data-dev="${esc(d.id)}">Отключить</button></div>`).join("") || '<p class="muted small">Пока ни одно устройство не подключено</p>'}</div>` +
    `<div class="dev-acts">${limit > 0 && limit < 3 ? '<button class="btn primary" id="dev-buy">Добавить место — 50 ₽</button>' : ""}` +
    '<button class="btn" data-open="/?screen=subscriptions">Открыть кабинет</button></div>';
}

$("devices-body").onclick = async (e) => {
  const off = e.target.closest("[data-dev]"), buy = e.target.closest("#dev-buy"), k = currentKey();
  if (!k || (!off && !buy)) return;
  const btn = off || buy;
  btn.disabled = true;
  try {
    if (off) await api("/topup/device-remove", { method: "POST", body: { key_id: k.id, device_id: Number(off.dataset.dev) } });
    else await api("/topup/buy-device-slot", { method: "POST", body: { key_id: k.id } });
    toast(off ? "Устройство отключено — место свободно" : "Место добавлено");
    await openDevices();
    loadSubscription(true);
  } catch (err) {
    btn.disabled = false;
    if (buy && /недостаточно/i.test(err.message)) { toast("На балансе не хватает 50 ₽ — пополни в кабинете"); openSite("/?screen=balance"); }
    else toast(err.message);
  }
};
$("devices-open").onclick = openDevices;
$("devices-close").onclick = () => ($("devices").hidden = true);
$("devices").onclick = (e) => { if (e.target.id === "devices") $("devices").hidden = true; };
$("notice").onclick = (e) => { if (e.target.closest("#notice-devices")) openDevices(); };

// ── подключено: время, IP снаружи и пинг ─────────────────────────────────────
let since = 0, clock = 0;
function renderStats() {
  const on = S.state === "on";
  $("stats").hidden = !on;
  clearInterval(clock);
  if (!on) { since = 0; return; }
  if (!since) { since = Date.now(); $("st-ip").textContent = "…"; lookupIp(); }
  const srv = current(), ping = srv && S.pings[keyOf(srv)];
  $("st-ping").textContent = ping ? ping + " мс" : "—";
  const tick = () => {
    const s = Math.floor((Date.now() - since) / 1000), h = Math.floor(s / 3600), two = (n) => String(n).padStart(2, "0");
    $("st-time").textContent = (h ? h + ":" : "") + two(Math.floor(s / 60) % 60) + ":" + two(s % 60);
  };
  tick(); clock = setInterval(tick, 1000);
}
// адрес, который видят сайты: служебная страница Cloudflare через само подключение
async function lookupIp() {
  try {
    const r = await invoke("http", { req: { url: "https://cloudflare.com/cdn-cgi/trace", proxy: S.ports && S.ports.http, timeout_ms: 9000 } });
    const ip = /^ip=(.+)$/m.exec(r.body), loc = /^loc=([A-Z]{2})$/m.exec(r.body);
    // в проверочном запуске на GitHub снимки экрана публичные — адрес сервера не показываем
    if (!ip) throw new Error("no ip");
    const shown = S.demo ? ip[1].replace(/[0-9a-f]/gi, "•") : ip[1];
    if (S.state === "on") { $("st-ip").innerHTML = (loc ? flagSvg(loc[1]) + " " : "") + esc(shown); $("st-ip").title = shown; }
  } catch (e) { if (S.state === "on") $("st-ip").textContent = "—"; }
}

function renderMode() {
  for (const b of $("mode").querySelectorAll("button")) {
    b.classList.toggle("on", b.dataset.mode === S.mode);
    b.setAttribute("aria-checked", b.dataset.mode === S.mode);
    b.disabled = S.state === "busy";
  }
  $("foot").textContent = S.mode === "tun"
    ? "Весь трафик компьютера идёт через Mognu VPN: игры, Discord и любые программы."
    : "Браузеры, Telegram и большинство программ идут через Mognu VPN (системный прокси Windows).";
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
  $("power-mascot").dataset.mood = S.state;
  document.body.classList.toggle("connected", S.state === "on");
  p.setAttribute("aria-label", S.state === "on" ? "Отключить" : "Подключить");
  const srv = current(), label = srv ? flagHtml(cleanName(srv.name).flag) + " " + esc(cleanName(srv.name).name) : "";
  title.classList.toggle("on", S.state === "on");
  if (S.state === "on") { title.textContent = "Подключено"; sub.innerHTML = label; }
  else if (S.state === "busy") { title.textContent = "Подключаем…"; sub.innerHTML = label; }
  else { title.textContent = "Не подключено"; sub.textContent = "Нажми на Могну, чтобы подключиться"; }
  renderStats();
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
  S.active = srv; S.state = "busy"; renderPower();
  try {
    const ports = await invoke("free_ports");
    await invoke("core_start", { config: JSON.stringify(buildConfig(srv, ports, { tun })) });
    if (!(await verify(ports.http))) throw new Error("Сервер не отвечает — попробуй другой");
    // в режиме «весь трафик» системный прокси не нужен: трафик и так идёт через адаптер Mognu
    if (!tun) await invoke("proxy_set", { port: ports.http });
    S.ports = ports; S.state = "on";
  } catch (e) {
    await invoke("core_stop").catch(() => {});
    S.state = "off"; S.ports = null; S.active = null;
    invoke("core_note", { text: "не подключилось: " + String(e.message || e).slice(0, 300) }).catch(() => {});
    toast(String(e.message || e).split("\n")[0].slice(0, 140));
  }
  renderPower(); renderServers();
}

async function disconnect(quiet) {
  await invoke("core_stop").catch(() => {});
  S.state = "off"; S.ports = null; S.active = null;
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
  const text = `Mognu VPN для Windows ${S.version}\n${navigator.userAgent}\n\n${log || "(журнал ядра пуст)"}`;
  try { await navigator.clipboard.writeText(text); toast("Журнал скопирован — вставь его в чат поддержки"); }
  catch (e) { toast("Не удалось скопировать"); }
};

// ── обновления (update.rs): новые версии — пре-релизы desktop-v* на GitHub ───────
let pendingUpdate = null;
const viaCore = () => (S.state === "on" && S.ports ? S.ports.http : null);

async function checkUpdate(manual) {
  try {
    const u = await invoke("update_check", { proxy: viaCore() });
    if (u) {
      pendingUpdate = u;
      $("update-title").textContent = "Mognu VPN " + u.version + " готов";
      $("update").hidden = false;
    } else if (manual) toast("У тебя последняя версия — " + S.version);
  } catch (e) {
    if (manual) toast("Не удалось проверить обновления");
  }
}

$("update-go").onclick = async () => {
  const b = $("update-go");
  if (!pendingUpdate || b.disabled) return;
  b.disabled = true; b.textContent = "Скачиваем…";
  try {
    // после скачивания и проверки программа сама закроется, обновится и откроется снова
    await invoke("update_install", { u: pendingUpdate, proxy: viaCore() });
  } catch (e) {
    b.disabled = false; b.textContent = "Обновить";
    toast("Не удалось обновить: " + String(e).slice(0, 100));
  }
};
$("update-check").onclick = () => { $("settings").hidden = true; checkUpdate(true); };

// ── окно: своя шапка вместо системной (tauri.conf.json: decorations false) ────────
const win = () => window.__TAURI__.window.getCurrentWindow();
$("win-min").onclick = () => win().minimize();
$("win-max").onclick = () => win().toggleMaximize();
// значок кнопки: один квадрат — развернуть, два — вернуть прежний размер
const MAXI = '<rect x="1.5" y="1.5" width="7" height="7" rx="1"/>';
const RESTORE = '<rect x="1.5" y="3" width="5.5" height="5.5" rx="1"/><path d="M3.5 3V2.2c0-.4.3-.7.7-.7h4.1c.4 0 .7.3.7.7v4.1c0 .4-.3.7-.7.7H7"/>';
async function syncMax() {
  const m = await win().isMaximized().catch(() => false);
  $("win-max").querySelector("svg").innerHTML = m ? RESTORE : MAXI;
  $("win-max").setAttribute("aria-label", m ? "Свернуть в окно" : "Развернуть");
}
addEventListener("resize", syncMax);
syncMax();
// крестик — как у системной шапки: main.rs прячет окно в трей, подключение остаётся
$("win-close").onclick = () => win().close();

// ── небо: звёзды (и снег в новогодний сезон) на холсте под интерфейсом ───────
function sky(snow) {
  const cv = $("stars"), cx = cv.getContext("2d");
  if (!cx) return;
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let w = 0, h = 0, stars = [], flakes = [];
  const size = () => {
    const r = devicePixelRatio || 1;
    w = cv.clientWidth; h = cv.clientHeight;
    cv.width = w * r; cv.height = h * r; cx.setTransform(r, 0, 0, r, 0, 0);
    stars = Array.from({ length: Math.round((w * h) / 9000) }, () => ({ x: Math.random() * w, y: Math.random() * h * 0.8, r: Math.random() * 1.1 + 0.3, a: Math.random() * 0.6 + 0.2, s: Math.random() * 2 + 1 }));
    flakes = snow ? Array.from({ length: Math.round(w / 22) }, () => ({ x: Math.random() * w, y: Math.random() * h, r: Math.random() * 1.8 + 0.8, v: Math.random() * 0.4 + 0.25, d: Math.random() * 6 })) : [];
  };
  const draw = (t) => {
    cx.clearRect(0, 0, w, h);
    for (const s of stars) {
      cx.globalAlpha = still ? s.a : s.a * (0.65 + 0.35 * Math.sin(t / 1000 / s.s + s.x));
      cx.fillStyle = "#fff"; cx.beginPath(); cx.arc(s.x, s.y, s.r, 0, 6.283); cx.fill();
    }
    cx.globalAlpha = 0.7;
    for (const f of flakes) {
      f.y += f.v; f.x += Math.sin(t / 1600 + f.d) * 0.25;
      if (f.y > h + 4) { f.y = -4; f.x = Math.random() * w; }
      cx.beginPath(); cx.arc(f.x, f.y, f.r, 0, 6.283); cx.fill();
    }
    cx.globalAlpha = 1;
  };
  size(); draw(0);
  addEventListener("resize", () => { size(); draw(performance.now()); });
  if (still) return;
  // ~30 кадров в секунду и только пока окно видно: в трее небо не тратит процессор
  let last = 0;
  const loop = (t) => { if (!document.hidden && t - last > 33) { last = t; draw(t); } requestAnimationFrame(loop); };
  requestAnimationFrame(loop);
}

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
  const ny = newYear();
  mountMascots(ny);
  sky(ny);
  try { S.version = await window.__TAURI__.app.getVersion(); } catch (e) { S.version = "0.1.0"; }
  $("version").textContent = "Mognu VPN для Windows " + S.version;
  refreshHosts();
  setTimeout(checkUpdate, 8000);
  setInterval(checkUpdate, 6 * 3600e3);
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
