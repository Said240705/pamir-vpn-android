"""Mognu VPN: новая веб-админка (admin/index.html) — всё под /admin/m/...

Ставится патчем patch_admin_mognu.py как routers/pamir_admin_mognu.py бэкенда кабинета. Работает с базой бота
напрямую (как pamir_admin_extra.py), а действия с ключами в панели — через бота (/mini-app-api/...), как старая
админка. Сообщения и рассылки уходят от имени бота через Telegram Bot API (BOT_TOKEN бэкенда).

Свои таблицы (создаются сами): pamir_admin_audit — журнал действий, pamir_broadcasts — рассылки.
Время в базе — UTC; «сегодня» и графики по дням — по Москве (display_timezone бота).
"""
import asyncio
import json
import os
import time
import re
from datetime import datetime, timedelta, timezone

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

import auth
import db

router = APIRouter(prefix="/admin/m", tags=["admin"])

BOT_API = os.getenv("BOT_MINI_APP_BASE_URL", "http://127.0.0.1:8088/mini-app-api")
SITE = (os.getenv("PUBLIC_APP_URL") or "https://mognu.app").rstrip("/")
TG_API = os.getenv("PAMIR_TELEGRAM_API", "https://api.telegram.org")  # подмена только для проверки
BOT_USERNAME = "pamirlink_bot"
MSK = "+3 hours"  # display_timezone = Europe/Moscow, без перехода на летнее время
# Реальные деньги: оплачено, к оплате > 0, не списание с баланса и не пробный период.
PAID = "p.status = 'paid' AND p.payable_amount_minor > 0 AND COALESCE(p.payment_type, '') NOT IN ('balance', 'trial')"
DRAFT = "(k.server_id IS NULL OR COALESCE(k.panel_email, '') = '')"
TRIAL_KEY = "EXISTS (SELECT 1 FROM trial_activations ta WHERE ta.vpn_key_id = k.id)"
ACTION_RU = {"key.extend": "продлил ключ", "key.delete": "удалил ключ", "key.fix": "доделал ключ", "key.reset_devices": "сбросил устройства",
             "key.sub_url": "смотрел ссылку подписки", "user.balance": "изменил баланс", "user.ban": "блокировка", "user.gift": "подарил дни",
             "user.message": "написал через бота", "user.note": "заметка и метки", "payment.complete": "доделал оплату"}
PURPOSE = {"key_purchase": "Покупка ключа", "key_renewal": "Продление", "balance_topup": "Пополнение баланса",
           "trial": "Пробный период", "device_slot": "Доп. устройство"}

# Настройки бота, которые можно менять из админки: ключ → (группа, подпись, тип, подсказка)
SETTINGS = {
    "yookassa_qr_enabled": ("Оплата", "Оплата через СБП (ЮKassa)", "bool", ""),
    "stars_enabled": ("Оплата", "Оплата Telegram Stars", "bool", ""),
    "referral_enabled": ("Сервис", "Реферальная программа", "bool", "дни за приглашённых друзей"),
    "notification_days": ("Сервис", "За сколько дней напоминать об окончании", "number", "бот пишет человеку перед концом подписки"),
    "expired_key_retention_days": ("Сервис", "Сколько дней хранить истёкший ключ", "number", "потом ключ удаляется"),
    "expired_key_deletion_notifications_enabled": ("Сервис", "Предупреждать перед удалением истёкшего ключа", "bool", ""),
    "payment_notifications_enabled": ("Сервис", "Сообщать админам об оплатах", "bool", "сообщение в Telegram на каждую оплату"),
    "coupon_lapsed_enabled": ("Купоны", "Скидка тем, у кого закончилась подписка", "bool", ""),
    "coupon_lapsed_discount_percent": ("Купоны", "…размер скидки, %", "number", ""),
    "coupon_lapsed_delay_days": ("Купоны", "…через сколько дней после окончания", "number", ""),
    "coupon_lapsed_lifetime_days": ("Купоны", "…сколько дней действует купон", "number", ""),
    "coupon_auto_enabled": ("Купоны", "Купон после оплаты на следующую покупку", "bool", ""),
    "coupon_auto_discount_percent": ("Купоны", "…размер скидки, %", "number", ""),
    "coupon_auto_lifetime_days": ("Купоны", "…сколько дней действует купон", "number", ""),
}
NUMBER_RANGE = (0, 365)

# Сегменты рассылки: условие на users u (+ общий фильтр: есть Telegram, не бан, бот не заблокирован)
ACTIVE = "EXISTS (SELECT 1 FROM vpn_keys k WHERE k.user_id = u.id AND k.expires_at > datetime('now'))"
ANY_KEY = "EXISTS (SELECT 1 FROM vpn_keys k WHERE k.user_id = u.id)"
EVER_PAID = f"EXISTS (SELECT 1 FROM payments p WHERE p.user_id = u.id AND {PAID})"
SEGMENTS = {
    "all": "1 = 1",
    "active": ACTIVE,
    "expiring_3d": "EXISTS (SELECT 1 FROM vpn_keys k WHERE k.user_id = u.id AND k.expires_at > datetime('now') "
                   "AND k.expires_at <= datetime('now', '+3 days')) AND NOT EXISTS (SELECT 1 FROM vpn_keys k "
                   "WHERE k.user_id = u.id AND k.expires_at > datetime('now', '+3 days'))",
    "expired": f"{ANY_KEY} AND NOT {ACTIVE}",
    "trial_only": f"u.used_trial = 1 AND NOT {EVER_PAID}",
    "never_paid": f"NOT {EVER_PAID}",
    "balance_no_sub": f"u.personal_balance > 0 AND NOT {ACTIVE}",
    "inactive_30d": f"{ANY_KEY} AND NOT EXISTS (SELECT 1 FROM vpn_keys k WHERE k.user_id = u.id "
                    "AND k.expires_at > datetime('now', '-30 days'))",
}
REACHABLE = "u.telegram_id > 0 AND COALESCE(u.is_banned, 0) = 0 AND COALESCE(u.is_bot_blocked, 0) = 0"
BUTTONS = {"renew": f"{SITE}/?screen=subscriptions", "cabinet": f"{SITE}/", "app": f"{SITE}/android.html",
           "support": f"https://t.me/{BOT_USERNAME}"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def _scalar(conn, sql, args=()):
    row = await (await conn.execute(sql, args)).fetchone()
    return row[0] if row else None


async def _rows(conn, sql, args=()):
    return [dict(r) for r in await (await conn.execute(sql, args)).fetchall()]


def _tg(admin) -> int:
    return int(admin.get("tg_id") or str(admin.get("sub", "0")).split(":")[-1] or 0)


_ready = False


async def _ensure(conn):
    global _ready
    if _ready:
        return
    await conn.execute("""CREATE TABLE IF NOT EXISTS pamir_admin_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT, at TIMESTAMP NOT NULL, admin_tg INTEGER, action TEXT NOT NULL,
        user_id INTEGER, details TEXT)""")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_pamir_admin_audit_user ON pamir_admin_audit(user_id)")
    await conn.execute("""CREATE TABLE IF NOT EXISTS pamir_broadcasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TIMESTAMP NOT NULL, admin_tg INTEGER, segment TEXT NOT NULL,
        text TEXT NOT NULL, button_text TEXT, button_action TEXT, scheduled_at TIMESTAMP, status TEXT NOT NULL,
        total INTEGER NOT NULL DEFAULT 0, sent INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0,
        finished_at TIMESTAMP)""")
    await conn.execute("""CREATE TABLE IF NOT EXISTS pamir_user_clients (
        user_id INTEGER NOT NULL, client TEXT NOT NULL, version TEXT, first_seen TIMESTAMP NOT NULL, last_seen TIMESTAMP NOT NULL,
        PRIMARY KEY (user_id, client))""")
    await conn.execute("""CREATE TABLE IF NOT EXISTS pamir_payment_clients (
        order_id TEXT PRIMARY KEY, user_id INTEGER, client TEXT NOT NULL, created_at TIMESTAMP NOT NULL)""")
    await conn.execute("CREATE TABLE IF NOT EXISTS pamir_admin_meta (key TEXT PRIMARY KEY, value TEXT)")
    await conn.execute("""CREATE TABLE IF NOT EXISTS pamir_user_notes (
        user_id INTEGER PRIMARY KEY, note TEXT, tags TEXT, updated_at TIMESTAMP, admin_tg INTEGER)""")
    await conn.execute("""CREATE TABLE IF NOT EXISTS pamir_online_samples (
        at TIMESTAMP NOT NULL, location TEXT NOT NULL, n INTEGER NOT NULL)""")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_pamir_online_samples_at ON pamir_online_samples(at)")
    await conn.execute("INSERT OR IGNORE INTO pamir_admin_meta (key, value) VALUES ('clients_since', ?)", (_now(),))
    await conn.commit()
    _ready = True


async def _audit(admin, action, user_id=None, details=""):
    conn = await db.get_db()
    try:
        await _ensure(conn)
        await conn.execute("INSERT INTO pamir_admin_audit (at, admin_tg, action, user_id, details) VALUES (?, ?, ?, ?, ?)",
                           (_now(), _tg(admin), action, user_id, str(details)[:500]))
        await conn.commit()
    finally:
        await conn.close()


async def _bot(method, path, payload=None, timeout=30):
    """Вызов бота (/mini-app-api) с тем же секретом, что у старой админки."""
    headers = {"X-Pamir-MiniApp-Secret": os.getenv("MINI_APP_API_SECRET", "")}
    try:
        async with aiohttp.ClientSession() as s:
            kw = {"json": payload} if method == "POST" else {"params": payload}
            async with s.request(method, BOT_API + path, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout), **kw) as r:
                data = await r.json(content_type=None)
    except Exception:
        raise HTTPException(502, "Не удалось связаться с ботом")
    if not isinstance(data, dict):
        raise HTTPException(502, "Бот ответил непонятно")
    return data


async def _telegram(chat_id, text, button=None):
    """Сообщение от бота. HTML; если Telegram не принял разметку — тем же текстом без неё. → (ok, blocked)."""
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        raise HTTPException(500, "BOT_TOKEN не настроен на сервере")
    body = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if button:
        body["reply_markup"] = {"inline_keyboard": [[{"text": button[0], "url": button[1]}]]}
    async with aiohttp.ClientSession() as s:
        for attempt in range(3):
            async with s.post(f"{TG_API}/bot{token}/sendMessage", json=body,
                              timeout=aiohttp.ClientTimeout(total=20)) as r:
                data = await r.json(content_type=None)
            if data.get("ok"):
                return True, False
            desc = str(data.get("description", ""))
            if r.status == 429:
                await asyncio.sleep(int((data.get("parameters") or {}).get("retry_after", 2)) + 1)
                continue
            if "can't parse" in desc and "parse_mode" in body:
                body.pop("parse_mode")
                body["text"] = re.sub(r"<[^>]+>", "", text)
                continue
            return False, r.status == 403
    return False, False


# ---------- поиск ----------

@router.get("/search")
async def search(q: str, admin=Depends(auth.current_admin)):
    q = q.strip()
    if len(q) < 2:
        return {"users": [], "keys": [], "payments": []}
    conn = await db.get_db()
    try:
        like = "%" + q.lstrip("@").replace("%", "").replace("_", "\\_") + "%"
        num = int(q.lstrip("#")) if re.fullmatch(r"#?\d{1,19}", q) else None
        users = await _rows(conn, """
            SELECT id, telegram_id, username, first_name, last_name, email FROM users
            WHERE id = ? OR telegram_id = ? OR username LIKE ? ESCAPE '\\' OR email LIKE ? ESCAPE '\\'
               OR first_name LIKE ? ESCAPE '\\' ORDER BY (id = ? OR telegram_id = ?) DESC, id DESC LIMIT 8""",
            (num or -1, num or -1, like, like, like, num or -1, num or -1))
        keys = await _rows(conn, f"""
            SELECT k.id, k.user_id, u.username, u.first_name, u.telegram_id,
                   CASE WHEN {DRAFT} THEN 'черновик' WHEN k.expires_at > datetime('now') THEN 'активен' ELSE 'истёк' END AS status
            FROM vpn_keys k JOIN users u ON u.id = k.user_id
            WHERE k.id = ? OR k.custom_name LIKE ? ESCAPE '\\' OR k.panel_email LIKE ? ESCAPE '\\' LIMIT 5""",
            (num or -1, like, like))
        payments = await _rows(conn, """
            SELECT p.order_id, p.user_id, p.status, p.payable_amount_minor, u.username, u.first_name, u.telegram_id
            FROM payments p JOIN users u ON u.id = p.user_id WHERE p.order_id = ? OR p.order_id LIKE ? LIMIT 5""",
            (q, q.upper() + "%"))
        return {"users": users, "keys": keys, "payments": payments}
    finally:
        await conn.close()


# ---------- обзор и тревоги ----------

async def _stuck(conn):
    """Оплачено, но бот не довёл до конца: заказ не завершён дольше 15 минут или ключ остался черновиком."""
    return await _rows(conn, f"""
        SELECT p.order_id, p.user_id, p.purpose, p.paid_at, p.payable_amount_minor, p.fulfillment_status,
               p.fulfillment_last_error, p.vpn_key_id, u.telegram_id, u.username, u.first_name,
               (SELECT {DRAFT} FROM vpn_keys k WHERE k.id = p.vpn_key_id) AS key_draft
        FROM payments p JOIN users u ON u.id = p.user_id
        WHERE p.status = 'paid' AND p.paid_at >= datetime('now', '-30 days')
          AND (
            (COALESCE(p.fulfillment_status, '') != 'completed' AND p.paid_at <= datetime('now', '-15 minutes')
             AND p.purpose IN ('key_purchase', 'key_renewal', 'balance_topup'))
            OR EXISTS (SELECT 1 FROM vpn_keys k WHERE k.id = p.vpn_key_id AND {DRAFT}))
        ORDER BY p.paid_at DESC LIMIT 50""")


@router.get("/alerts")
async def alerts(admin=Depends(auth.current_admin)):
    await _start_background()  # на случай, если бэкенд не вызывает startup-события (lifespan)
    conn = await db.get_db()
    try:
        items = []
        drafts = await _scalar(conn, f"SELECT COUNT(*) FROM vpn_keys k WHERE {DRAFT}")
        if drafts:
            items.append({"level": "bad", "title": f"Черновых ключей: {drafts}", "text": "ключ есть в базе, но не стоит в панели",
                          "href": "#/keys?status=draft", "action": "Доделать"})
        stuck = await _stuck(conn)
        if stuck:
            items.append({"level": "bad", "title": f"Зависших оплат: {len(stuck)}", "text": "оплачено, но бот не довёл заказ",
                          "href": "#/payments?tab=stuck", "action": "Разобрать"})
        for s in await _rows(conn, """SELECT s.name, h.status, h.checked_at FROM servers s
                                      LEFT JOIN server_health h ON h.server_id = s.id WHERE s.is_active = 1"""):
            if s["status"] and s["status"] != "up":
                items.append({"level": "bad", "title": f"Сервер «{s['name']}» не отвечает", "href": "#/servers", "action": "Серверы"})
            elif s["checked_at"] and s["checked_at"] < (datetime.now(timezone.utc) - timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S"):
                items.append({"level": "warn", "title": f"Сервер «{s['name']}» давно не проверялся", "text": "проверка бота не обновлялась 20+ минут",
                              "href": "#/servers", "action": "Серверы"})
        for loc in await _rows(conn, "SELECT name, status FROM location_health WHERE status NOT IN ('up', 'unknown')"):
            items.append({"level": "warn", "title": f"Локация «{loc['name']}» не работает", "href": "#/servers", "action": "Серверы"})
        support_open = await _scalar(conn, "SELECT COUNT(*) FROM support_threads WHERE status = 'open'") or 0
        if support_open:
            items.append({"level": "warn", "title": f"Открытых обращений: {support_open}", "href": "#/support", "action": "Ответить"})
        if not items:
            items.append({"level": "ok", "title": "Всё в порядке", "text": "серверы отвечают, ключи на месте, оплаты доведены"})
        return {"items": items, "support_open": support_open}
    finally:
        await conn.close()


@router.get("/overview")
async def overview(admin=Depends(auth.current_admin)):
    conn = await db.get_db()
    try:
        today = f"date(p.paid_at, '{MSK}') = date('now', '{MSK}')"
        out = {
            "payments_today": await _scalar(conn, f"SELECT COUNT(*) FROM payments p WHERE {PAID} AND {today}"),
            "revenue_30d_minor": await _scalar(conn, f"SELECT COALESCE(SUM(p.payable_amount_minor), 0) FROM payments p WHERE {PAID} AND p.paid_at >= datetime('now', '-30 days')"),
            "trial_active_keys": await _scalar(conn, f"SELECT COUNT(*) FROM vpn_keys k WHERE k.expires_at > datetime('now') AND {TRIAL_KEY}"),
            "paid_active_keys": await _scalar(conn, f"SELECT COUNT(*) FROM vpn_keys k WHERE k.expires_at > datetime('now') AND NOT {TRIAL_KEY}"),
            "new_today": await _scalar(conn, f"SELECT COUNT(*) FROM users WHERE date(created_at, '{MSK}') = date('now', '{MSK}')"),
            "new_7d": await _scalar(conn, "SELECT COUNT(*) FROM users WHERE created_at >= datetime('now', '-7 days')"),
            "support_open": await _scalar(conn, "SELECT COUNT(*) FROM support_threads WHERE status = 'open'"),
        }
        r = await (await conn.execute(f"""SELECT SUM(u.used_trial = 1) AS t,
                SUM(u.used_trial = 1 AND EXISTS (SELECT 1 FROM payments p WHERE p.user_id = u.id AND {PAID})) AS p
            FROM users u WHERE u.created_at >= datetime('now', '-30 days')""")).fetchone()
        out["trial_conversion_30d"] = round((r["p"] or 0) / r["t"] * 100) if r["t"] else 0
        return out
    finally:
        await conn.close()


@router.get("/daily")
async def daily(days: int = 30, admin=Depends(auth.current_admin)):
    days = max(1, min(days, 366))
    conn = await db.get_db()
    try:
        since = f"date('now', '{MSK}', '-{days - 1} days')"
        out = {}
        for r in await _rows(conn, f"""SELECT date(p.paid_at, '{MSK}') AS day, COUNT(*) AS payments,
                                       SUM(p.payable_amount_minor) AS revenue_minor FROM payments p
                                       WHERE {PAID} AND date(p.paid_at, '{MSK}') >= {since} GROUP BY 1"""):
            out.setdefault(r["day"], {}).update(payments=r["payments"], revenue_minor=r["revenue_minor"])
        for r in await _rows(conn, f"""SELECT date(created_at, '{MSK}') AS day, COUNT(*) AS n FROM users
                                       WHERE date(created_at, '{MSK}') >= {since} GROUP BY 1"""):
            out.setdefault(r["day"], {})["new_users"] = r["n"]
        return {"days": [{"day": d, **v} for d, v in sorted(out.items())]}
    finally:
        await conn.close()


# ---------- пользователь ----------

@router.get("/users/{user_id}/extra")
async def user_extra(user_id: int, admin=Depends(auth.current_admin)):
    conn = await db.get_db()
    try:
        await _ensure(conn)
        u = await (await conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))).fetchone()
        if not u:
            raise HTTPException(404, "Пользователь не найден")
        u = dict(u)
        out = {
            "used_trial": u.get("used_trial") or 0, "email_verified": u.get("email_verified") or 0,
            "is_bot_blocked": u.get("is_bot_blocked") or 0, "referred_by": u.get("referred_by"),
            "invited": await _scalar(conn, "SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,)),
            "paid_total_minor": await _scalar(conn, f"SELECT COALESCE(SUM(p.payable_amount_minor), 0) FROM payments p WHERE p.user_id = ? AND {PAID}", (user_id,)),
            "support_thread_id": await _scalar(conn, "SELECT id FROM support_threads WHERE user_id = ? ORDER BY last_message_at DESC LIMIT 1", (user_id,)),
        }
        keys = {}
        for k in await _rows(conn, f"""
                SELECT k.id, {DRAFT} AS draft, k.expires_at > datetime('now') AS alive, s.name AS server_name,
                       COALESCE(k.max_ips_override, ds.device_limit, t.max_ips) AS devices_limit, {TRIAL_KEY} AS trial
                FROM vpn_keys k LEFT JOIN servers s ON s.id = k.server_id LEFT JOIN tariffs t ON t.id = k.tariff_id
                LEFT JOIN key_device_slots ds ON ds.key_id = k.id WHERE k.user_id = ?""", (user_id,)):
            keys[str(k["id"])] = {"status": "draft" if k["draft"] else "active" if k["alive"] else "expired",
                                  "server_name": k["server_name"], "devices_limit": k["devices_limit"], "trial": bool(k["trial"])}
        out["keys"] = keys
        out["clients"] = await _rows(conn, "SELECT client, version, last_seen FROM pamir_user_clients WHERE user_id = ? ORDER BY last_seen DESC", (user_id,))
        out["clients_since"] = await _scalar(conn, "SELECT value FROM pamir_admin_meta WHERE key = 'clients_since'")
        # Платежи полностью: скидка, промокод, списание с баланса — чтобы «90 ₽» и «0 ₽» было понятно
        out["payments"] = await _rows(conn, """SELECT order_id, status, purpose, description, payment_type, paid_at, created_at,
                                                      payable_amount_minor, nominal_amount_minor, balance_deduct_minor,
                                                      discount_percent, promo_code
                                               FROM payments WHERE user_id = ? ORDER BY id DESC LIMIT 50""", (user_id,))
        n = await (await conn.execute("SELECT note, tags, updated_at FROM pamir_user_notes WHERE user_id = ?", (user_id,))).fetchone()
        out["note"] = n["note"] if n else ""
        out["tags"] = [t for t in (n["tags"] or "").split(",") if t] if n else []
        out["note_updated_at"] = n["updated_at"] if n else None

        tl = [{"at": u["created_at"], "kind": "", "title": "Зарегистрировался",
               "text": "через почту" if (u.get("telegram_id") or 0) <= 0 else ""}]
        for r in await _rows(conn, "SELECT activated_at, vpn_key_id FROM trial_activations WHERE user_id = ?", (user_id,)):
            tl.append({"at": r["activated_at"], "kind": "key", "title": "Взял пробный период", "text": f"ключ #{r['vpn_key_id']}" if r["vpn_key_id"] else ""})
        for r in await _rows(conn, """SELECT paid_at, purpose, payment_type, payable_amount_minor, description, order_id FROM payments
                                      WHERE user_id = ? AND status = 'paid' AND COALESCE(payment_type, '') != 'trial' ORDER BY id DESC LIMIT 30""", (user_id,)):
            how = {"yookassa_qr": "СБП", "balance": "с баланса", "stars": "Stars"}.get(r["payment_type"], r["payment_type"] or "")
            tl.append({"at": r["paid_at"], "kind": "pay", "title": r["description"] or PURPOSE.get(r["purpose"], r["purpose"]),
                       "text": f"{r['payable_amount_minor'] / 100:.0f} ₽ · {how} · {r['order_id']}"})
        for r in await _rows(conn, """SELECT created_at, operation_type, delta_days, source, vpn_key_id FROM key_operation_log
                                      WHERE user_id = ? ORDER BY id DESC LIMIT 20""", (user_id,)):
            tl.append({"at": r["created_at"], "kind": "key", "title": f"Ключ #{r['vpn_key_id']}: {r['operation_type']}",
                       "text": (f"{r['delta_days']:+d} дн. · " if r["delta_days"] else "") + (r["source"] or "")})
        for r in await _rows(conn, """SELECT created_at, delta_minor, delta_cents, source, reason FROM balance_operations
                                      WHERE user_id = ? ORDER BY id DESC LIMIT 20""", (user_id,)):
            d = r["delta_minor"] or r["delta_cents"] or 0
            tl.append({"at": r["created_at"], "kind": "pay", "title": f"Баланс {d / 100:+.0f} ₽", "text": r["reason"] or r["source"] or ""})
        for r in await _rows(conn, "SELECT created_at, status FROM support_threads WHERE user_id = ? ORDER BY id DESC LIMIT 10", (user_id,)):
            tl.append({"at": r["created_at"], "kind": "sup", "title": "Обращение в поддержку", "text": "открыто" if r["status"] == "open" else "закрыто"})
        for r in await _rows(conn, "SELECT at, action, details FROM pamir_admin_audit WHERE user_id = ? ORDER BY id DESC LIMIT 20", (user_id,)):
            tl.append({"at": r["at"], "kind": "bad" if r["action"] in ("user.ban", "key.delete") else "",
                       "title": "Админ: " + ACTION_RU.get(r["action"], r["action"]), "text": r["details"] or ""})
        tl.sort(key=lambda x: str(x["at"] or ""), reverse=True)
        out["timeline"] = tl[:60]
        return out
    finally:
        await conn.close()


async def _user(conn, user_id):
    u = await (await conn.execute("SELECT id, telegram_id, username, first_name FROM users WHERE id = ?", (user_id,))).fetchone()
    if not u:
        raise HTTPException(404, "Пользователь не найден")
    return dict(u)


async def _extend(key_id: int, days: int):
    """Продление тем же путём, что и старая админка (бот меняет срок в базе), и сразу — в панели."""
    data = await _bot("POST", "/admin-key-extend", {"key_id": key_id, "days": days}, 15)
    if not data.get("ok"):
        raise HTTPException(400, {"key_not_found": "Ключ не найден"}.get(data.get("reason"), "Не удалось продлить ключ"))
    try:
        await _bot("POST", "/mognu-admin/key-sync", {"key_id": key_id}, 30)
    except HTTPException:
        pass  # срок в базе уже новый; панель подтянет его при плановой сверке бота
    return data


class DaysIn(BaseModel):
    days: int


@router.post("/keys/{key_id}/extend")
async def key_extend(key_id: int, payload: DaysIn, admin=Depends(auth.current_admin)):
    if not 1 <= payload.days <= 3650:
        raise HTTPException(400, "От 1 до 3650 дней")
    conn = await db.get_db()
    try:
        uid = await _scalar(conn, "SELECT user_id FROM vpn_keys WHERE id = ?", (key_id,))
    finally:
        await conn.close()
    data = await _extend(key_id, payload.days)
    await _audit(admin, "key.extend", uid, f"ключ #{key_id} +{payload.days} дн. → до {data.get('expires_at')}")
    return data


@router.post("/keys/{key_id}/delete")
async def key_delete(key_id: int, admin=Depends(auth.current_admin)):
    conn = await db.get_db()
    try:
        uid = await _scalar(conn, "SELECT user_id FROM vpn_keys WHERE id = ?", (key_id,))
    finally:
        await conn.close()
    data = await _bot("POST", "/admin-key-delete", {"key_id": key_id}, 20)
    if not data.get("ok"):
        raise HTTPException(400, data.get("reason") or "Не удалось удалить ключ")
    await _audit(admin, "key.delete", uid, f"ключ #{key_id}")
    return data


@router.post("/keys/{key_id}/fix")
async def key_fix(key_id: int, admin=Depends(auth.current_admin)):
    """Черновик (нет сервера или клиента в панели): бот ставит ключ так же, как после оплаты (fix_draft_keys.py)."""
    conn = await db.get_db()
    try:
        k = await (await conn.execute(f"""SELECT k.id, k.user_id, {DRAFT} AS draft, u.telegram_id,
                (SELECT p.order_id FROM payments p WHERE p.vpn_key_id = k.id AND p.status = 'paid' ORDER BY p.id LIMIT 1) AS order_id
            FROM vpn_keys k JOIN users u ON u.id = k.user_id WHERE k.id = ?""", (key_id,))).fetchone()
    finally:
        await conn.close()
    if not k:
        raise HTTPException(404, "Ключ не найден")
    if not k["draft"]:
        return {"ok": True, "message": "Ключ уже стоит в панели"}
    if not k["order_id"]:
        raise HTTPException(409, "Не нашёл оплаченный заказ этого ключа — доделать автоматически нельзя")
    data = await _bot("POST", "/mognu-admin/fix-order", {"order_id": k["order_id"], "telegram_id": k["telegram_id"]}, 90)
    await _audit(admin, "key.fix", k["user_id"], f"ключ #{key_id}, заказ {k['order_id']}: {data.get('status')}")
    if not data.get("ok"):
        raise HTTPException(400, f"Бот не смог поставить ключ: {data.get('error_code') or data.get('reason') or data.get('status')}")
    return {"ok": True, "message": f"Ключ поставлен в панель ({data.get('status')})"}


@router.post("/keys/fix-drafts")
async def keys_fix_drafts(admin=Depends(auth.current_admin)):
    conn = await db.get_db()
    try:
        ids = [r["id"] for r in await _rows(conn, f"SELECT k.id FROM vpn_keys k WHERE {DRAFT} LIMIT 50")]
    finally:
        await conn.close()
    fixed = failed = 0
    for kid in ids:
        try:
            await key_fix(kid, admin)
            fixed += 1
        except HTTPException:
            failed += 1
    return {"fixed": fixed, "failed": failed}


@router.post("/keys/{key_id}/reset-devices")
async def key_reset_devices(key_id: int, admin=Depends(auth.current_admin)):
    conn = await db.get_db()
    try:
        k = await (await conn.execute("SELECT k.user_id, u.telegram_id FROM vpn_keys k JOIN users u ON u.id = k.user_id WHERE k.id = ?", (key_id,))).fetchone()
    finally:
        await conn.close()
    if not k:
        raise HTTPException(404, "Ключ не найден")
    data = await _bot("GET", "/devices", {"telegram_id": k["telegram_id"], "key_id": key_id}, 20)
    if not data.get("ok", True):
        raise HTTPException(400, "Бот не отдал список устройств: " + str(data.get("reason")))
    devices = data.get("devices") or data.get("items") or []
    removed = 0
    for d in devices:
        did = d.get("id") if isinstance(d, dict) else None
        if isinstance(did, int):
            r = await _bot("POST", "/devices/remove", {"telegram_id": k["telegram_id"], "key_id": key_id, "device_id": did}, 20)
            removed += 1 if r.get("removed") == did or r.get("ok", True) else 0
    await _audit(admin, "key.reset_devices", k["user_id"], f"ключ #{key_id}: отвязано {removed}")
    return {"ok": True, "removed": removed}


class BalanceIn(BaseModel):
    delta_minor: int


@router.post("/users/{user_id}/balance")
async def user_balance(user_id: int, payload: BalanceIn, admin=Depends(auth.current_admin)):
    if not payload.delta_minor or abs(payload.delta_minor) > 100_000_00:
        raise HTTPException(400, "Сумма от 1 ₽ до 100 000 ₽")
    new_balance = await db.admin_adjust_balance(user_id, payload.delta_minor)
    await _audit(admin, "user.balance", user_id, f"{payload.delta_minor / 100:+.0f} ₽ → {new_balance / 100:.0f} ₽")
    return {"personal_balance": new_balance}


class BanIn(BaseModel):
    banned: bool


@router.post("/users/{user_id}/ban")
async def user_ban(user_id: int, payload: BanIn, admin=Depends(auth.current_admin)):
    await db.admin_set_ban(user_id, payload.banned)
    await _audit(admin, "user.ban", user_id, "заблокирован" if payload.banned else "разблокирован")
    return {"status": "ok"}


class GiftIn(BaseModel):
    days: int
    notify: bool = True


@router.post("/users/{user_id}/gift")
async def user_gift(user_id: int, payload: GiftIn, admin=Depends(auth.current_admin)):
    if not 1 <= payload.days <= 365:
        raise HTTPException(400, "От 1 до 365 дней")
    conn = await db.get_db()
    try:
        u = await _user(conn, user_id)
        ids = [r["id"] for r in await _rows(conn, "SELECT id FROM vpn_keys WHERE user_id = ? AND expires_at > datetime('now')", (user_id,))]
        if not ids:
            ids = [r["id"] for r in await _rows(conn, "SELECT id FROM vpn_keys WHERE user_id = ? ORDER BY expires_at DESC LIMIT 1", (user_id,))]
    finally:
        await conn.close()
    if not ids:
        raise HTTPException(409, "У человека нет ни одного ключа — подарить дни некуда")
    for kid in ids:
        await _extend(kid, payload.days)
    if payload.notify and (u["telegram_id"] or 0) > 0:
        try:
            await _telegram(u["telegram_id"], f"🎁 Mognu VPN дарит вам <b>{payload.days} дн.</b> подписки! Срок уже продлён — просто пользуйтесь.")
        except Exception:
            pass
    await _audit(admin, "user.gift", user_id, f"+{payload.days} дн. ключам {', '.join('#' + str(i) for i in ids)}")
    return {"ok": True, "keys": len(ids)}


class MessageIn(BaseModel):
    text: str


@router.post("/users/{user_id}/message")
async def user_message(user_id: int, payload: MessageIn, admin=Depends(auth.current_admin)):
    text = payload.text.strip()
    if not text or len(text) > 4000:
        raise HTTPException(400, "Текст от 1 до 4000 символов")
    conn = await db.get_db()
    try:
        u = await _user(conn, user_id)
    finally:
        await conn.close()
    if (u["telegram_id"] or 0) <= 0:
        raise HTTPException(409, "У человека нет Telegram — только почта")
    # Через обращение в поддержку: ответ человека придёт в «Поддержку», а не в карточку кабинета
    conn = await db.get_db()
    try:
        thread_id = await _scalar(conn, "SELECT id FROM support_threads WHERE user_telegram_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
                                  (u["telegram_id"],))
        if not thread_id:
            now = _now()
            cur = await conn.execute(
                """INSERT INTO support_threads (user_id, user_telegram_id, initiator_type, initiator_admin_id, assigned_admin_id,
                                                status, created_at, updated_at, last_message_at)
                   VALUES (?, ?, 'admin', ?, ?, 'open', ?, ?, ?)""",
                (u["id"], u["telegram_id"], _tg(admin), _tg(admin), now, now, now))
            await conn.commit()
            thread_id = cur.lastrowid
    finally:
        await conn.close()
    data = await _bot("POST", "/admin-support/reply", {"thread_id": int(thread_id), "text": text, "admin_telegram_id": _tg(admin)}, 30)
    if not data.get("ok"):
        raise HTTPException(409, "Бот не смог отправить сообщение: " + str(data.get("reason") or "ошибка"))
    await _audit(admin, "user.message", user_id, text[:200])
    return {"ok": True, "thread_id": thread_id}


# ---------- списки: ключи и зависшие оплаты ----------

KEY_FILTERS = {
    "active": f"k.expires_at > datetime('now') AND NOT {DRAFT}",
    "expiring": "k.expires_at > datetime('now') AND k.expires_at <= datetime('now', '+3 days')",
    "trial": f"k.expires_at > datetime('now') AND {TRIAL_KEY}",
    "draft": DRAFT,
    "expired": "k.expires_at <= datetime('now')",
    "all": "1 = 1",
}


@router.get("/keys")
async def keys_list(status: str = "active", q: str = "", offset: int = 0, limit: int = 40, admin=Depends(auth.current_admin)):
    where = KEY_FILTERS.get(status, KEY_FILTERS["active"])
    args = []
    if q.strip():
        qq = q.strip().lstrip("@#")
        num = int(qq) if qq.isdigit() else -1
        where += " AND (k.id = ? OR u.telegram_id = ? OR u.username LIKE ? OR k.custom_name LIKE ?)"
        args += [num, num, f"%{qq}%", f"%{qq}%"]
    conn = await db.get_db()
    try:
        base = "FROM vpn_keys k JOIN users u ON u.id = k.user_id LEFT JOIN tariffs t ON t.id = k.tariff_id LEFT JOIN servers s ON s.id = k.server_id"
        total = await _scalar(conn, f"SELECT COUNT(*) {base} WHERE {where}", args)
        rows = await _rows(conn, f"""
            SELECT k.id, k.user_id, k.custom_name, k.expires_at, u.username, u.first_name, u.telegram_id, t.name AS tariff_name,
                   s.name AS server_name, {TRIAL_KEY} AS is_trial,
                   CASE WHEN {DRAFT} THEN 'draft' WHEN k.expires_at > datetime('now') THEN 'active' ELSE 'expired' END AS status
            {base} WHERE {where} ORDER BY k.expires_at {'DESC' if status in ('expired', 'all') else 'ASC'} LIMIT ? OFFSET ?""",
            (*args, max(1, min(limit, 200)), max(0, offset)))
        counts = {k: await _scalar(conn, f"SELECT COUNT(*) FROM vpn_keys k WHERE {v}") for k, v in KEY_FILTERS.items()}
        counts["disabled"] = 0
        return {"total": total, "keys": rows, "counts": counts}
    finally:
        await conn.close()


@router.get("/payments/stuck")
async def payments_stuck(admin=Depends(auth.current_admin)):
    conn = await db.get_db()
    try:
        items = await _stuck(conn)
    finally:
        await conn.close()
    for p in items:
        if p["key_draft"]:
            p["reason"] = f"ключ #{p['vpn_key_id']} остался черновиком"
            p["fixable"] = True
        else:
            p["reason"] = f"заказ не завершён ({p['fulfillment_status']})" + (f": {p['fulfillment_last_error'][:120]}" if p["fulfillment_last_error"] else "")
            p["fixable"] = p["purpose"] == "key_purchase" and not p["vpn_key_id"]
    return {"items": items}


@router.post("/payments/{order_id}/complete")
async def payment_complete(order_id: str, admin=Depends(auth.current_admin)):
    conn = await db.get_db()
    try:
        p = await (await conn.execute("""SELECT p.user_id, p.purpose, p.status, p.vpn_key_id, u.telegram_id FROM payments p
                                         JOIN users u ON u.id = p.user_id WHERE p.order_id = ?""", (order_id,))).fetchone()
    finally:
        await conn.close()
    if not p or p["status"] != "paid":
        raise HTTPException(404, "Оплаченный заказ не найден")
    if p["purpose"] not in ("key_purchase", "trial"):
        raise HTTPException(409, "Этот заказ доделать автоматически нельзя — напиши разработчику")
    data = await _bot("POST", "/mognu-admin/fix-order", {"order_id": order_id, "telegram_id": p["telegram_id"]}, 90)
    await _audit(admin, "payment.complete", p["user_id"], f"заказ {order_id}: {data.get('status')} {data.get('error_code') or ''}")
    if not data.get("ok"):
        raise HTTPException(400, f"Бот не смог: {data.get('error_code') or data.get('reason') or data.get('status')}")
    return {"ok": True, "message": f"Заказ {order_id}: {data.get('status')}"}


# ---------- серверы и тарифы ----------

@router.get("/servers")
async def servers(admin=Depends(auth.current_admin)):
    conn = await db.get_db()
    try:
        out = []
        for s in await _rows(conn, """SELECT s.id, s.name, s.is_active, s.panel_version, h.status, h.checked_at, h.up_since
                                      FROM servers s LEFT JOIN server_health h ON h.server_id = s.id ORDER BY s.id"""):
            s["keys_active"] = await _scalar(conn, "SELECT COUNT(*) FROM vpn_keys WHERE server_id = ? AND expires_at > datetime('now')", (s["id"],))
            s["keys_total"] = await _scalar(conn, "SELECT COUNT(*) FROM vpn_keys WHERE server_id = ?", (s["id"],))
            s["traffic_today"] = await _scalar(conn, """SELECT COALESCE(SUM(MAX(0, h1.traffic_used - COALESCE(h0.traffic_used, 0))), 0)
                FROM traffic_history h1 JOIN vpn_keys k ON k.id = h1.key_id
                LEFT JOIN traffic_history h0 ON h0.key_id = h1.key_id AND h0.snapshot_date = date(h1.snapshot_date, '-1 day')
                WHERE k.server_id = ? AND h1.snapshot_date = (SELECT MAX(snapshot_date) FROM traffic_history)""", (s["id"],))
            s["health"] = {"ok": None if not s["status"] or s["status"] == "unknown" else s["status"] == "up",
                           "checked_at": s.pop("checked_at"), "up_since": s.pop("up_since"), "status": s.pop("status")}
            s["locations"] = await _rows(conn, "SELECT inbound_id, name, status, checked_at FROM location_health WHERE server_id = ? ORDER BY sort, inbound_id", (s["id"],))
            out.append(s)
        return {"servers": out}
    finally:
        await conn.close()


@router.get("/tariffs")
async def tariffs(admin=Depends(auth.current_admin)):
    conn = await db.get_db()
    try:
        trial_ids = {r["tariff_id"] for r in await _rows(conn, "SELECT tariff_id FROM trial_offers WHERE tariff_id IS NOT NULL")}
        groups = await _rows(conn, "SELECT id, name FROM tariff_groups ORDER BY sort_order, id")
        rows = await _rows(conn, """SELECT t.id, t.name, t.duration_days, t.price_minor, t.is_active, t.group_id, t.max_ips AS devices,
                                           t.traffic_limit_gb, t.display_order,
                                           (SELECT COUNT(*) FROM payments p WHERE p.tariff_id = t.id AND p.status = 'paid'
                                              AND p.payable_amount_minor > 0 AND p.paid_at >= datetime('now', '-30 days')) AS sold_30d
                                    FROM tariffs t WHERE COALESCE(t.system_type, '') = '' ORDER BY t.display_order, t.duration_days""")
        for t in rows:
            t["is_trial"] = t["id"] in trial_ids
        rows.sort(key=lambda t: t["is_trial"])  # пробный — последним: он не продаётся
        return {"groups": groups, "tariffs": rows}
    finally:
        await conn.close()


class TariffIn(BaseModel):
    name: str
    price_minor: int
    is_active: bool


@router.post("/tariffs/{tariff_id}")
async def tariff_update(tariff_id: int, payload: TariffIn, admin=Depends(auth.current_admin)):
    name = payload.name.strip()
    if not name or len(name) > 60:
        raise HTTPException(400, "Название от 1 до 60 символов")
    if not 0 <= payload.price_minor <= 1_000_000_00:
        raise HTTPException(400, "Цена от 0 до 1 000 000 ₽")
    conn = await db.get_db()
    try:
        t = await (await conn.execute("SELECT * FROM tariffs WHERE id = ? AND COALESCE(system_type, '') = ''", (tariff_id,))).fetchone()
        if not t:
            raise HTTPException(404, "Тариф не найден")
        is_trial = await _scalar(conn, "SELECT 1 FROM trial_offers WHERE tariff_id = ?", (tariff_id,))
        active = int(t["is_active"]) if is_trial else int(payload.is_active)  # пробный тариф не продаётся — не включаем
        if not active and not is_trial and not await _scalar(
                conn, "SELECT COUNT(*) FROM tariffs WHERE is_active = 1 AND id != ? AND COALESCE(system_type, '') = ''", (tariff_id,)):
            raise HTTPException(409, "Это последний тариф в продаже — без него купить подписку будет нельзя")
        await conn.execute("UPDATE tariffs SET name = ?, price_minor = ?, is_active = ? WHERE id = ?",
                           (name, payload.price_minor, active, tariff_id))
        await conn.commit()
    finally:
        await conn.close()
    await _audit(admin, "tariff.update", None,
                 f"«{t['name']}»: {t['price_minor'] / 100:.0f} ₽ → {payload.price_minor / 100:.0f} ₽"
                 + (f", название «{name}»" if name != t["name"] else "") + ("" if active == t["is_active"] else (", в продаже" if active else ", скрыт")))
    return {"ok": True}


# ---------- настройки и новости ----------

@router.get("/settings")
async def settings_get(admin=Depends(auth.current_admin)):
    conn = await db.get_db()
    try:
        vals = {r["key"]: r["value"] for r in await _rows(conn, f"SELECT key, value FROM settings WHERE key IN ({','.join('?' * len(SETTINGS))})", tuple(SETTINGS))}
    finally:
        await conn.close()
    items = []
    for key, (group, label, kind, hint) in SETTINGS.items():
        v = vals.get(key)
        items.append({"key": key, "group": group, "label": label, "type": kind, "hint": hint,
                      "value": (str(v).strip() in ("1", "true", "True")) if kind == "bool" else v})
    return {"items": items}


class SettingIn(BaseModel):
    key: str
    value: object = None


@router.post("/settings")
async def settings_set(payload: SettingIn, admin=Depends(auth.current_admin)):
    meta = SETTINGS.get(payload.key)
    if not meta:
        raise HTTPException(400, "Эту настройку из админки менять нельзя")
    if meta[2] == "bool":
        value = "1" if payload.value in (True, 1, "1", "true") else "0"
    else:
        try:
            n = int(float(str(payload.value).strip()))
        except ValueError:
            raise HTTPException(400, "Нужно целое число")
        lo, hi = (1, 100) if "percent" in payload.key else NUMBER_RANGE
        if not lo <= n <= hi:
            raise HTTPException(400, f"Число от {lo} до {hi}")
        value = str(n)
    conn = await db.get_db()
    try:
        old = await _scalar(conn, "SELECT value FROM settings WHERE key = ?", (payload.key,))
        await conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (payload.key, value))
        await conn.commit()
    finally:
        await conn.close()
    await _audit(admin, "setting.update", None, f"{meta[1]}: {old} → {value}")
    return {"ok": True, "value": value}


@router.get("/news")
async def news_list(admin=Depends(auth.current_admin)):
    conn = await db.get_db()
    try:
        rows = await _rows(conn, "SELECT id, text, created_at, is_active FROM news ORDER BY id DESC LIMIT 50")
    except Exception:
        rows = []
    finally:
        await conn.close()
    return {"items": rows}


class NewsIn(BaseModel):
    text: str


@router.post("/news")
async def news_create(payload: NewsIn, admin=Depends(auth.current_admin)):
    text = payload.text.strip()
    if not text or len(text) > 2000:
        raise HTTPException(400, "Текст от 1 до 2000 символов")
    conn = await db.get_db()
    try:
        await conn.execute("CREATE TABLE IF NOT EXISTS news (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, "
                           "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, is_active INTEGER DEFAULT 1)")
        await conn.execute("INSERT INTO news (text, created_at, is_active) VALUES (?, ?, 1)", (text, _now()))
        await conn.commit()
    finally:
        await conn.close()
    await _audit(admin, "news.create", None, text[:200])
    return {"ok": True}


@router.post("/news/{news_id}/delete")
async def news_delete(news_id: int, admin=Depends(auth.current_admin)):
    conn = await db.get_db()
    try:
        await conn.execute("UPDATE news SET is_active = 0 WHERE id = ?", (news_id,))
        await conn.commit()
    finally:
        await conn.close()
    await _audit(admin, "news.delete", None, f"#{news_id}")
    return {"ok": True}


# ---------- рассылки ----------

@router.get("/broadcast/segments")
async def broadcast_segments(admin=Depends(auth.current_admin)):
    conn = await db.get_db()
    try:
        return {"counts": {k: await _scalar(conn, f"SELECT COUNT(*) FROM users u WHERE {REACHABLE} AND ({v})") for k, v in SEGMENTS.items()}}
    finally:
        await conn.close()


class BroadcastIn(BaseModel):
    segment: str
    text: str
    test: bool = False
    button_text: str = ""
    button_action: str = ""
    scheduled_at: str = ""


def _button(b):
    if b.get("button_text") and b.get("button_action") in BUTTONS:
        return (b["button_text"][:40], BUTTONS[b["button_action"]])
    return None


@router.post("/broadcast/send")
async def broadcast_send(payload: BroadcastIn, admin=Depends(auth.current_admin)):
    text = payload.text.strip()
    if payload.segment not in SEGMENTS:
        raise HTTPException(400, "Неизвестный сегмент")
    if not text or len(text) > 4000:
        raise HTTPException(400, "Текст от 1 до 4000 символов")
    if payload.button_action and payload.button_action not in BUTTONS:
        raise HTTPException(400, "Неизвестная кнопка")
    if payload.test:
        ok, _ = await _telegram(_tg(admin), text, _button(payload.dict()))
        if not ok:
            raise HTTPException(400, "Telegram не принял сообщение — проверь разметку")
        return {"ok": True, "test": True}
    when = None
    if payload.scheduled_at:
        try:
            when = datetime.fromisoformat(payload.scheduled_at.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            raise HTTPException(400, "Неверное время")
        if when < datetime.now(timezone.utc) - timedelta(minutes=1):
            raise HTTPException(400, "Время уже прошло")
    conn = await db.get_db()
    try:
        await _ensure(conn)
        if await _scalar(conn, "SELECT 1 FROM pamir_broadcasts WHERE status = 'sending'"):
            raise HTTPException(409, "Предыдущая рассылка ещё идёт — дождись её окончания")
        total = await _scalar(conn, f"SELECT COUNT(*) FROM users u WHERE {REACHABLE} AND ({SEGMENTS[payload.segment]})")
        cur = await conn.execute(
            """INSERT INTO pamir_broadcasts (created_at, admin_tg, segment, text, button_text, button_action, scheduled_at, status, total)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'scheduled', ?)""",
            (_now(), _tg(admin), payload.segment, text, payload.button_text.strip()[:40], payload.button_action,
             (when or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S"), total))
        await conn.commit()
        bid = cur.lastrowid
    finally:
        await conn.close()
    await _audit(admin, "broadcast.send", None, f"#{bid} {payload.segment}, {total} чел." + (f", на {when:%d.%m %H:%M} UTC" if when else ""))
    _start_worker()
    return {"ok": True, "id": bid, "total": total, "scheduled": bool(when)}


@router.get("/broadcast/history")
async def broadcast_history(admin=Depends(auth.current_admin)):
    _start_worker()
    conn = await db.get_db()
    try:
        await _ensure(conn)
        return {"items": await _rows(conn, "SELECT id, segment, text, status, total, sent, failed, created_at, scheduled_at, finished_at "
                                           "FROM pamir_broadcasts ORDER BY id DESC LIMIT 30")}
    finally:
        await conn.close()


@router.post("/broadcast/{bid}/cancel")
async def broadcast_cancel(bid: int, admin=Depends(auth.current_admin)):
    conn = await db.get_db()
    try:
        await _ensure(conn)
        cur = await conn.execute("UPDATE pamir_broadcasts SET status = 'canceled' WHERE id = ? AND status = 'scheduled'", (bid,))
        await conn.commit()
        if not cur.rowcount:
            raise HTTPException(409, "Рассылку уже нельзя отменить")
    finally:
        await conn.close()
    await _audit(admin, "broadcast.cancel", None, f"#{bid}")
    return {"ok": True}


_worker = None


def _start_worker():
    global _worker
    if _worker is None or _worker.done():
        _worker = asyncio.get_running_loop().create_task(_broadcast_loop())


async def _broadcast_loop():
    """Раз в 20 секунд: забрать подошедшую рассылку и отправить (не больше ~20 сообщений в секунду)."""
    conn = await db.get_db()
    try:
        await _ensure(conn)
        # Рассылка, которую оборвал перезапуск бэкенда, — помечаем, чтобы не слать повторно
        await conn.execute("UPDATE pamir_broadcasts SET status = 'failed', finished_at = ? WHERE status = 'sending'", (_now(),))
        await conn.commit()
    finally:
        await conn.close()
    while True:
        try:
            await _broadcast_tick()
        except Exception:
            pass
        await asyncio.sleep(20)


async def _broadcast_tick():
    conn = await db.get_db()
    try:
        b = await (await conn.execute("SELECT * FROM pamir_broadcasts WHERE status = 'scheduled' AND scheduled_at <= ? ORDER BY id LIMIT 1", (_now(),))).fetchone()
        if not b:
            return
        b = dict(b)
        cur = await conn.execute("UPDATE pamir_broadcasts SET status = 'sending' WHERE id = ? AND status = 'scheduled'", (b["id"],))
        await conn.commit()
        if not cur.rowcount:
            return
        targets = await _rows(conn, f"SELECT u.id, u.telegram_id FROM users u WHERE {REACHABLE} AND ({SEGMENTS[b['segment']]})")
        await conn.execute("UPDATE pamir_broadcasts SET total = ? WHERE id = ?", (len(targets), b["id"]))
        # Та же новость — в уведомления приложений и кабинета, как у старой рассылки
        plain = re.sub(r"<[^>]+>", "", b["text"])
        await conn.executemany("INSERT INTO app_notifications (user_id, title, body) VALUES (?, ?, ?)",
                               [(t["id"], "Mognu VPN", plain) for t in targets])
        await conn.commit()
    finally:
        await conn.close()
    sent = failed = 0
    button = _button(b)
    for i, t in enumerate(targets):
        try:
            ok, _ = await _telegram(t["telegram_id"], b["text"], button)
        except Exception:
            ok = False
        sent, failed = sent + ok, failed + (not ok)
        await asyncio.sleep(0.05)
        if i % 25 == 24 or i == len(targets) - 1:
            conn = await db.get_db()
            try:
                st = await _scalar(conn, "SELECT status FROM pamir_broadcasts WHERE id = ?", (b["id"],))
                await conn.execute("UPDATE pamir_broadcasts SET sent = ?, failed = ? WHERE id = ?", (sent, failed, b["id"]))
                await conn.commit()
            finally:
                await conn.close()
            if st != "sending":
                break
    conn = await db.get_db()
    try:
        await conn.execute("UPDATE pamir_broadcasts SET status = 'done', sent = ?, failed = ?, finished_at = ? WHERE id = ? AND status = 'sending'",
                           (sent, failed, _now(), b["id"]))
        await conn.commit()
    finally:
        await conn.close()


# ---------- журнал ----------

@router.get("/audit")
async def audit(offset: int = 0, limit: int = 50, admin=Depends(auth.current_admin)):
    conn = await db.get_db()
    try:
        await _ensure(conn)
        total = await _scalar(conn, "SELECT COUNT(*) FROM pamir_admin_audit")
        rows = await _rows(conn, """SELECT a.at, a.action, a.user_id, a.details, a.admin_tg, u.username, u.first_name
                                    FROM pamir_admin_audit a LEFT JOIN users u ON u.telegram_id = a.admin_tg
                                    ORDER BY a.id DESC LIMIT ? OFFSET ?""", (max(1, min(limit, 200)), max(0, offset)))
        for r in rows:
            r["admin"] = ("@" + r["username"]) if r.get("username") else (r.get("first_name") or f"tg {r['admin_tg']}")
        return {"total": total, "items": rows}
    finally:
        await conn.close()



# ---------- откуда заходят и платят ----------
# Бэкенд отмечает, с чего человек пользуется сервисом: Android-приложение и программа для Windows узнаются по
# User-Agent, кабинет присылает X-Mognu-Client (telegram — внутри Telegram, web — браузер). Оплаты, созданные через
# бэкенд, получают ту же отметку; оплата без отметки после начала учёта — значит, из Telegram-бота.

PAY_PATH = re.compile(r"^(/api)?/topup/(purchase|renew|topup|buy-device-slot|card-bind/start)$")
_seen = {}
_uid_by_tg = {}


def _client_of(request: Request):
    ua = request.headers.get("user-agent", "")
    m = re.search(r"(?:PamirVPN|Mognu)-Android/([\w.]+)", ua)
    if m:
        return "android", m.group(1)
    m = re.search(r"Mognu-Desktop/?\s*([\w.]+)?", ua)
    if m:
        return "windows", m.group(1) or ""
    x = request.headers.get("x-mognu-client", "")
    if x == "telegram":
        return "telegram", ""
    if x == "web":
        return ("web_phone" if re.search(r"Mobile|Android|iPhone|iPad", ua) else "web_pc"), ""
    return None, ""


async def _user_id_of(request: Request):
    authz = request.headers.get("authorization", "")
    if not authz.startswith("Bearer "):
        return None
    try:
        p = auth.decode_app_token(authz[7:].strip())
    except Exception:
        return None
    if not isinstance(p, dict) or p.get("is_admin"):
        return None
    for k in ("user_id", "uid", "id"):
        if str(p.get(k, "")).isdigit():
            return int(p[k])
    sub = str(p.get("sub", ""))
    if sub.split(":")[-1].isdigit() and not sub.startswith(("admin", "tg")):
        return int(sub.split(":")[-1])
    tg = p.get("tg_id") or p.get("telegram_id")
    if tg:
        if tg not in _uid_by_tg:
            conn = await db.get_db()
            try:
                _uid_by_tg[tg] = await _scalar(conn, "SELECT id FROM users WHERE telegram_id = ?", (int(tg),))
            finally:
                await conn.close()
        return _uid_by_tg[tg]
    return None


async def _remember(uid, client, version, order_id=None):
    now = _now()
    conn = await db.get_db()
    try:
        await _ensure(conn)
        await conn.execute("""INSERT INTO pamir_user_clients (user_id, client, version, first_seen, last_seen) VALUES (?, ?, ?, ?, ?)
                              ON CONFLICT(user_id, client) DO UPDATE SET version = COALESCE(NULLIF(excluded.version, ''), version),
                              last_seen = excluded.last_seen""", (uid, client, version, now, now))
        if order_id:
            await conn.execute("INSERT OR IGNORE INTO pamir_payment_clients (order_id, user_id, client, created_at) VALUES (?, ?, ?, ?)",
                               (order_id, uid, client, now))
        await conn.commit()
    finally:
        await conn.close()


def track_clients(app):
    """Подключается в main.py: отметка клиента на каждом запросе вошедшего человека (не чаще раза в 10 минут) и на оплатах.
    Заодно с первым же запросом запускает фоновые задачи админки: рассылки по расписанию и замеры онлайна
    (без startup-событий — их нет в новых версиях FastAPI)."""
    @app.middleware("http")
    async def _mognu_track_clients(request: Request, call_next):
        if _online_task is None or _online_task.done():
            try:
                await _start_background()
            except Exception:
                pass
        response = await call_next(request)
        try:
            client, version = _client_of(request)
            if not client or response.status_code >= 400:
                return response
            uid = await _user_id_of(request)
            if not uid:
                return response
            order_id = None
            if request.method == "POST" and PAY_PATH.match(request.url.path):
                body = b"".join([chunk async for chunk in response.body_iterator])
                response = Response(content=body, status_code=response.status_code, headers=dict(response.headers),
                                    media_type=response.media_type)
                try:
                    data = json.loads(body or b"{}")
                    order_id = data.get("order_id") if isinstance(data, dict) else None
                except ValueError:
                    pass
            key = (uid, client)
            if order_id or time.monotonic() - _seen.get(key, -1e9) > 600:
                _seen[key] = time.monotonic()
                asyncio.get_running_loop().create_task(_remember(uid, client, version, str(order_id) if order_id else None))
        except Exception:
            pass
        return response


@router.get("/clients")
async def clients(users: str = "", orders: str = "", admin=Depends(auth.current_admin)):
    uids = [int(x) for x in users.split(",") if x.strip().isdigit()][:300]
    oids = [x.strip() for x in orders.split(",") if x.strip()][:300]
    conn = await db.get_db()
    try:
        await _ensure(conn)
        since = await _scalar(conn, "SELECT value FROM pamir_admin_meta WHERE key = 'clients_since'")
        out_u, out_o = {}, {}
        if uids:
            for r in await _rows(conn, f"SELECT user_id, client, version, last_seen FROM pamir_user_clients WHERE user_id IN ({','.join('?' * len(uids))}) ORDER BY last_seen DESC", uids):
                out_u.setdefault(str(r["user_id"]), []).append({"client": r["client"], "version": r["version"], "last_seen": r["last_seen"]})
        if oids:
            known = {r["order_id"]: r["client"] for r in await _rows(conn, f"SELECT order_id, client FROM pamir_payment_clients WHERE order_id IN ({','.join('?' * len(oids))})", oids)}
            for r in await _rows(conn, f"SELECT order_id, payment_type, COALESCE(created_at, paid_at) AS at FROM payments WHERE order_id IN ({','.join('?' * len(oids))})", oids):
                if r["order_id"] in known:
                    out_o[r["order_id"]] = known[r["order_id"]]
                elif since and r["at"] and str(r["at"])[:19] >= since and r["payment_type"] != "trial":
                    out_o[r["order_id"]] = "bot"
        tags = {}
        if uids:
            for r in await _rows(conn, f"SELECT user_id, tags FROM pamir_user_notes WHERE user_id IN ({','.join('?' * len(uids))}) AND COALESCE(tags, '') != ''", uids):
                tags[str(r["user_id"])] = [t for t in r["tags"].split(",") if t]
        return {"users": out_u, "orders": out_o, "since": since, "tags": tags}
    finally:
        await conn.close()


# ---------- фон: замеры онлайна ----------

_online_task = None


async def _start_background():
    global _online_task
    _start_worker()
    if _online_task is None or _online_task.done():
        _online_task = asyncio.get_running_loop().create_task(_online_loop())


async def _online_loop():
    """Каждые 5 минут — сколько людей онлайн на каждой локации (по данным бота); храним 30 дней."""
    while True:
        try:
            data = await _bot("GET", "/admin-online-list", None, 30)
            counts = {}
            for e in data.get("entries") or []:
                loc = e.get("server_name") or e.get("location") or "—"
                counts[loc] = counts.get(loc, 0) + 1
            if data.get("ok", True) is not False:
                now = _now()
                conn = await db.get_db()
                try:
                    await _ensure(conn)
                    rows = [(now, loc, n) for loc, n in counts.items()] or [(now, "—", 0)]
                    await conn.executemany("INSERT INTO pamir_online_samples (at, location, n) VALUES (?, ?, ?)", rows)
                    await conn.execute("DELETE FROM pamir_online_samples WHERE at < datetime('now', '-30 days')")
                    await conn.commit()
                finally:
                    await conn.close()
        except Exception:
            pass
        await asyncio.sleep(300)


@router.get("/online/history")
async def online_history(hours: int = 24, admin=Depends(auth.current_admin)):
    """Онлайн по часам: среднее и пик за каждый час (по московскому времени), по локациям."""
    hours = max(1, min(hours, 24 * 30))
    _start_worker()
    conn = await db.get_db()
    try:
        await _ensure(conn)
        rows = await _rows(conn, f"""
            SELECT strftime('%Y-%m-%d %H:00', at, '{MSK}') AS hour, at, location, n FROM pamir_online_samples
            WHERE at >= datetime('now', ?) ORDER BY at""", (f"-{hours} hours",))
    finally:
        await conn.close()
    per_sample, locs = {}, {}
    for r in rows:
        sm = per_sample.setdefault(r["at"], {"hour": r["hour"], "total": 0})
        if r["location"] != "—":
            sm["total"] += r["n"]
            sm[r["location"]] = r["n"]
            locs[r["location"]] = max(locs.get(r["location"], 0), r["n"])
    hours_out = {}
    for sm in per_sample.values():
        h = hours_out.setdefault(sm["hour"], {"hour": sm["hour"], "samples": 0, "sum": 0, "peak": 0})
        h["samples"] += 1
        h["sum"] += sm["total"]
        h["peak"] = max(h["peak"], sm["total"])
    series = [{"hour": h["hour"], "avg": round(h["sum"] / h["samples"], 1), "peak": h["peak"]} for h in sorted(hours_out.values(), key=lambda x: x["hour"])]
    by_hour_of_day = {}
    for h in series:
        by_hour_of_day.setdefault(h["hour"][11:13], []).append(h["avg"])
    busiest = max(by_hour_of_day.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))[0] if by_hour_of_day else None
    return {"series": series, "locations_peak": dict(sorted(locs.items(), key=lambda kv: -kv[1])),
            "busiest_hour": busiest, "samples": len(per_sample)}


# ---------- удержание и прогноз ----------

@router.get("/retention")
async def retention(admin=Depends(auth.current_admin)):
    conn = await db.get_db()
    try:
        # Когорты по месяцу первой оплаты: сколько из них заплатили ещё раз
        cohorts = await _rows(conn, f"""
            WITH firsts AS (SELECT p.user_id, MIN(p.paid_at) AS first_at FROM payments p WHERE {PAID} GROUP BY p.user_id)
            SELECT strftime('%Y-%m', f.first_at, '{MSK}') AS month, COUNT(*) AS payers,
                   SUM(EXISTS (SELECT 1 FROM payments p WHERE p.user_id = f.user_id AND {PAID} AND p.paid_at > f.first_at)) AS repeat
            FROM firsts f WHERE f.first_at >= datetime('now', '-12 months') GROUP BY 1 ORDER BY 1""")
        # Новые пользователи по месяцам: взяли пробный → оплатили
        trials = await _rows(conn, f"""
            SELECT strftime('%Y-%m', u.created_at, '{MSK}') AS month, COUNT(*) AS users, SUM(u.used_trial = 1) AS trial,
                   SUM(EXISTS (SELECT 1 FROM payments p WHERE p.user_id = u.id AND {PAID})) AS paid
            FROM users u WHERE u.created_at >= datetime('now', '-12 months') GROUP BY 1 ORDER BY 1""")
        # Продлили после первого месяца: первая оплата 35–180 дней назад, вторая — в течение 45 дней
        r = await (await conn.execute(f"""
            WITH firsts AS (SELECT p.user_id, MIN(p.paid_at) AS first_at FROM payments p WHERE {PAID} GROUP BY p.user_id)
            SELECT COUNT(*) AS base,
                   SUM(EXISTS (SELECT 1 FROM payments p WHERE p.user_id = f.user_id AND {PAID}
                               AND p.paid_at > f.first_at AND p.paid_at <= datetime(f.first_at, '+45 days'))) AS renewed
            FROM firsts f WHERE f.first_at <= datetime('now', '-35 days') AND f.first_at >= datetime('now', '-180 days')""")).fetchone()
        renew_rate = (r["renewed"] or 0) / r["base"] if r["base"] else None
        # Пробный → оплата за всё время (для прогноза по пробным)
        r2 = await (await conn.execute(f"""SELECT SUM(u.used_trial = 1) AS t,
                SUM(u.used_trial = 1 AND EXISTS (SELECT 1 FROM payments p WHERE p.user_id = u.id AND {PAID})) AS p
            FROM users u WHERE u.created_at <= datetime('now', '-7 days')""")).fetchone()
        trial_rate = (r2["p"] or 0) / r2["t"] if r2["t"] else None
        avg_renew = await _scalar(conn, f"""SELECT AVG(p.payable_amount_minor) FROM payments p WHERE {PAID}
                                           AND p.paid_at >= datetime('now', '-90 days') AND p.purpose = 'key_renewal'""") \
            or await _scalar(conn, f"SELECT AVG(p.payable_amount_minor) FROM payments p WHERE {PAID}") or 0
        avg_first = await _scalar(conn, f"""SELECT AVG(p.payable_amount_minor) FROM payments p WHERE {PAID}
                                           AND p.paid_at >= datetime('now', '-90 days') AND p.purpose = 'key_purchase'""") or avg_renew
        # Прогноз на 7 дней: у кого истекает подписка — сколько продлят и на какую сумму
        days = await _rows(conn, f"""
            SELECT date(k.expires_at, '{MSK}') AS day, SUM(NOT {TRIAL_KEY}) AS paid_keys, SUM({TRIAL_KEY}) AS trial_keys
            FROM vpn_keys k WHERE k.expires_at > datetime('now') AND k.expires_at <= datetime('now', '+7 days') AND NOT {DRAFT}
            GROUP BY 1 ORDER BY 1""")
        exp_total = 0.0
        for d in days:
            d["expected_minor"] = round((d["paid_keys"] or 0) * (renew_rate or 0) * avg_renew + (d["trial_keys"] or 0) * (trial_rate or 0) * avg_first)
            exp_total += d["expected_minor"]
        active_paid = await _scalar(conn, f"""SELECT COUNT(DISTINCT k.user_id) FROM vpn_keys k
                                             WHERE k.expires_at > datetime('now') AND NOT {TRIAL_KEY}""")
        lost_30d = await _scalar(conn, f"""SELECT COUNT(*) FROM users u WHERE {EVER_PAID}
            AND NOT {ACTIVE} AND (SELECT MAX(k.expires_at) FROM vpn_keys k WHERE k.user_id = u.id) >= datetime('now', '-30 days')""")
        new_payers_30d = await _scalar(conn, f"""SELECT COUNT(*) FROM (SELECT p.user_id, MIN(p.paid_at) AS f FROM payments p
                                                WHERE {PAID} GROUP BY p.user_id) WHERE f >= datetime('now', '-30 days')""")
        return {"cohorts": cohorts, "trials": trials, "renew_rate": renew_rate, "renew_base": r["base"], "trial_rate": trial_rate,
                "avg_renew_minor": round(avg_renew), "forecast": days, "forecast_total_minor": round(exp_total),
                "active_paid": active_paid, "lost_30d": lost_30d, "new_payers_30d": new_payers_30d}
    finally:
        await conn.close()


# ---------- заметки и метки ----------

TAG_RE = re.compile(r"^[\w\- ёЁ]{1,24}$")


class NoteIn(BaseModel):
    note: str = ""
    tags: list = []


@router.post("/users/{user_id}/note")
async def user_note(user_id: int, payload: NoteIn, admin=Depends(auth.current_admin)):
    note = payload.note.strip()[:2000]
    tags = []
    for t in payload.tags[:10]:
        t = str(t).strip().lower()
        if t and TAG_RE.match(t) and t not in tags:
            tags.append(t)
    conn = await db.get_db()
    try:
        await _ensure(conn)
        await _user(conn, user_id)
        await conn.execute("""INSERT INTO pamir_user_notes (user_id, note, tags, updated_at, admin_tg) VALUES (?, ?, ?, ?, ?)
                              ON CONFLICT(user_id) DO UPDATE SET note = excluded.note, tags = excluded.tags,
                              updated_at = excluded.updated_at, admin_tg = excluded.admin_tg""",
                           (user_id, note, ",".join(tags), _now(), _tg(admin)))
        await conn.commit()
    finally:
        await conn.close()
    await _audit(admin, "user.note", user_id, (", ".join(tags) + " · " if tags else "") + note[:150])
    return {"ok": True, "tags": tags}


@router.get("/tags")
async def tags_list(admin=Depends(auth.current_admin)):
    conn = await db.get_db()
    try:
        await _ensure(conn)
        counts = {}
        for r in await _rows(conn, "SELECT tags FROM pamir_user_notes WHERE COALESCE(tags, '') != ''"):
            for t in r["tags"].split(","):
                if t:
                    counts[t] = counts.get(t, 0) + 1
        return {"tags": [{"tag": t, "count": n} for t, n in sorted(counts.items(), key=lambda kv: -kv[1])]}
    finally:
        await conn.close()


@router.get("/users/by-tag")
async def users_by_tag(tag: str, admin=Depends(auth.current_admin)):
    tag = tag.strip().lower()
    conn = await db.get_db()
    try:
        await _ensure(conn)
        users = await _rows(conn, """SELECT u.id, u.telegram_id, u.username, u.first_name, u.last_name, u.email, u.created_at,
                                            u.personal_balance, u.is_banned, n.note
                                     FROM pamir_user_notes n JOIN users u ON u.id = n.user_id
                                     WHERE ',' || n.tags || ',' LIKE ? ORDER BY n.updated_at DESC LIMIT 500""", (f"%,{tag},%",))
        return {"total": len(users), "users": users}
    finally:
        await conn.close()


# ---------- массовые действия ----------

class BulkGiftIn(BaseModel):
    user_ids: list
    days: int
    notify: bool = True


class BulkMessageIn(BaseModel):
    user_ids: list
    text: str


def _ids(raw):
    ids = []
    for x in raw[:200]:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            pass
    if not ids:
        raise HTTPException(400, "Никто не выбран")
    return list(dict.fromkeys(ids))


@router.post("/bulk/gift")
async def bulk_gift(payload: BulkGiftIn, admin=Depends(auth.current_admin)):
    ids = _ids(payload.user_ids)
    done = skipped = 0
    for uid in ids:
        try:
            await user_gift(uid, GiftIn(days=payload.days, notify=payload.notify), admin)
            done += 1
        except HTTPException as e:
            if e.status_code == 400:
                raise
            skipped += 1
    return {"ok": True, "done": done, "skipped": skipped}


@router.post("/bulk/message")
async def bulk_message(payload: BulkMessageIn, admin=Depends(auth.current_admin)):
    ids = _ids(payload.user_ids)
    text = payload.text.strip()
    if not text or len(text) > 4000:
        raise HTTPException(400, "Текст от 1 до 4000 символов")
    conn = await db.get_db()
    try:
        users = await _rows(conn, f"SELECT id, telegram_id FROM users WHERE id IN ({','.join('?' * len(ids))})", ids)
    finally:
        await conn.close()
    sent = failed = 0
    for u in users:
        if (u["telegram_id"] or 0) <= 0:
            failed += 1
            continue
        try:
            ok, _ = await _telegram(u["telegram_id"], text)
        except Exception:
            ok = False
        sent, failed = sent + ok, failed + (not ok)
        await asyncio.sleep(0.05)
    await _audit(admin, "bulk.message", None, f"{sent} из {len(ids)}: {text[:150]}")
    return {"ok": True, "sent": sent, "failed": failed}


# ---------- ссылка подписки ----------

@router.get("/keys/{key_id}/sub-url")
async def key_sub_url(key_id: int, admin=Depends(auth.current_admin)):
    """Та же ссылка, что видит человек в приложении и кабинете (бот: /mini-app-api/keys). Просмотр пишется в журнал."""
    conn = await db.get_db()
    try:
        k = await (await conn.execute("SELECT k.user_id, u.telegram_id FROM vpn_keys k JOIN users u ON u.id = k.user_id WHERE k.id = ?", (key_id,))).fetchone()
    finally:
        await conn.close()
    if not k:
        raise HTTPException(404, "Ключ не найден")
    data = await _bot("GET", "/keys", {"telegram_id": k["telegram_id"]}, 20)
    for item in data.get("keys") or []:
        if str(item.get("id", item.get("key_id"))) == str(key_id) and str(item.get("subscription_url", "")).startswith("http"):
            await _audit(admin, "key.sub_url", k["user_id"], f"ключ #{key_id}")
            return {"url": item["subscription_url"]}
    raise HTTPException(404, "Бот не отдал ссылку для этого ключа (черновик или удалён)")


# ---------- подозрительное ----------

_devices_cache = {"at": 0.0, "data": None}
HEAVY_GB_WEEK = 300


async def _devices_scan(conn):
    """Устройства активных ключей (бот: /mini-app-api/devices), не чаще раза в 10 минут."""
    if _devices_cache["data"] is not None and time.monotonic() - _devices_cache["at"] < 600:
        return _devices_cache["data"]
    keys = await _rows(conn, f"""SELECT k.id, k.user_id, u.telegram_id, COALESCE(k.max_ips_override, ds.device_limit, t.max_ips) AS lim,
                                       {TRIAL_KEY} AS trial
                                FROM vpn_keys k JOIN users u ON u.id = k.user_id LEFT JOIN tariffs t ON t.id = k.tariff_id
                                LEFT JOIN key_device_slots ds ON ds.key_id = k.id
                                WHERE k.expires_at > datetime('now') AND NOT {DRAFT} AND u.telegram_id > 0 LIMIT 400""")
    out = []
    for k in keys:
        try:
            d = await _bot("GET", "/devices", {"telegram_id": k["telegram_id"], "key_id": k["id"]}, 10)
        except HTTPException:
            continue
        devs = d.get("devices") or d.get("items") or []
        ids = []
        for dv in devs:
            if isinstance(dv, dict):
                hw = dv.get("hwid") or dv.get("device_id") or dv.get("hw_id")
                label = " ".join(str(dv.get(x)) for x in ("device_model", "model", "device_os", "os") if dv.get(x))
                ids.append({"hwid": str(hw) if hw else None, "label": label})
        out.append({**k, "devices": ids})
    _devices_cache.update(at=time.monotonic(), data=out)
    return out


@router.get("/suspicious")
async def suspicious(admin=Depends(auth.current_admin)):
    conn = await db.get_db()
    try:
        async def users(ids):
            if not ids:
                return []
            return await _rows(conn, f"SELECT id, telegram_id, username, first_name, email FROM users WHERE id IN ({','.join('?' * len(ids))})", ids)
        # Трафик за 7 дней по снимкам бота
        heavy = await _rows(conn, f"""
            SELECT h.key_id, k.user_id, MAX(h.traffic_used) - MIN(h.traffic_used) AS week_bytes
            FROM traffic_history h JOIN vpn_keys k ON k.id = h.key_id
            WHERE h.snapshot_date >= date('now', '-7 days') GROUP BY h.key_id
            HAVING week_bytes >= ? ORDER BY week_bytes DESC LIMIT 30""", (HEAVY_GB_WEEK * 1_000_000_000,))
        # Пробный несколько раз
        trials = await _rows(conn, """SELECT user_id, COUNT(*) AS n, MAX(activated_at) AS last_at FROM trial_activations
                                      GROUP BY user_id HAVING n > 1 ORDER BY n DESC LIMIT 30""")
        try:
            scan = await _devices_scan(conn)
        except Exception:
            scan = []
        many = [{"key_id": k["id"], "user_id": k["user_id"], "devices": len(k["devices"]), "limit": k["lim"]}
                for k in scan if k["devices"] and (len(k["devices"]) > (k["lim"] or 1) or len(k["devices"]) >= 5)]
        by_hw = {}
        for k in scan:
            for dv in k["devices"]:
                if dv["hwid"]:
                    by_hw.setdefault(dv["hwid"], {"label": dv["label"], "keys": []})["keys"].append(
                        {"key_id": k["id"], "user_id": k["user_id"], "trial": bool(k["trial"])})
        shared = [{"label": v["label"], "keys": v["keys"]} for v in by_hw.values() if len({x["user_id"] for x in v["keys"]}) > 1]
        ids = {x["user_id"] for x in heavy + trials + many} | {kk["user_id"] for g in shared for kk in g["keys"]}
        people = {str(u["id"]): u for u in await users(list(ids))}
        return {"heavy": heavy, "heavy_gb_week": HEAVY_GB_WEEK, "repeat_trials": trials, "many_devices": many,
                "shared_devices": shared, "devices_checked": len(scan), "users": people}
    finally:
        await conn.close()
