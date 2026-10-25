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
  allKeys: [],
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
// Уведомления Windows (tauri-plugin-notification): о том, что важно, когда окно спрятано в трее
async function notify(title, body) {
  const n = window.__TAURI__.notification;
  if (!n || S.demo) return;
  try {
    if (!(await n.isPermissionGranted()) && (await n.requestPermission()) !== "granted") return;
    n.sendNotification({ title, body });
  } catch (e) { /* без уведомления */ }
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
// Сайт открываем на адресе, который отвечает сейчас: при «белых списках» mognu.app молчит, и кабинет
// открывается на зеркале из hosts.json (ceboukahusibod.begetcdn.cloud). Спрашиваем все адреса сразу.
async function siteHost() {
  const all = [SITE, ...hosts().filter((h) => h !== SITE)];
  const ok = await Promise.all(all.map((h) => http(h + "/hosts.json", { timeout: 2500 })
    .then((r) => r.status === 200 && r.body.trimStart().startsWith("{"), () => false)));
  return all[ok.indexOf(true)] || SITE;
}
function openSite(path) {
  siteHost().then((h) => invoke("open_url", { url: h + path })).catch(() => toast("Не удалось открыть браузер"));
}

document.addEventListener("click", (e) => {
  const a = e.target.closest("[data-open]");
  if (a) { e.preventDefault(); openSite(a.dataset.open); }
});

// ── вход ─────────────────────────────────────────────────────────────────────
function loginStatus(msg, error) { const s = $("login-status"); s.textContent = msg || ""; s.classList.toggle("error", !!error); }

// Вход через Telegram: на этом компьютере (открываем ссылку) или с телефона (та же ссылка QR-кодом —
// камера телефона откроет Telegram). Сервер выдаёт токен, мы ждём подтверждения до 5 минут.
let tgTimer = 0;
function showLoginStart() {
  clearInterval(tgTimer);
  for (const [id, on] of [["login-start", true], ["qr-box", false], ["email-form", false]]) $(id).hidden = !on;
  loginStatus("");
}
async function telegramLogin(viaQr) {
  clearInterval(tgTimer);
  loginStatus(viaQr ? "Готовим код…" : "Открываем Telegram…");
  try {
    const { token, deep_link } = await api("/auth/telegram/start", { method: "POST", auth: false });
    if (viaQr) {
      const q = window.qrcode(0, "M");
      q.addData(deep_link); q.make();
      $("qr").innerHTML = q.createSvgTag({ cellSize: 6, margin: 3, scalable: true });
      $("qr").classList.remove("stale");
      $("qr-refresh").hidden = true;
      $("login-start").hidden = true; $("qr-box").hidden = false;
      loginStatus("Ждём подтверждения на телефоне…");
    } else {
      await invoke("open_url", { url: deep_link });
      loginStatus("Подтверди вход в Telegram — мы подождём здесь");
    }
    let tries = 0;
    tgTimer = setInterval(async () => {
      if (++tries > 150) {
        clearInterval(tgTimer);
        if (viaQr) { $("qr").classList.add("stale"); $("qr-refresh").hidden = false; loginStatus("Код устарел — обнови его", true); }
        else loginStatus("Время ожидания вышло. Попробуй ещё раз", true);
        return;
      }
      try {
        const r = await api("/auth/telegram/poll?token=" + encodeURIComponent(token), { auth: false });
        if (r.status === "approved") { clearInterval(tgTimer); signedIn(r.access_token); }
      } catch (e) { /* ждём дальше */ }
    }, 2000);
  } catch (e) { loginStatus(e.message, true); }
}
$("tg-login").onclick = () => telegramLogin(false);
$("qr-login").onclick = () => telegramLogin(true);
$("qr-refresh").onclick = (e) => { e.preventDefault(); telegramLogin(true); };
$("qr-back").onclick = (e) => { e.preventDefault(); showLoginStart(); };
$("email-open").onclick = () => { clearInterval(tgTimer); $("login-start").hidden = true; $("email-form").hidden = false; $("email").focus(); loginStatus(""); };
$("email-back").onclick = (e) => { e.preventDefault(); showLoginStart(); };
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
  showLoginStart();
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
  S.allKeys = list; // для продления: и истёкшие тоже
  S.keys = list.filter((k) => k.is_active && String(k.subscription_url || "").startsWith("http"));
  // подписка заканчивается — напомнить раз в день (за 3 дня и меньше)
  for (const k of S.keys) {
    const d = daysLeft(k), today = new Date().toDateString();
    if (d !== null && d <= 3 && store.get("exp_note_" + k.id) !== today) {
      store.set("exp_note_" + k.id, today);
      notify(d <= 0 ? "Подписка заканчивается сегодня" : `Подписка заканчивается через ${d} ${plural(d, "день", "дня", "дней")}`,
        `«${k.display_name || "Ключ"}» — продли в Mognu VPN, чтобы не остаться без интернета`);
    }
  }
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
$("days").onclick = () => openRenew();
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
$("sub-renew").onclick = () => openRenew();

const BARS = '<span class="bars" aria-hidden="true"><i></i><i></i><i></i></span>';
function pingHtml(k) {
  const ping = S.pings[k];
  const cls = ping == null ? "" : ping < 150 ? "good" : ping < 400 ? "mid" : "bad";
  if (ping == null && !(k in S.pings)) return '<span class="ping wait" aria-label="Измеряем"><i></i><i></i><i></i></span>';
  return `<span class="ping ${cls}">${ping == null ? "нет ответа" : ping + " мс"}${BARS}</span>`;
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
    notice.innerHTML = '<b>Нет активной подписки</b>Оформи её в личном кабинете — серверы появятся здесь сами.<button class="btn primary" id="notice-buy">Купить подписку</button>';
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
$("notice").onclick = (e) => {
  if (e.target.closest("#notice-devices")) openDevices();
  if (e.target.closest("#notice-buy")) openRenew(true);
};

// ── продление и покупка (как в Android: тарифы, СБП/карта на странице ЮKassa или с баланса) ─────────────
// /topup/renew {key_id, tariff_id, method} или /topup/purchase {tariff_id, method}: в ответ либо страница оплаты
// (открываем в браузере и ждём /topup/payment-status), либо сразу «оплачено» (с баланса).
const R = { buy: false, keyId: null, tariffs: [], balance: null, busy: null, state: null, order: null, url: null, timer: 0, error: "", keysBefore: [] };
const rub = (minor) => {
  const v = Number(minor) / 100;
  return (Number.isInteger(v) ? v.toLocaleString("ru-RU") : v.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })) + " ₽";
};
const keyDate = (k) => {
  if (!k || !k.expires_at) return "бессрочно";
  const d = daysLeft(k), end = new Date(String(k.expires_at).replace(" ", "T") + (/[zZ+]/.test(k.expires_at) ? "" : "Z"));
  return (d > 0 ? "до " : "истёк ") + end.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
};

async function openRenew(buy = false) {
  if (S.demo) { openSite("/?screen=subscriptions"); return; }
  clearInterval(R.timer);
  Object.assign(R, { buy, state: null, busy: null, error: "", order: null, url: null });
  $("settings").hidden = true;
  $("renew").hidden = false;
  $("renew-title").textContent = buy ? "Купить подписку" : "Продление";
  $("renew-body").innerHTML = '<p class="muted">Загружаем тарифы…</p>';
  try {
    const [keys, tar, me] = await Promise.all([api("/auth/keys"), api("/topup/tariffs"), api("/auth/me").catch(() => ({}))]);
    S.allKeys = Array.isArray(keys) ? keys : keys.keys || [];
    R.tariffs = tar.tariffs || [];
    R.balance = me && me.balance != null ? Number(me.balance) : null;
    const cur = currentKey();
    R.keyId = buy ? null : (S.allKeys.find((k) => cur && k.id === cur.id) || S.allKeys.find((k) => k.is_active) || S.allKeys[0] || {}).id ?? null;
    if (R.keyId === null) R.buy = true;
    renderRenew();
  } catch (e) {
    $("renew-body").innerHTML = `<p class="muted">Не удалось загрузить тарифы: ${esc(e.message)}</p><button class="btn" data-open="/?screen=subscriptions">Продлить в кабинете</button>`;
  }
}

function renderRenew() {
  const b = $("renew-body");
  if (R.state === "waiting") {
    b.innerHTML = '<div class="pay-wait"><span class="spin" aria-hidden="true"></span><b>Ждём оплату</b>' +
      '<p class="muted small">Оплати на открывшейся странице — по СБП или картой. Как только оплата пройдёт, подписка ' + (R.buy ? "появится" : "продлится") + ' сама.</p>' +
      '<div class="dev-acts"><button class="btn" id="pay-reopen">Открыть страницу оплаты</button><button class="btn" id="pay-cancel">Отмена</button></div></div>';
    return;
  }
  if (R.state === "paid") {
    b.innerHTML = '<div class="pay-wait done"><span class="ok" aria-hidden="true">✓</span><b>Оплата прошла</b>' +
      `<p class="muted small">${R.buy ? "Ключ готов — серверы уже загружаются." : "Подписка продлена, VPN работает без перерыва."}</p>` +
      '<button class="btn primary" id="pay-done">Готово</button></div>';
    return;
  }
  if (R.state === "failed") {
    b.innerHTML = '<div class="pay-wait"><b>Оплата не прошла</b><p class="muted small">Деньги не списались. Можно попробовать ещё раз или выбрать другой способ.</p>' +
      '<button class="btn primary" id="pay-again">Выбрать тариф</button></div>';
    return;
  }
  const key = S.allKeys.find((k) => k.id === R.keyId);
  const group = key ? Number(key.tariff_group_id) || 0 : 0;
  let list = R.tariffs.filter((t) => !group || !Number(t.group_id) || Number(t.group_id) === group);
  if (!list.length) list = R.tariffs;
  // «Весь дом» продлевается только тарифами «Весь дом», обычный ключ — только обычными; при покупке — два блока
  const home = (name) => /^\s*🏠/.test(name || "");
  if (key && !R.buy) {
    const same = list.filter((t) => home(t.name) === home(key.tariff_name));
    if (same.length) list = same;
  }
  const regular = list.filter((t) => !home(t.name)), homes = list.filter((t) => home(t.name));
  $("renew-title").textContent = R.buy ? "Купить подписку" : key && home(key.tariff_name) ? "🏠 Продлить «Весь дом»" : "Продление";
  const card = (t) => {
    const price = Number(t.price_minor) || 0, days = Number(t.duration_days) || 0, id = t.id, isHome = home(t.name);
    const name = isHome ? String(t.name).replace(/^\s*🏠\s*Весь дом\s*·\s*/, "") : t.name;
    const canBalance = R.balance !== null && R.balance >= price;
    return `<div class="tariff${isHome ? " t-home" : ""}"><div class="t-head"><span><b>${esc(name || "Тариф")}</b>${days ? `<small>${days} ${plural(days, "день", "дня", "дней")}</small>` : ""}</span><b class="t-price">${rub(price)}</b></div>` +
      `<div class="dev-acts"><button class="btn primary" data-pay="${id}:yookassa_qr"${R.busy ? " disabled" : ""}>${R.busy === id + ":yookassa_qr" ? "Создаём оплату…" : "СБП / Карта"}</button>` +
      (canBalance ? `<button class="btn" data-pay="${id}:balance"${R.busy ? " disabled" : ""}>${R.busy === id + ":balance" ? "Оплачиваем…" : "С баланса"}</button>` : "") + "</div></div>";
  };
  const homeBlock = homes.length
    ? `<div class="t-home-block"><div class="t-home-head"><b>🏠 Весь дом</b><small>Один ключ: роутер дома + 2 устройства с собой. Безлимитный трафик.</small></div>${homes.map(card).join("")}</div>`
    : "";
  const keys = !R.buy && S.allKeys.length > 1
    ? `<div class="keys renew-keys">${S.allKeys.map((k) => `<button data-rkey="${k.id}" class="${k.id === R.keyId ? "on" : ""}">${esc(k.display_name || "Ключ")}</button>`).join("")}</div>`
    : "";
  b.innerHTML =
    keys + (key && !R.buy ? `<p class="muted small" style="margin:0 0 8px">«${esc(key.display_name || "Ключ")}» · ${esc(keyDate(key))}</p>` : "") +
    (R.error ? `<p class="small" style="color:var(--danger);margin:0 0 8px">${esc(R.error)}</p>` : "") +
    (list.length ? regular.map(card).join("") + homeBlock : '<p class="muted">Тарифы сейчас недоступны — попробуй позже или оформи в кабинете.</p>') +
    (R.balance !== null ? `<p class="muted small center" style="margin:10px 0 0">На балансе: ${rub(R.balance)}</p>` : "") +
    '<p class="small center" style="margin:6px 0 0"><a href="#" data-open="/?screen=balance">Промокод и пополнение — в кабинете</a></p>';
}

async function pay(tariffId, method) {
  if (R.busy) return;
  R.busy = tariffId + ":" + method; R.error = ""; renderRenew();
  try {
    const body = { tariff_id: Number(tariffId), method };
    if (!R.buy) body.key_id = R.keyId;
    R.keysBefore = S.allKeys.map((k) => k.id);
    const r = await api(R.buy ? "/topup/purchase" : "/topup/renew", { method: "POST", body });
    R.busy = null;
    if (String(r.payment_url || "").startsWith("http")) {
      R.url = r.payment_url; R.order = r.order_id || null; R.state = "waiting"; renderRenew();
      invoke("open_url", { url: R.url }).catch(() => toast("Не удалось открыть браузер"));
      watchPayment();
    } else if (r.completed || r.ok) onPaid();
    else { R.error = "Не получилось начать оплату — попробуй ещё раз"; renderRenew(); }
  } catch (e) {
    R.busy = null;
    R.error = /недостаточно/i.test(e.message) ? "На балансе не хватает денег — выбери СБП / Карта" : e.message;
    renderRenew();
  }
}

function watchPayment() {
  clearInterval(R.timer);
  let tries = 0;
  R.timer = setInterval(async () => {
    if (R.state !== "waiting") { clearInterval(R.timer); return; }
    if (++tries > 200) { // ~13 минут без ответа
      clearInterval(R.timer); R.state = null; R.error = "Не дождались подтверждения оплаты. Если деньги списались — напиши в поддержку"; renderRenew();
      return;
    }
    if (!R.order) return;
    try {
      const st = String((await api("/topup/payment-status?order_id=" + encodeURIComponent(R.order))).status || "");
      if (st === "paid") onPaid();
      else if (/cancel|fail|expire|reject|declin/.test(st)) { clearInterval(R.timer); R.state = "failed"; renderRenew(); }
    } catch (e) { /* проверим через 4 секунды */ }
  }, 4000);
}

async function onPaid() {
  clearInterval(R.timer);
  R.state = "paid"; renderRenew();
  notify("Оплата прошла", R.buy ? "Подписка оформлена — Mognu VPN готов к подключению" : "Подписка продлена — VPN работает без перерыва");
  // новый ключ сервер создаёт через несколько секунд после оплаты — ждём его до ~2 минут
  for (let i = 0; i < 40; i++) {
    try {
      await loadKeys();
      const fresh = R.buy ? S.keys.find((k) => !R.keysBefore.includes(k.id)) : currentKey();
      if (fresh) { S.keyId = fresh.id; store.set("key", S.keyId); renderKeys(); await loadSubscription(true); return; }
    } catch (e) { /* ещё подождём */ }
    await new Promise((res) => setTimeout(res, 3000));
  }
  toast("Оплата прошла. Ключ появится через минуту — нажми «Обновить» у серверов");
}

$("renew-body").onclick = (e) => {
  const p = e.target.closest("[data-pay]"), k = e.target.closest("[data-rkey]");
  if (p && !p.disabled) { const [id, m] = p.dataset.pay.split(":"); pay(id, m); }
  if (k) { R.keyId = Number(k.dataset.rkey); renderRenew(); }
  if (e.target.closest("#pay-reopen") && R.url) invoke("open_url", { url: R.url }).catch(() => {});
  if (e.target.closest("#pay-cancel") || e.target.closest("#pay-again")) { clearInterval(R.timer); R.state = null; renderRenew(); }
  if (e.target.closest("#pay-done")) $("renew").hidden = true;
};
// закрыть можно и во время ожидания: проверка оплаты идёт дальше, по её итогу придёт уведомление
$("renew-close").onclick = () => {
  if (R.state === "waiting") toast("Ждём оплату в фоне — сообщим, когда пройдёт");
  $("renew").hidden = true;
};
$("renew").onclick = (e) => { if (e.target.id === "renew") $("renew-close").click(); };

// ── поддержка: тот же чат, что в кабинете и Android ─────────────────────────────
// GET /topup/support/messages — одно открытое обращение; POST /topup/support/send {text}; POST /topup/support/close.
// Ответы Могну (сервер: mognu_assistant.py) начинаются с невидимого знака, за ним — знаки кнопок и просьбы об оценке.
const MOGNU = "\u2063", RATE = "\u2064";
const ACTS = { "\u2060": "connect", "\u2061": "renew", "\u2062": "status" };
const HIDDEN = /^[\u2060-\u2064\u206f]+/;
const SP = { thread: 0, status: null, messages: [], loaded: false, waitingSince: 0, rated: 0, busy: false, timer: 0, bg: 0 };
const spIsMognu = (m) => m.sender_type === "admin" && (String(m.text || "").startsWith(MOGNU) || String(m.text || "").startsWith("Привет! Я Могну"));
const spIsRate = (m) => { const t = String(m.text || ""); return t[0] === MOGNU && t[1] === RATE; };
function spActions(m) {
  const t = String(m.text || "");
  if (t[0] !== MOGNU) return [];
  const out = [];
  for (const ch of t.slice(1)) { if (!/[\u2060-\u2064\u206f]/.test(ch)) break; if (ACTS[ch]) out.push(ACTS[ch]); }
  return out;
}
// текст без HTML и невидимых знаков: разбираем как документ (скрипты при этом не выполняются) и берём только текст
function spPlain(m) {
  const raw = String(m.text || "").replace(HIDDEN, "").replace(/\n/g, "<br>");
  const doc = new DOMParser().parseFromString(raw, "text/html");
  doc.querySelectorAll("br").forEach((b) => b.replaceWith("\n"));
  return (doc.body.textContent || "").trim() || (m.media_type === "photo" ? "Фото" : "");
}
const spLastAdmin = () => SP.messages.filter((m) => m.sender_type === "admin").reduce((a, m) => Math.max(a, Number(m.id) || 0), 0);
const spOpen = () => SP.status === "open";

async function spLoad(viewed) {
  if (S.demo || !store.get("token")) return;
  try {
    const r = await api("/topup/support/messages");
    const before = spLastAdmin();
    SP.thread = Number(r.thread_id) || 0;
    SP.status = r.thread_status && r.thread_status !== "null" ? r.thread_status : null;
    SP.messages = r.messages || [];
    SP.loaded = true;
    const last = spLastAdmin(), seenKey = "sp_seen";
    if (last > before && SP.waitingSince) SP.waitingSince = 0;
    const seen = store.get(seenKey);
    if (viewed || !seen || seen.thread !== SP.thread) store.set(seenKey, { thread: SP.thread, id: last });
    else if (spOpen() && last > seen.id) {
      // новый ответ, а чат закрыт — уведомление и точка на кнопке
      store.set(seenKey, { thread: SP.thread, id: last });
      const msg = SP.messages.find((m) => Number(m.id) === last);
      notify(msg && spIsMognu(msg) ? "Могну ответил" : "Поддержка ответила", (msg && spPlain(msg).slice(0, 180)) || "Открой Mognu VPN, чтобы прочитать");
      $("support-dot").hidden = false;
    }
    if (!$("support").hidden) renderSupport();
  } catch (e) { /* без сети — в следующий раз */ }
}

function renderSupport() {
  const list = $("sp-list");
  const msgs = SP.messages.map((m) => [m, spPlain(m)]).filter(([, t]) => t).slice(-40);
  const humans = msgs.some(([m]) => m.sender_type === "admin" && !spIsMognu(m));
  const handed = msgs.some(([m, t]) => spIsMognu(m) && /позвал|передал админу/i.test(t));
  $("sp-sub").textContent = SP.waitingSince ? "Могну печатает…" : SP.rated >= 3 ? "Обращение закрыто — пиши, я тут"
    : humans ? "Админ на связи — отвечает здесь" : handed ? "Позвал админа — он ответит здесь" : "Могну отвечает сразу, сложное передаёт админу";
  if (!msgs.length) {
    list.innerHTML = '<div class="chat-empty"><b>Привет! Я Могну 👑</b><p class="muted small">Напиши, что случилось — отвечу сразу, а сложное передам админу.</p>' +
      '<div class="chips">' + ["Не подключается", "Медленно работает", "Как продлить?", "Позвать человека"].map((c) => `<button data-ask="${c}">${c}</button>`).join("") + "</div></div>";
  } else {
    list.innerHTML = msgs.map(([m, t], i) => {
      const mine = m.sender_type === "user", bot = spIsMognu(m);
      const when = m.created_at ? new Date(String(m.created_at).replace(" ", "T") + (/[zZ+]/.test(m.created_at) ? "" : "Z")) : null;
      const acts = bot ? spActions(m).map((a) => `<button data-act="${a}">${{ connect: "📲 Подключить", renew: "💳 Тарифы и оплата", status: "📊 Статус серверов" }[a]}</button>`).join("") : "";
      const rate = bot && i === msgs.length - 1 && spIsRate(m) && !SP.waitingSince
        ? '<div class="rate">' + [1, 2, 3, 4, 5].map((n) => `<button data-rate="${n}" aria-label="${n} из 5">★</button>`).join("") + "</div>" : "";
      return `<div class="msg ${mine ? "me" : "them"}">${mine ? "" : `<span class="who">${bot ? "Могну" : "Поддержка"}</span>`}` +
        `<div class="bubble">${esc(t).replace(/\n/g, "<br>")}</div>${acts ? `<div class="acts">${acts}</div>` : ""}${rate}` +
        `${when && !isNaN(when) ? `<time>${when.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</time>` : ""}</div>`;
    }).join("") + (SP.waitingSince ? '<div class="msg them"><span class="who">Могну</span><div class="bubble typing"><i></i><i></i><i></i></div></div>' : "");
  }
  list.scrollTop = list.scrollHeight;
  $("sp-close-ticket").hidden = !spOpen();
  $("sp-send").disabled = SP.busy;
}

async function spSend(text, score = 0) {
  const t = String(text || "").trim();
  if (!t || SP.busy) return;
  SP.busy = true; renderSupport();
  try {
    await api("/topup/support/send", { method: "POST", body: { text: t } });
    $("sp-text").value = "";
    if (score) SP.rated = score; else SP.waitingSince = Date.now();
    await spLoad(true);
  } catch (e) { toast(e.message); }
  SP.busy = false; renderSupport();
}

function openSupport() {
  $("settings").hidden = true;
  $("support").hidden = false;
  $("support-dot").hidden = true;
  if (!SP.loaded) $("sp-list").innerHTML = '<p class="muted center">Загружаем переписку…</p>';
  else renderSupport();
  spLoad(true);
  clearInterval(SP.timer);
  // пока чат открыт — свежие ответы каждые 3 секунды, пока Могну «печатает» (до минуты), иначе каждые 8
  let tick = 0;
  SP.timer = setInterval(() => {
    if ($("support").hidden) { clearInterval(SP.timer); return; }
    if (SP.waitingSince && Date.now() - SP.waitingSince > 60000) { SP.waitingSince = 0; renderSupport(); }
    if (SP.waitingSince || ++tick % 3 === 0) spLoad(true);
  }, 3000);
  setTimeout(() => $("sp-text").focus(), 50);
}
$("support-open").onclick = openSupport;
$("settings-support").onclick = openSupport;
$("support-close").onclick = () => { $("support").hidden = true; clearInterval(SP.timer); };
$("support").onclick = (e) => { if (e.target.id === "support") $("support-close").click(); };
$("sp-form").onsubmit = (e) => { e.preventDefault(); spSend($("sp-text").value); };
$("sp-list").onclick = (e) => {
  const ask = e.target.closest("[data-ask]"), act = e.target.closest("[data-act]"), rate = e.target.closest("[data-rate]");
  if (ask) spSend(ask.dataset.ask);
  if (rate) spSend(rate.dataset.rate + " ⭐", Number(rate.dataset.rate));
  if (act) {
    const a = act.dataset.act;
    if (a === "connect") { $("support").hidden = true; if (S.state === "off") connect(); }
    else if (a === "renew") { $("support").hidden = true; openRenew(); }
    else openSite("/status.html");
  }
};
$("sp-close-ticket").onclick = async (e) => {
  e.preventDefault();
  try { await api("/topup/support/close", { method: "POST", body: {} }); toast(`Обращение${SP.thread ? " №" + SP.thread : ""} закрыто`); await spLoad(true); }
  catch (err) { toast(err.message); }
};
// в фоне: раз в минуту, пока обращение открыто — чтобы ответ поддержки не потерялся, даже если окно в трее
function spBackground() {
  clearInterval(SP.bg);
  SP.bg = setInterval(() => { if (spOpen() && $("support").hidden) spLoad(false); }, 60000);
}

// ── подключено: время, IP снаружи, скорость и трафик за сессию ───────────────
let since = 0, clock = 0;
// трафик через сервер: счётчики ядра растут с его запуска; после переподключения ядро считает заново, поэтому
// за сессию складываем только приросты
const T = { up: 0, down: 0, lastUp: null, lastDown: null, lastAt: 0, upRate: 0, downRate: 0 };
function resetTraffic() { Object.assign(T, { up: 0, down: 0, lastUp: null, lastDown: null, lastAt: 0, upRate: 0, downRate: 0 }); }
function bytes(n) {
  if (n < 1024 * 1024) return Math.round(n / 1024) + " КБ";
  if (n < 1024 ** 3) return (n / 1024 / 1024).toFixed(n < 100 * 1024 * 1024 ? 1 : 0).replace(".", ",") + " МБ";
  return (n / 1024 ** 3).toFixed(2).replace(".", ",") + " ГБ";
}
function rate(bps) {
  const bits = bps * 8;
  if (bits < 1e6) return Math.round(bits / 1e3) + " Кбит/с";
  return (bits / 1e6).toFixed(bits < 1e8 ? 1 : 0).replace(".", ",") + " Мбит/с";
}
async function pollTraffic() {
  if (S.state !== "on" || !S.ports || !S.ports.metrics) return;
  try {
    const r = await invoke("http", { req: { url: "http://127.0.0.1:" + S.ports.metrics + "/debug/vars", timeout_ms: 2000 } });
    const o = ((JSON.parse(r.body).stats || {}).outbound || {}).proxy || {};
    const up = Number(o.uplink) || 0, down = Number(o.downlink) || 0, now = Date.now();
    if (T.lastUp !== null && T.lastAt) {
      const dUp = up >= T.lastUp ? up - T.lastUp : up, dDown = down >= T.lastDown ? down - T.lastDown : down;
      const sec = Math.max(0.5, (now - T.lastAt) / 1000);
      T.up += dUp; T.down += dDown;
      // плавно, чтобы цифры не прыгали каждую секунду
      T.upRate = T.upRate * 0.4 + (dUp / sec) * 0.6;
      T.downRate = T.downRate * 0.4 + (dDown / sec) * 0.6;
    }
    Object.assign(T, { lastUp: up, lastDown: down, lastAt: now });
    $("st-down").textContent = rate(T.downRate); $("st-down-total").textContent = "всего " + bytes(T.down);
    $("st-up").textContent = rate(T.upRate); $("st-up-total").textContent = "всего " + bytes(T.up);
  } catch (e) { /* ядро перезапускается — следующая секунда покажет */ }
}
function renderStats() {
  const on = S.state === "on";
  $("stats").hidden = !on;
  clearInterval(clock);
  if (!on) { if (S.state === "off") { since = 0; resetTraffic(); } return; }
  if (!since) { since = Date.now(); $("st-ip").textContent = "…"; resetTraffic(); lookupIp(); }
  const tick = () => {
    const s = Math.floor((Date.now() - since) / 1000), h = Math.floor(s / 3600), two = (n) => String(n).padStart(2, "0");
    $("st-time").textContent = (h ? h + ":" : "") + two(Math.floor(s / 60) % 60) + ":" + two(s % 60);
    pollTraffic();
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
  // запустились вместе с Windows и окно ещё в трее — новая копия с правами тоже останется в трее
  const hidden = S.launch.autostart && document.visibilityState === "hidden";
  const ok = await invoke("relaunch_elevated", { hidden }).catch((e) => { toast(String(e)); return false; });
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
  $("power-mascot").dataset.mood = S.state === "paused" ? "busy" : S.state;
  document.body.classList.toggle("connected", S.state === "on");
  p.setAttribute("aria-label", S.state === "on" || S.state === "paused" ? "Отключить" : "Подключить");
  const srv = current(), label = srv ? flagHtml(cleanName(srv.name).flag) + " " + esc(cleanName(srv.name).name) : "";
  title.classList.toggle("on", S.state === "on");
  const ping = srv && S.pings[keyOf(srv)];
  if (S.state === "on") { title.textContent = "Подключено"; sub.innerHTML = label + (ping ? ` <span class="muted">· ${ping} мс</span>` : ""); }
  else if (S.state === "busy") {
    title.textContent = S.healing ? "Переподключаемся…" : "Подключаем…";
    sub.innerHTML = label + (S.step ? `<span class="step" aria-live="polite"><i></i>${esc(S.step)}</span>` : "");
  }
  else if (S.state === "paused") {
    title.textContent = "Нет связи с сервером";
    sub.textContent = "Интернет на паузе, чтобы ничего не ушло мимо VPN. Пробуем снова…";
  }
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
  // шаги под кнопкой: человек видит, что идёт работа, а не зависание
  const step = (t) => { S.step = t; if (S.state === "busy") renderPower(); };
  S.active = srv; S.state = "busy"; step("Запускаем защищённый туннель");
  try {
    const ports = await invoke("free_ports");
    await invoke("core_start", { config: JSON.stringify(buildConfig(srv, ports, coreOpts())) });
    step("Стучимся на сервер " + cleanName(srv.name).name);
    await new Promise((r) => setTimeout(r, 350));
    step("Проверяем, что интернет идёт через VPN");
    // в режиме «весь трафик» Windows поднимает адаптер и маршруты не сразу: первая проверка может не пройти
    // (так 0.4.0 один раз не подключился в CI), поэтому даём ещё одну попытку через пару секунд
    let ok = await verify(ports.http);
    if (!ok && tun) { await new Promise((r) => setTimeout(r, 2500)); ok = await verify(ports.http); }
    if (!ok) throw new Error("Сервер не отвечает — попробуй другой");
    // в режиме «весь трафик» системный прокси не нужен: трафик и так идёт через адаптер Mognu
    if (!tun) { step("Включаем VPN для браузеров и программ"); await invoke("proxy_set", { port: ports.http }); }
    S.ports = ports; S.state = "on"; S.step = "";
    startWatch();
  } catch (e) {
    await invoke("core_stop").catch(() => {});
    S.state = "off"; S.ports = null; S.active = null; S.step = "";
    invoke("core_note", { text: "не подключилось: " + String(e.message || e).slice(0, 300) }).catch(() => {});
    toast(String(e.message || e).split("\n")[0].slice(0, 140));
  }
  renderPower(); renderServers();
}

async function disconnect(quiet) {
  stopWatch();
  await invoke("core_stop").catch(() => {});
  S.state = "off"; S.ports = null; S.active = null;
  if (!quiet) renderPower();
}

$("power").onclick = () => {
  // во время подключения нажатие ждёт, во время переподключения — отключает
  if (S.state === "busy" && !S.healing) return;
  if (S.healing) { disconnect(); return; }
  if (S.state === "on" || S.state === "paused") disconnect(); else connect();
};

// ── связь под присмотром: переподключение и защита от утечек ─────────────────
// Каждые 15 секунд: ядро живо и сайт открывается через подключение? Две неудачи подряд, упавшее ядро или выход
// из сна — переподключаемся: сначала к тому же серверу, потом к самым быстрым остальным. Ядро перезапускается на тех
// же портах, поэтому системный прокси всё это время указывает на Mognu и браузеры не уходят в интернет напрямую.
// Если не вышло: с защитой от утечек интернет остаётся на паузе и попытки идут дальше, без неё — VPN отключается
// и интернет работает как без Mognu.
const coreOpts = () => ({ tun: S.mode === "tun", ruDirect: store.get("ru_direct", true) });
const guardOn = () => store.get("guard", true);
let watchTimer = 0, watchFails = 0, watchLast = 0;
function startWatch() { stopWatch(); watchFails = 0; watchLast = Date.now(); watchTimer = setInterval(checkHealth, 15000); }
function stopWatch() { clearInterval(watchTimer); watchTimer = 0; }

async function checkHealth() {
  if (S.healing || !S.ports) return;
  const now = Date.now(), woke = now - watchLast > 45000;
  watchLast = now;
  if (S.state === "paused") { heal(); return; }
  if (S.state !== "on") return;
  const alive = await invoke("core_running").catch(() => false);
  if (alive && !woke && (await verify(S.ports.http))) { watchFails = 0; return; }
  if (!alive || woke || ++watchFails >= 2) heal();
}

async function heal() {
  if (S.healing || !S.ports) return;
  S.healing = true;
  const was = S.active, paused = S.state === "paused";
  if (!paused) { S.state = "busy"; renderPower(); }
  const others = S.servers.filter((p) => !isStub(p) && !S.down[keyOf(p)] && (isLte(p) === !!(was && isLte(was))))
    .sort((a, b) => (S.pings[keyOf(a)] || 9e9) - (S.pings[keyOf(b)] || 9e9));
  const order = [was, ...others].filter((p, i, a) => p && a.findIndex((q) => q && keyOf(q) === keyOf(p)) === i).slice(0, 4);
  for (const srv of order) {
    if (!S.ports) break; // пока пробовали, человек нажал «Отключить»
    try {
      await invoke("core_start", { config: JSON.stringify(buildConfig(srv, S.ports, coreOpts())) });
      // «Отключить» нажали, пока ядро перезапускалось: оно не должно остаться работать (в TUN — держать адаптер)
      if (!S.ports) { await invoke("core_stop").catch(() => {}); break; }
      if (await verify(S.ports.http)) {
        S.active = srv; S.state = "on"; S.healing = false; watchFails = 0;
        invoke("core_note", { text: "переподключились: " + cleanName(srv.name).name }).catch(() => {});
        if (was && keyOf(was) !== keyOf(srv)) {
          const msg = cleanName(was.name).name + " не отвечает — переключились на " + cleanName(srv.name).name;
          toast(msg);
          if (document.visibilityState === "hidden") notify("Mognu VPN переключил сервер", msg);
        }
        renderPower(); renderServers();
        return;
      }
    } catch (e) { /* следующий сервер */ }
  }
  S.healing = false;
  if (!S.ports) return;
  invoke("core_note", { text: "связь с серверами пропала" + (guardOn() ? ", интернет на паузе" : ", VPN отключён") }).catch(() => {});
  if (guardOn()) {
    if (S.state !== "paused") notify("Нет связи с сервером", "Интернет на паузе, чтобы ничего не ушло мимо VPN. Mognu VPN пробует переподключиться");
    S.state = "paused"; renderPower(); return;
  }
  await disconnect();
  toast("Связь с серверами пропала — VPN отключён, интернет работает напрямую");
  notify("VPN отключился", "Серверы не отвечают — интернет работает напрямую, без Mognu VPN");
}
// «Подключить / Отключить» из меню значка в трее; до входа в аккаунт пункт ничего не делает
window.__TAURI__.event.listen("tray-toggle", () => { if (!$("home").hidden) $("power").click(); });
// «Обновить» у серверов: значок крутится, пинги заново «ищутся», в конце — «Обновлено»
$("refresh").onclick = async () => {
  const b = $("refresh");
  if (b.classList.contains("busy")) return;
  b.classList.add("busy"); b.lastChild.textContent = "Обновляем…";
  S.pings = {}; S.refreshing = true; renderServers();
  const started = Date.now();
  try { await loadSubscription(true); } finally {
    // крутится хотя бы секунду — иначе мелькает и непонятно, было ли что-то
    await new Promise((r) => setTimeout(r, Math.max(0, 1000 - (Date.now() - started))));
    S.refreshing = false; renderServers();
    b.classList.remove("busy"); b.classList.add("done"); b.lastChild.textContent = "Обновлено";
    setTimeout(() => { b.classList.remove("done"); b.lastChild.textContent = "Обновить"; }, 1800);
  }
};

// ── настройки ────────────────────────────────────────────────────────────────
$("settings-open").onclick = async () => {
  $("settings").hidden = false;
  $("opt-autostart").checked = await invoke("autostart_get").catch(() => false);
  $("opt-autoconnect").checked = store.get("autoconnect", false);
  $("opt-ru").checked = store.get("ru_direct", true);
  $("opt-guard").checked = store.get("guard", true);
  try { const me = await api("/auth/me"); $("account").textContent = me.email || (me.username ? "@" + me.username : "") || ""; } catch (e) {}
};
$("settings-close").onclick = () => ($("settings").hidden = true);
$("opt-autostart").onchange = async (e) => {
  try { await invoke("autostart_set", { on: e.target.checked }); }
  catch (err) { e.target.checked = !e.target.checked; toast("Не удалось изменить автозапуск: " + String(err).slice(0, 80)); }
};
$("opt-autoconnect").onchange = (e) => store.set("autoconnect", e.target.checked);
$("opt-guard").onchange = (e) => store.set("guard", e.target.checked);
// маршруты меняются в ядре: если подключены — переподключаемся к тому же серверу с новыми правилами
$("opt-ru").onchange = async (e) => {
  store.set("ru_direct", e.target.checked);
  if (S.state === "on" && S.active) {
    try { await invoke("core_start", { config: JSON.stringify(buildConfig(S.active, S.ports, coreOpts())) }); }
    catch (err) { heal(); }
  }
  toast(e.target.checked ? "Российские сайты теперь открываются напрямую" : "Теперь все сайты идут через VPN");
};
$("settings").onclick = (e) => { if (e.target.id === "settings") $("settings").hidden = true; };
$("logout").onclick = async () => {
  await disconnect();
  for (const k of ["token", "key", "server", "sp_seen"]) store.del(k);
  clearInterval(SP.bg); clearInterval(SP.timer);
  Object.assign(SP, { thread: 0, status: null, messages: [], loaded: false, waitingSince: 0, rated: 0 });
  $("support-dot").hidden = true; $("support").hidden = true; $("renew").hidden = true; clearInterval(R.timer);
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
// Баннер на главной ведёт по шагам: есть версия → скачиваем (полоска) → готово, перезапуск через 5 секунд →
// установщик закрывает Mognu и открывает уже новую. Если не вышло — «Повторить» и «Скачать вручную».
let pendingUpdate = null, upState = "", upTimer = 0, upChecking = null;
const viaCore = () => (S.state === "on" && S.ports ? S.ports.http : null);
const UP_LINES = [
  "Mognu подкрутил гайки и смазал шестерёнки — обновление займёт меньше минуты.",
  "Свежая версия уже ждёт: быстрее, аккуратнее, надёжнее.",
  "Mognu принёс обновление — пара секунд, и всё как было, только лучше.",
];
const mb = (n) => (n / 1048576).toLocaleString("ru-RU", { maximumFractionDigits: 1 });
const releasePage = (v) => "https://github.com/Said240705/pamir-vpn-android/releases/tag/desktop-v" + v;

function renderUpdate(state, extra = {}) {
  upState = state;
  const u = pendingUpdate || {}, box = $("update"), acts = $("update-acts"), bar = $("update-bar");
  box.hidden = !state; box.dataset.state = state;
  if (!state) return;
  const set = (tag, title, sub) => { $("update-tag").textContent = tag; $("update-title").textContent = title; $("update-sub").textContent = sub; };
  bar.hidden = !(state === "download" || state === "verify" || state === "restart");
  const ico = { done: "M5 12.5l4.5 4.5L19 7.5", error: "M12 7v6M12 17h.01", restart: "M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" }[state] || "M12 3v12M7 10l5 5 5-5M5 21h14";
  box.querySelector(".up-ico").innerHTML = `<svg viewBox="0 0 24 24"><path d="${ico}"/></svg>`;
  if (state === "ready") {
    set("Новая версия", "Вышла Mognu VPN " + u.version, UP_LINES[Math.floor(Math.random() * UP_LINES.length)] + " Ключ и настройки останутся на месте.");
    acts.innerHTML = '<button class="link" id="update-later">Позже</button><button class="btn primary" id="update-go">Обновить</button>';
  } else if (state === "download") {
    const pct = extra.total ? Math.min(100, Math.round((extra.done / extra.total) * 100)) : 0;
    set("Обновление", "Скачиваем Mognu VPN " + u.version, extra.total ? `${mb(extra.done)} из ${mb(extra.total)} МБ · ${pct}%` : "Начинаем скачивание…");
    $("update-fill").style.width = pct + "%";
    acts.innerHTML = "";
  } else if (state === "verify") {
    set("Обновление", "Проверяем файл", "Сверяем контрольную сумму — так мы знаем, что скачалось именно обновление Mognu.");
    $("update-fill").style.width = "100%";
    acts.innerHTML = "";
  } else if (state === "restart") {
    const was = S.state === "on" ? " VPN подключится снова сам." : "";
    set("Всё готово", `Перезапуск через ${extra.left} с`, "Mognu VPN закроется на пару секунд и откроется уже новым — ничего делать не нужно." + was);
    $("update-fill").style.width = "100%";
    acts.innerHTML = '<button class="btn primary" id="update-now">Перезапустить сейчас</button>';
  } else if (state === "error") {
    set("Обновление", "Не получилось обновить", extra.msg || "Проверь интернет и попробуй ещё раз.");
    acts.innerHTML = '<button class="link" id="update-manual">Скачать вручную</button><button class="btn primary" id="update-go">Повторить</button>';
  } else if (state === "done") {
    set("Обновлено", "Mognu VPN " + S.version + " — уже здесь", "Спасибо, что с нами! Хорошего пользования 👑");
    acts.innerHTML = '<button class="btn" id="update-later">Отлично</button>';
  }
}

async function checkUpdate() {
  // одна проверка за раз: из настроек и по таймеру
  if (!upChecking) upChecking = invoke("update_check", { proxy: viaCore() }).finally(() => { upChecking = null; });
  const u = await upChecking;
  if (u && !upState) { pendingUpdate = u; renderUpdate("ready"); }
  return u;
}

async function startUpdate() {
  if (!pendingUpdate || upState === "download" || upState === "verify" || upState === "restart") return;
  renderUpdate("download", { done: 0, total: pendingUpdate.size });
  try {
    await invoke("update_download", { u: pendingUpdate, proxy: viaCore() });
    renderUpdate("verify");
    await new Promise((r) => setTimeout(r, 600));
    let left = 5;
    renderUpdate("restart", { left });
    clearInterval(upTimer);
    upTimer = setInterval(() => { left -= 1; if (left <= 0) applyUpdate(); else renderUpdate("restart", { left }); }, 1000);
  } catch (e) {
    renderUpdate("error", { msg: "Не скачалось: " + String(e).slice(0, 90) + ". Проверь интернет и попробуй ещё раз." });
  }
}

async function applyUpdate() {
  clearInterval(upTimer);
  // новая копия покажет «Обновлено» и, если VPN был включён, подключится снова (launch_info.after_update)
  try { await invoke("update_apply", { reconnect: S.state === "on" }); }
  catch (e) { renderUpdate("error", { msg: "Не запустилась установка: " + String(e).slice(0, 90) }); }
}

window.__TAURI__.event.listen("update-progress", (e) => {
  if (upState === "download") renderUpdate("download", e.payload || {});
});
$("update").onclick = (e) => {
  const id = e.target.closest("button")?.id;
  if (id === "update-go") startUpdate();
  else if (id === "update-now") applyUpdate();
  else if (id === "update-later") renderUpdate("");
  // прямая ссылка на установщик (GitHub или зеркало на нашем сайте) — браузер скачает его сам
  else if (id === "update-manual" && pendingUpdate) invoke("open_url", { url: pendingUpdate.url || releasePage(pendingUpdate.version) }).catch(() => {});
};

// «Проверить обновления» в настройках: ответ прямо в строке, окно настроек не закрывается
$("update-check").onclick = async () => {
  const st = $("update-check-state"), btn = $("update-check");
  if (btn.dataset.busy) return;
  // уже нашли версию — показать баннер (если обновление уже идёт, просто к нему)
  if (btn.dataset.found) { $("settings").hidden = true; if (!upState || upState === "error") renderUpdate("ready"); return; }
  btn.dataset.busy = "1"; st.className = "uc-state busy"; st.innerHTML = '<i class="mini-spin" aria-hidden="true"></i>Проверяем…';
  try {
    const u = await checkUpdate();
    if (u) {
      pendingUpdate = u; btn.dataset.found = "1";
      st.className = "uc-state found"; st.textContent = "Есть " + u.version + " — обновить →";
    } else { st.className = "uc-state ok"; st.textContent = "✓ У тебя последняя версия"; }
  } catch (e) {
    st.className = "uc-state err"; st.textContent = "Нет связи — попробовать ещё";
  }
  delete btn.dataset.busy;
};

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
  spLoad(false).then(spBackground);
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
  const quietCheck = () => checkUpdate().catch(() => {});
  setTimeout(quietCheck, 8000);
  setInterval(quietCheck, 6 * 3600e3);
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
  // перезапуск с правами ради «весь трафик» — подключаемся сразу, человек уже нажал «Подключить»;
  // «Подключаться при запуске» — тоже сразу, к выбранному или самому быстрому серверу
  // после автообновления — «Обновлено» и, если VPN был включён, подключаемся снова
  const after = S.launch.after_update;
  if (after && after.from !== S.version) renderUpdate("done");
  if (S.launch.handoff || (after && after.reconnect) || (store.get("autoconnect", false) && S.state === "off")) connect();
})();
