"""Pamir: промокоды и аналитика для веб-админки (admin/promo.html, admin/analytics.html).

Ставится патчем patch_admin_extra.py как routers/pamir_admin_extra.py бэкенда кабинета.
Работает с базой бота напрямую (таблицы promo_codes, promo_link_visits, payments, users),
ничего в схеме не меняет. Ссылка с промокодом — штатная ботовая t.me/<bot>?start=pr_<КОД>.
Время в базе — UTC.
"""
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import auth
import db

router = APIRouter(prefix="/admin", tags=["admin"])

BOT_USERNAME = "pamirlink_bot"
CODE_RE = re.compile(r"^[A-Z0-9_-]{3,32}$")
# Автоматические коды бота: «последний шанс», колесо, купоны после оплаты и для ушедших.
AUTO_SOURCES = {
    "lastchance": "miniapp_lastchance:%",
    "wheel": "wheel:%",
    "auto": "auto_%",
}
# Реальные деньги: оплаченный заказ, к оплате > 0, не списание с баланса.
PAID = "p.status = 'paid' AND p.payable_amount_minor > 0 AND COALESCE(p.payment_type, '') != 'balance'"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def _columns(conn, table: str) -> set:
    try:
        cur = await conn.execute(f"PRAGMA table_info({table})")
        return {r[1] for r in await cur.fetchall()}
    except Exception:
        return set()


async def _scalar(conn, sql: str, args=()):
    cur = await conn.execute(sql, args)
    row = await cur.fetchone()
    return row[0] if row else None


async def _admin_user_id(conn, admin):
    """users.id администратора; current_admin отдаёт telegram_id (или словарь с ним)."""
    tg = admin.get("telegram_id") or admin.get("sub") if isinstance(admin, dict) else admin
    try:
        return await _scalar(conn, "SELECT id FROM users WHERE telegram_id = ?", (int(tg),))
    except Exception:
        return None


def _promo_out(r) -> dict:
    d = dict(r)
    d["link"] = f"https://t.me/{BOT_USERNAME}?start=pr_{d['code']}"
    exp = d.get("expires_at")
    d["expired"] = bool(exp and str(exp)[:19] < _now())
    lim = d.get("activation_limit")
    d["exhausted"] = bool(lim and d.get("usage_count", 0) >= lim)
    return d


# ---------- промокоды ----------

@router.get("/promo")
async def promo_list(kind: str = "manual", limit: int = 100, admin=Depends(auth.current_admin)):
    """kind: manual — созданные вручную (по умолчанию), lastchance / wheel / auto, all — все."""
    where, args = "1=1", []
    if kind == "manual":
        where = "pc.source = 'manual'"
    elif kind in AUTO_SOURCES:
        where, args = "pc.source LIKE ?", [AUTO_SOURCES[kind]]
    conn = await db.get_db()
    try:
        cur = await conn.execute(
            f"""
            SELECT pc.id, pc.type, pc.code, pc.discount_percent, pc.expires_at, pc.is_active,
                   pc.activation_limit, pc.usage_count, pc.source, pc.note, pc.created_at,
                   (SELECT COUNT(*) FROM promo_link_visits v WHERE v.promo_code_id = pc.id) AS link_visits,
                   (SELECT COUNT(*) FROM payments p WHERE p.promo_code_id = pc.id AND {PAID}) AS paid_orders,
                   (SELECT COALESCE(SUM(p.payable_amount_minor), 0) FROM payments p
                     WHERE p.promo_code_id = pc.id AND {PAID}) AS revenue_minor
            FROM promo_codes pc
            WHERE {where}
            ORDER BY pc.id DESC
            LIMIT ?
            """,
            (*args, max(1, min(limit, 500))),
        )
        items = [_promo_out(r) for r in await cur.fetchall()]
        # Сводка по группам за всё время: сколько выдано, сколько оплатили со скидкой.
        groups = {}
        for name, cond, cargs in [
            ("manual", "pc.source = 'manual'", ()),
            *[(k, "pc.source LIKE ?", (v,)) for k, v in AUTO_SOURCES.items()],
        ]:
            cur = await conn.execute(
                f"""
                SELECT COUNT(*) AS issued,
                       (SELECT COUNT(*) FROM payments p JOIN promo_codes pc ON pc.id = p.promo_code_id
                         WHERE {cond} AND {PAID}) AS paid_orders,
                       (SELECT COALESCE(SUM(p.payable_amount_minor), 0) FROM payments p
                         JOIN promo_codes pc ON pc.id = p.promo_code_id WHERE {cond} AND {PAID}) AS revenue_minor
                FROM promo_codes pc WHERE {cond}
                """,
                (*cargs, *cargs, *cargs),
            )
            groups[name] = dict(await cur.fetchone())
        return {"items": items, "groups": groups}
    finally:
        await conn.close()


class PromoIn(BaseModel):
    code: str = ""
    discount_percent: int
    days: int = 0                 # срок действия в днях; 0 — бессрочно
    activation_limit: int = 0     # сколько раз можно применить; 0 — без ограничения
    note: str = ""


@router.post("/promo")
async def promo_create(payload: PromoIn, admin=Depends(auth.current_admin)):
    if not 1 <= payload.discount_percent <= 100:
        raise HTTPException(400, "Скидка должна быть от 1 до 100%")
    if payload.days < 0 or payload.activation_limit < 0:
        raise HTTPException(400, "Срок и лимит не могут быть отрицательными")
    code = payload.code.strip().upper() or "PAMIR" + secrets.token_hex(3).upper()
    if not CODE_RE.match(code):
        raise HTTPException(400, "Код: 3–32 символа, латиница, цифры, «-» и «_»")
    expires = None
    if payload.days:
        expires = (datetime.now(timezone.utc) + timedelta(days=payload.days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = await db.get_db()
    try:
        if await _scalar(conn, "SELECT 1 FROM promo_codes WHERE code = ?", (code,)):
            raise HTTPException(409, "Такой код уже есть")
        admin_id = await _admin_user_id(conn, admin)
        now = _now()
        cur = await conn.execute(
            """
            INSERT INTO promo_codes (type, code, discount_percent, expires_at, is_active, activation_limit,
                                     usage_count, source, created_by_admin_id, note, created_at, updated_at)
            VALUES ('promo', ?, ?, ?, 1, ?, 0, 'manual', ?, ?, ?, ?)
            """,
            (code, payload.discount_percent, expires, payload.activation_limit or None,
             admin_id, payload.note.strip()[:200] or None, now, now),
        )
        await conn.commit()
        row = await (await conn.execute("SELECT * FROM promo_codes WHERE id = ?", (cur.lastrowid,))).fetchone()
        out = _promo_out(row)
        out.update(link_visits=0, paid_orders=0, revenue_minor=0)
        return out
    finally:
        await conn.close()


@router.post("/promo/{promo_id}/toggle")
async def promo_toggle(promo_id: int, admin=Depends(auth.current_admin)):
    conn = await db.get_db()
    try:
        cur = await conn.execute(
            "UPDATE promo_codes SET is_active = 1 - is_active, updated_at = ? WHERE id = ?",
            (_now(), promo_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Промокод не найден")
        await conn.commit()
        return {"id": promo_id, "is_active": await _scalar(conn, "SELECT is_active FROM promo_codes WHERE id = ?", (promo_id,))}
    finally:
        await conn.close()


@router.post("/promo/{promo_id}/delete")
async def promo_delete(promo_id: int, admin=Depends(auth.current_admin)):
    """Удалить можно только ручной код, которым ещё никто не воспользовался; иначе — выключить."""
    conn = await db.get_db()
    try:
        row = await (await conn.execute(
            "SELECT source, usage_count FROM promo_codes WHERE id = ?", (promo_id,))).fetchone()
        if not row:
            raise HTTPException(404, "Промокод не найден")
        used = row["usage_count"] or await _scalar(
            conn, "SELECT COUNT(*) FROM payments WHERE promo_code_id = ?", (promo_id,))
        if row["source"] != "manual" or used:
            raise HTTPException(409, "Код уже использовали — его можно только выключить")
        try:
            await conn.execute("UPDATE users SET active_promo_code_id = NULL WHERE active_promo_code_id = ?", (promo_id,))
            await conn.execute("DELETE FROM promo_link_visits WHERE promo_code_id = ?", (promo_id,))
            await conn.execute("DELETE FROM promo_codes WHERE id = ?", (promo_id,))
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise HTTPException(409, "Код уже использовали — его можно только выключить")
        return {"ok": True}
    finally:
        await conn.close()


# ---------- аналитика ----------

@router.get("/analytics")
async def analytics(days: int = 30, admin=Depends(auth.current_admin)):
    """days: 7 / 30 / 90; 0 — за всё время. Графики по дням — на дашборде."""
    days = max(0, min(days, 365))
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S") if days else "1970-01-01"
    conn = await db.get_db()
    try:
        out = {"days": days}

        # Итоги за период.
        cur = await conn.execute(
            f"SELECT COUNT(*) AS n, COALESCE(SUM(p.payable_amount_minor), 0) AS s, COUNT(DISTINCT p.user_id) AS u "
            f"FROM payments p WHERE {PAID} AND p.paid_at >= ?", (since,))
        r = await cur.fetchone()
        out["revenue"] = {
            "payments": r["n"], "revenue_minor": r["s"], "payers": r["u"],
            "avg_check_minor": round(r["s"] / r["n"]) if r["n"] else 0,
        }
        # Первые и повторные оплаты: первая — у пользователя нет оплаченного заказа раньше этого.
        out["revenue"]["first_payments"] = await _scalar(conn, f"""
            SELECT COUNT(*) FROM payments p WHERE {PAID} AND p.paid_at >= ?
              AND NOT EXISTS (SELECT 1 FROM payments q WHERE q.user_id = p.user_id AND q.status = 'paid'
                              AND q.payable_amount_minor > 0 AND COALESCE(q.payment_type, '') != 'balance'
                              AND q.paid_at < p.paid_at)""", (since,))

        # Воронка тех, кто пришёл за период: регистрация → пробный → оплата → повторная оплата.
        cur = await conn.execute(f"""
            SELECT COUNT(*) AS registered,
                   SUM(CASE WHEN u.used_trial = 1 THEN 1 ELSE 0 END) AS trial,
                   SUM(CASE WHEN pc >= 1 THEN 1 ELSE 0 END) AS paid,
                   SUM(CASE WHEN pc >= 2 THEN 1 ELSE 0 END) AS repeat
            FROM (SELECT u.used_trial,
                         (SELECT COUNT(*) FROM payments p WHERE p.user_id = u.id AND {PAID}) AS pc
                  FROM users u WHERE u.created_at >= ?) u""", (since,))
        out["funnel"] = {k: v or 0 for k, v in dict(await cur.fetchone()).items()}

        # Откуда пришли: по приглашению, по промо-ссылке, остальные.
        cur = await conn.execute("""
            SELECT SUM(CASE WHEN u.referred_by IS NOT NULL THEN 1 ELSE 0 END) AS referral,
                   SUM(CASE WHEN u.referred_by IS NULL AND EXISTS (
                         SELECT 1 FROM promo_link_visits v WHERE v.user_id = u.id
                           AND v.created_at <= datetime(u.created_at, '+1 day')) THEN 1 ELSE 0 END) AS promo_link,
                   COUNT(*) AS total
            FROM users u WHERE u.created_at >= ?""", (since,))
        r = dict(await cur.fetchone())
        r = {k: v or 0 for k, v in r.items()}
        r["other"] = r["total"] - r["referral"] - r["promo_link"]
        out["sources"] = r

        # Рефералы: сколько друзей оплатили и сколько дней начислено.
        try:
            cur = await conn.execute(
                "SELECT COUNT(DISTINCT payer_id) AS payers, COALESCE(SUM(reward_days), 0) AS days "
                "FROM payment_referral_effects WHERE level = 1 AND created_at >= ?", (since,))
            out["referral"] = dict(await cur.fetchone())
        except Exception:
            out["referral"] = None

        # Скидки: сколько оплат прошло по промокодам и по каким группам.
        cur = await conn.execute(f"""
            SELECT CASE WHEN pc.source = 'manual' THEN 'manual'
                        WHEN pc.source LIKE 'miniapp_lastchance:%' THEN 'lastchance'
                        WHEN pc.source LIKE 'wheel:%' THEN 'wheel'
                        ELSE 'auto' END AS grp,
                   COUNT(*) AS n, COALESCE(SUM(p.payable_amount_minor), 0) AS s
            FROM payments p JOIN promo_codes pc ON pc.id = p.promo_code_id
            WHERE {PAID} AND p.paid_at >= ? GROUP BY grp""", (since,))
        out["promo"] = {r["grp"]: {"payments": r["n"], "revenue_minor": r["s"]} for r in await cur.fetchall()}
        out["promo_issued_lastchance"] = await _scalar(
            conn, "SELECT COUNT(*) FROM promo_codes WHERE source LIKE 'miniapp_lastchance:%' AND created_at >= ?", (since,))

        # Карты и автопродление (таблицы бота; колонки проверяем, чтобы не упасть на другой версии).
        cards = None
        cols = await _columns(conn, "saved_payment_methods")
        if cols:
            who = "COUNT(DISTINCT user_id)" if "user_id" in cols else "COUNT(*)"
            alive = " WHERE is_active = 1" if "is_active" in cols else ""
            cards = {"users_with_card": await _scalar(conn, f"SELECT {who} FROM saved_payment_methods{alive}")}
            cols = await _columns(conn, "key_autorenew")
            if cols:
                on = next((c for c in ("enabled", "is_enabled", "is_active") if c in cols), None)
                cards["autorenew_keys"] = await _scalar(
                    conn, "SELECT COUNT(*) FROM key_autorenew" + (f" WHERE {on} = 1" if on else ""))
        out["cards"] = cards
        return out
    finally:
        await conn.close()
