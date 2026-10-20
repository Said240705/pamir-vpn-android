// Проверка подключения на настоящей Windows (сборка desktop-build.yml): тестовая подписка (секрет MOGNU_TEST_SUB,
// отдельный тестовый клиент, не ключ человека) → для каждого сервера тот же конфиг, что собирает программа →
// установленный xray.exe → запрос через него и сравнение внешнего IP с прямым.
// Логи сборки публичные: не печатаем ни ссылку подписки, ни адреса серверов, ни внешние IP — только имена и итог.
//   node test/e2e.mjs <путь к xray.exe>
import { spawn, execFileSync } from "node:child_process";
import { writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { parseSubscription, buildConfig, cleanName, isStub, isLte } from "../ui/xray.js";

const XRAY = process.argv[2];
const SUB = process.env.MOGNU_TEST_SUB;
if (!SUB) { console.log("MOGNU_TEST_SUB не задан — проверка пропущена"); process.exit(0); }

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function curl(args) {
  try { return execFileSync("curl.exe", ["-s", "--max-time", "15", ...args], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim(); }
  catch (e) { return ""; }
}

const res = await fetch(SUB, { headers: { "User-Agent": "v2rayN/Mognu-Desktop ci", "x-hwid": "mognu-ci-windows", "x-device-os": "Windows", "x-device-model": "CI" } });
if (!res.ok) { console.log("подписка ответила " + res.status); process.exit(1); }
const servers = parseSubscription(await res.text()).filter((p) => !isStub(p));
if (!servers.length) { console.log("в тестовой подписке нет серверов (истекла или лимит устройств?)"); process.exit(1); }

const direct = curl(["https://api.ipify.org"]);
const dir = mkdtempSync(join(tmpdir(), "mognu-e2e-"));
let ok = 0;
const rows = [];
for (const [i, p] of servers.entries()) {
  const ports = { socks: 20800 + i * 2, http: 20801 + i * 2 };
  const cfg = join(dir, `c${i}.json`);
  writeFileSync(cfg, JSON.stringify(buildConfig(p, ports)));
  const core = spawn(XRAY, ["run", "-c", cfg], { stdio: "ignore", windowsHide: true });
  await sleep(1500);
  const started = Date.now();
  const ip = curl(["-x", `http://127.0.0.1:${ports.http}`, "https://api.ipify.org"]);
  const ms = Date.now() - started;
  const web = curl(["-x", `http://127.0.0.1:${ports.http}`, "-o", "NUL", "-w", "%{http_code}", "https://www.google.com/generate_204"]);
  core.kill();
  await sleep(300);
  const { flag, name } = cleanName(p.name);
  const good = /^\d+\.\d+\.\d+\.\d+$|:/.test(ip) && ip !== direct && web === "204";
  if (good) ok++;
  rows.push(`${good ? "✅" : "❌"} ${name}${isLte(p) ? " (LTE)" : ""} — ${good ? `IP сменился, ответ за ${ms} мс` : ip ? "IP не сменился или сайт не открылся" : "нет ответа через сервер"}`);
}
console.log(`Проверка подключения на Windows: ${ok} из ${servers.length} серверов работают`);
for (const r of rows) console.log("  " + r);
process.exit(ok ? 0 : 1);
