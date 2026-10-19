"""Новогодний сезон Mognu на стороне бота: цена со скидкой в списках тарифов, адвент-календарь и «Твой год с Mognu».

Ставится в /root/YadrenoVPN/bot/services/mognu_season.py (patch_mognu_newyear.py), вызывается из mini_app_api.py
и page_button_items.py. Даты и «видят заранее» берутся из настроек расширения mognu_newyear (админка → Расширения),
так что скидка, календарь и итоги года включаются и выключаются в одном месте.

  • Скидка: сама цена при оплате считается политикой расширения; здесь — только показ «было → стало» в списках.
  • Адвент-календарь 20–31 декабря: одна коробка в день, подарок выдаёт сервер и запоминает (повторно не выдаётся).
    Три скидки, 50 ₽ на баланс (только тем, кто хоть раз платил, остальным — промокод), открытка и пожелания.
  • Итоги года: трафик за год по ежедневным снимкам, лучший месяц и день, место среди всех пользователей,
    приглашённые друзья, чаты с поддержкой, вращения колеса, оплаты, подарок от Могну в конце (один за сезон); плюс общая карточка всех пользователей —
    любимая страна по суммарному трафику серверов (панель не делит трафик человека по серверам, и мы этого не пишем).
"""
from __future__ import annotations

import datetime
import logging
import secrets
import sqlite3
import string
import time
from typing import Any

logger = logging.getLogger(__name__)

MSK = datetime.timezone(datetime.timedelta(hours=3))
EXT_ID = 'mognu_newyear'
POLICY_NAME = 'ext_mognu_newyear'

# Подарки календаря по дням декабря: (вид, значение). promo — скидка %, balance — рубли на баланс,
# card — открытка, wish — пожелание от Могну (сам текст — в кабинете, assets/cabinet-newyear.js).
# days (дни к подписке) в расписании больше нет, но уже открытые такие коробки показываются как раньше.
ADVENT = {
    20: ('wish', 0), 21: ('promo', 10), 22: ('wish', 0), 23: ('balance', 50),
    24: ('card', 0), 25: ('wish', 0), 26: ('promo', 15), 27: ('wish', 0),
    28: ('wish', 0), 29: ('wish', 0), 30: ('wish', 0), 31: ('promo', 25),
}
ADVENT_FIRST, ADVENT_LAST = 20, 31
# Кому дни не положены (ни одной оплаты или нет действующего ключа) — промокод вместо дней.
ADVENT_DAYS_FALLBACK_PROMO = 15
ADVENT_DAYS_FALLBACK_PROMO_BIG = 30   # вместо главного подарка 31 декабря
ADVENT_BALANCE_FALLBACK_PROMO = 10    # вместо рублей на баланс тем, кто ещё ни разу не платил
# Подарок в конце итогов года: дни тем, кто платил и у кого есть действующий ключ, остальным — промокод.
GIFT_DAYS = 14
GIFT_PROMO = 30


# ── настройки и даты ──────────────────────────────────────────────────────────

def _config() -> dict[str, Any]:
    try:
        from bot.utils.extension_settings import get_extension_config
        return dict(get_extension_config(EXT_ID) or {})
    except Exception as error:
        logger.warning('mognu_season: extension config unavailable: %s', error)
        return {}


def _date(value: Any, fallback: datetime.date) -> datetime.date:
    try:
        return datetime.date.fromisoformat(str(value).strip())
    except Exception:
        return fallback


def _window(config: dict[str, Any]) -> tuple[datetime.date, datetime.date]:
    return (_date(config.get('start'), datetime.date(2026, 12, 20)),
            _date(config.get('end'), datetime.date(2027, 1, 10)))


def _today() -> datetime.date:
    return datetime.datetime.now(MSK).date()


def _preview_telegram_ids(config: dict[str, Any]) -> set[int]:
    raw = str(config.get('preview_telegram_ids') or '')
    return {int(p) for p in raw.replace(';', ',').split(',') if p.strip().isdigit()}


def season(telegram_id: int | None) -> str | None:
    """'on' during the New Year window, 'preview' for preview Telegram IDs before it, None otherwise."""
    config = _config()
    if not config.get('enabled'):
        return None
    start, end = _window(config)
    today = _today()
    if start <= today <= end:
        return 'on'
    if today < start and telegram_id and int(telegram_id) in _preview_telegram_ids(config):
        return 'preview'
    return None


def _user(conn, telegram_id: int):
    return conn.execute("SELECT id, created_at FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()


# ── скидка в списках тарифов ──────────────────────────────────────────────────

def sale_for(tariff: dict[str, Any], user_id: int | None) -> dict[str, Any] | None:
    """The New Year price for a tariff list, from the same pricing policy that charges it; None — no sale."""
    try:
        from bot.utils.policy_registry import PRICING_POLICIES
        policy = PRICING_POLICIES.get(POLICY_NAME)
        price = int(tariff.get('price_minor') or 0)
        if policy is None or price <= 0:
            return None
        decision = policy({
            'tariff': dict(tariff), 'user_id': user_id, 'purpose': 'display', 'payment_type': 'display',
            'quote': {'original_amount': price, 'final_amount': price},
        })
    except Exception as error:
        logger.warning('mognu_season: sale preview failed tariff=%s: %s', tariff.get('id'), error)
        return None
    if not decision or 'final_amount' not in decision:
        return None
    final = int(decision['final_amount'])
    if final >= price:
        return None
    meta = dict(decision.get('metadata') or {})
    return {
        'sale_price_minor': final,
        'sale_percent': meta.get('percent'),
        'sale_until': meta.get('until'),
        'sale_label': decision.get('label'),
    }


def user_id_for_telegram(telegram_id: Any) -> int | None:
    try:
        tid = int(telegram_id)
    except (TypeError, ValueError):
        return None
    from database.connection import get_db
    with get_db() as conn:
        row = conn.execute("SELECT id FROM users WHERE telegram_id = ?", (tid,)).fetchone()
    return int(row['id']) if row else None


# ── адвент-календарь ──────────────────────────────────────────────────────────

def _ensure_advent_table(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS mognu_advent ("
        "user_id INTEGER NOT NULL, season INTEGER NOT NULL, day INTEGER NOT NULL, "
        "prize TEXT NOT NULL, value INTEGER NOT NULL DEFAULT 0, code TEXT, note TEXT, "
        "opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (user_id, season, day))"
    )


def _advent_today(state: str, opened: dict[int, dict], start: datetime.date) -> int | None:
    """Which box can be opened now: the date's box in December; in preview — the next unopened one, straight away."""
    today = _today()
    if state == 'on':
        if today.month == 12 and ADVENT_FIRST <= today.day <= ADVENT_LAST and today.year == start.year:
            return today.day
        return None
    # preview (owner testing before Dec 20): boxes in order, the next one right after the previous — no waiting a day
    for day in range(ADVENT_FIRST, ADVENT_LAST + 1):
        if day not in opened:
            return day
    return None


def advent_status(telegram_id: int) -> dict[str, Any]:
    state = season(telegram_id)
    if not state:
        return {'available': False}
    start, _ = _window(_config())
    from database.connection import get_db
    with get_db() as conn:
        _ensure_advent_table(conn)
        user = _user(conn, telegram_id)
        rows = [] if not user else conn.execute(
            "SELECT day, prize, value, code, note, opened_at FROM mognu_advent WHERE user_id = ? AND season = ?",
            (user['id'], start.year),
        ).fetchall()
    opened = {int(r['day']): dict(r) for r in rows}
    today = _advent_today(state, opened, start)
    days = []
    for day in range(ADVENT_FIRST, ADVENT_LAST + 1):
        if day in opened:
            r = opened[day]
            days.append({'day': day, 'state': 'opened', 'prize': r['prize'], 'value': r['value'],
                         'code': r['code'], 'note': r['note']})
        elif day == today:
            days.append({'day': day, 'state': 'today'})
        elif state == 'on' and _today().month == 12 and day < _today().day:
            days.append({'day': day, 'state': 'missed'})
        else:
            days.append({'day': day, 'state': 'locked'})
    return {'available': True, 'state': state, 'today': today, 'days': days}


def _new_code(prefix: str) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return prefix + ''.join(secrets.choice(alphabet) for _ in range(6))


def _has_paid(conn, user_id: int) -> bool:
    return conn.execute(
        "SELECT 1 FROM payments WHERE user_id = ? AND status = 'paid' AND payable_amount_minor > 0 LIMIT 1",
        (user_id,),
    ).fetchone() is not None


def _paid_and_active(conn, user_id: int) -> bool:
    paid = _has_paid(conn, user_id)
    active = conn.execute(
        "SELECT 1 FROM vpn_keys WHERE user_id = ? AND expires_at IS NOT NULL AND expires_at > datetime('now') LIMIT 1",
        (user_id,),
    ).fetchone()
    return bool(paid and active)


async def advent_open(telegram_id: int) -> dict[str, Any]:
    """Opens today's box once: records it first (so a double tap gives nothing twice), then hands out the prize."""
    status = advent_status(telegram_id)
    if not status.get('available'):
        return {'ok': False, 'reason': 'not_available'}
    day = status.get('today')
    if not day:
        return {'ok': False, 'reason': 'no_box_today'}
    config = _config()
    start, end = _window(config)
    # promo codes live until the last day of the New Year window (MSK end of day, stored in UTC)
    promo_until = (datetime.datetime.combine(end, datetime.time(23, 59, 59), MSK)
                   .astimezone(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))

    from database.connection import get_db
    from database.db_users import get_or_create_user

    user, _ = get_or_create_user(telegram_id)
    user_id = int(user['id'])
    prize, value = ADVENT[day]
    with get_db() as conn:
        _ensure_advent_table(conn)
        if prize == 'days' and not _paid_and_active(conn, user_id):
            prize, value = 'promo', (ADVENT_DAYS_FALLBACK_PROMO_BIG if day == ADVENT_LAST else ADVENT_DAYS_FALLBACK_PROMO)
        # money only for those who have paid at least once, or fresh accounts would farm it
        if prize == 'balance' and not _has_paid(conn, user_id):
            prize, value = 'promo', ADVENT_BALANCE_FALLBACK_PROMO
        cur = conn.execute(
            "INSERT OR IGNORE INTO mognu_advent (user_id, season, day, prize, value) VALUES (?, ?, ?, ?, ?)",
            (user_id, start.year, day, prize, value),
        )
        if cur.rowcount == 0:
            return {'ok': False, 'reason': 'already_opened'}

    code = None
    note = None
    try:
        if prize == 'promo':
            from database.db_promotions import create_promo_code
            from bot.services.promotions import activate_promo_code_for_user, get_active_promo_discount_percent
            code = _new_code('ELKA')
            create_promo_code(
                code=code, discount_percent=int(value), expires_at=promo_until, activation_limit=1,
                source=f'mognu_advent:{start.year}:{user_id}:{day}', code_type='promo', issued_to_user_id=user_id,
            )
            # apply it to the next payment unless a bigger discount is already waiting
            if get_active_promo_discount_percent(user_id) < int(value):
                activate_promo_code_for_user(user_id, code)
                note = 'applied'
        elif prize == 'days':
            from bot.services.rewards import grant_days_to_first_active_key
            result = await grant_days_to_first_active_key(
                user_id, int(value), source='mognu_advent', reason=f'Адвент-календарь, {day} декабря',
                reference_type='mognu_advent', reference_id=f'{start.year}:{user_id}:{day}',
            )
            note = str(result.get('status') or ('applied' if result.get('ok') else 'failed'))
            if not result.get('ok'):
                logger.warning('mognu_season: advent days not granted user=%s day=%s: %s',
                               user_id, day, result.get('reason'))
        elif prize == 'balance':
            from bot.services.balance import credit_user_balance
            result = await credit_user_balance(
                user_id, int(value) * 100, source='mognu_advent', reason=f'Адвент-календарь, {day} декабря',
                reference_type='mognu_advent', reference_id=f'{start.year}:{user_id}:{day}',
            )
            note = 'applied' if result.get('ok') else 'failed'
            if not result.get('ok'):
                logger.warning('mognu_season: advent balance not credited user=%s day=%s: %s',
                               user_id, day, result.get('status'))
    except Exception as error:
        logger.exception('mognu_season: advent prize failed user=%s day=%s: %s', user_id, day, error)
        note = 'failed'

    with get_db() as conn:
        conn.execute(
            "UPDATE mognu_advent SET code = ?, note = ? WHERE user_id = ? AND season = ? AND day = ?",
            (code, note, user_id, start.year, day),
        )
    return {'ok': True, 'day': day, 'prize': prize, 'value': value, 'code': code, 'note': note}


def _ensure_gift_table(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS mognu_gift ("
        "user_id INTEGER NOT NULL, season INTEGER NOT NULL, prize TEXT NOT NULL, value INTEGER NOT NULL DEFAULT 0, "
        "code TEXT, note TEXT, opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (user_id, season))"
    )


def _gift_row(conn, user_id: int, season_year: int) -> dict[str, Any] | None:
    _ensure_gift_table(conn)
    row = conn.execute("SELECT prize, value, code, note FROM mognu_gift WHERE user_id = ? AND season = ?",
                       (user_id, season_year)).fetchone()
    return dict(row) if row else None


async def gift_open(telegram_id: int) -> dict[str, Any]:
    """The gift at the end of the year in review, once per season: recorded first (a double tap gives nothing twice),
    then handed out — days for those who paid and have an active key, a promo code for everyone else."""
    if not season(telegram_id):
        return {'ok': False, 'reason': 'not_available'}
    config = _config()
    start, end = _window(config)
    promo_until = (datetime.datetime.combine(end, datetime.time(23, 59, 59), MSK)
                   .astimezone(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))

    from database.connection import get_db
    from database.db_users import get_or_create_user

    user, _ = get_or_create_user(telegram_id)
    user_id = int(user['id'])
    with get_db() as conn:
        _ensure_gift_table(conn)
        prize, value = ('days', GIFT_DAYS) if _paid_and_active(conn, user_id) else ('promo', GIFT_PROMO)
        cur = conn.execute("INSERT OR IGNORE INTO mognu_gift (user_id, season, prize, value) VALUES (?, ?, ?, ?)",
                           (user_id, start.year, prize, value))
        if cur.rowcount == 0:
            return {'ok': False, 'reason': 'already_opened', 'gift': _gift_row(conn, user_id, start.year)}

    code = None
    note = None
    try:
        if prize == 'promo':
            from database.db_promotions import create_promo_code
            from bot.services.promotions import activate_promo_code_for_user, get_active_promo_discount_percent
            code = _new_code('SPASIBO')
            create_promo_code(
                code=code, discount_percent=int(value), expires_at=promo_until, activation_limit=1,
                source=f'mognu_gift:{start.year}:{user_id}', code_type='promo', issued_to_user_id=user_id,
            )
            if get_active_promo_discount_percent(user_id) < int(value):
                activate_promo_code_for_user(user_id, code)
                note = 'applied'
        else:
            from bot.services.rewards import grant_days_to_first_active_key
            result = await grant_days_to_first_active_key(
                user_id, int(value), source='mognu_gift', reason='Подарок от Могну в итогах года',
                reference_type='mognu_gift', reference_id=f'{start.year}:{user_id}',
            )
            note = str(result.get('status') or ('applied' if result.get('ok') else 'failed'))
            if not result.get('ok'):
                logger.warning('mognu_season: gift days not granted user=%s: %s', user_id, result.get('reason'))
    except Exception as error:
        logger.exception('mognu_season: gift failed user=%s: %s', user_id, error)
        note = 'failed'

    with get_db() as conn:
        conn.execute("UPDATE mognu_gift SET code = ?, note = ? WHERE user_id = ? AND season = ?",
                     (code, note, user_id, start.year))
    return {'ok': True, 'gift': {'prize': prize, 'value': value, 'code': code, 'note': note}}


# ── итоги года ────────────────────────────────────────────────────────────────

_RANK_CACHE: dict[str, Any] = {'at': 0.0, 'year': None, 'totals': []}
_COMMUNITY_CACHE: dict[str, Any] = {'at': 0.0, 'data': None}
XUI_DB = '/etc/x-ui/x-ui.db'


def _place(remark: str) -> str:
    """'ES', 'DE', … from the flag in an inbound name; 'LTE' for the mobile-mode servers; '' when unknown."""
    if 'LTE' in remark.upper():
        return 'LTE'
    letters = [chr(ord(c) - 0x1F1E6 + ord('A')) for c in remark if 0x1F1E6 <= ord(c) <= 0x1F1FF]
    return ''.join(letters[:2]) if len(letters) >= 2 else ''


def _community() -> dict[str, Any] | None:
    """Everyone together: all-time traffic of every server summed by country, cached for 6 hours.
    Aggregate only — the panel keeps one counter per server for all users, nothing per person."""
    if _COMMUNITY_CACHE['data'] is not None and time.time() - _COMMUNITY_CACHE['at'] < 6 * 3600:
        return _COMMUNITY_CACHE['data']
    try:
        with sqlite3.connect(f'file:{XUI_DB}?mode=ro', uri=True, timeout=5) as x:
            rows = x.execute("SELECT remark, up, down FROM inbounds").fetchall()
    except Exception as e:
        logger.warning('mognu wrapped: community stats unavailable (%s)', e)
        return None
    places: dict[str, int] = {}
    for remark, up, down in rows:
        key = _place(str(remark or ''))
        if key:
            places[key] = places.get(key, 0) + int(up or 0) + int(down or 0)
    total = sum(places.values())
    if not total:
        return None
    top = max(places, key=places.get)
    data = {'total_bytes': total, 'top_place': top, 'top_share': int(round(100 * places[top] / total))}
    _COMMUNITY_CACHE.update(at=time.time(), data=data)
    return data


def _history_start(conn) -> str:
    """The first day the bot recorded traffic snapshots (it started on 2026-09-06)."""
    row = conn.execute("SELECT MIN(snapshot_date) FROM traffic_history").fetchone()
    return str(row[0] or '')[:10] if row else ''


def _key_year_traffic(rows, year: int, history_start: str = '') -> tuple[int, dict[int, int], dict[str, int]]:
    """Traffic of one key in a year from its daily snapshots of a cumulative counter that may reset.
    A key that existed before snapshots began carries everything it used so far in its first snapshot: that goes to
    the year total only, not to that day or month, or the first recorded day would win «best day» for everyone."""
    total, months, days = 0, {}, {}
    prev = None
    for row in rows:
        date = str(row['snapshot_date'])[:10]
        used = int(row['traffic_used'] or 0)
        carried = prev is None and date == history_start
        delta = used if prev is None or used < prev else used - prev
        prev = used
        if not date.startswith(str(year)) or delta <= 0:
            continue
        total += delta
        if carried:
            continue
        months[int(date[5:7])] = months.get(int(date[5:7]), 0) + delta
        days[date] = days.get(date, 0) + delta
    return total, months, days


def _rhythm(days: dict[str, int]) -> dict[str, Any]:
    """Favourite weekday (0 = Monday) by traffic and the longest run of days in a row with traffic.
    The weekday needs two full weeks of data, or one lucky evening decides it."""
    dates = sorted(datetime.date.fromisoformat(d) for d, v in days.items() if v > 0)
    weekday, share = None, 0
    if len(dates) >= 14:
        per = [0] * 7
        for d, v in days.items():
            per[datetime.date.fromisoformat(d).weekday()] += v
        weekday = max(range(7), key=lambda i: per[i])
        share = int(round(100 * per[weekday] / (sum(per) or 1)))
    streak = run = 0
    for i, d in enumerate(dates):
        run = run + 1 if i and (d - dates[i - 1]).days == 1 else 1
        streak = max(streak, run)
    return {'weekday': weekday, 'weekday_share': share, 'streak_days': streak, 'active_days': len(dates)}


def _all_totals(conn, year: int) -> list[int]:
    """Every user's traffic for the year (sorted), cached for 6 hours — for the «more than N% of users» line."""
    if _RANK_CACHE['year'] == year and time.time() - _RANK_CACHE['at'] < 6 * 3600:
        return _RANK_CACHE['totals']
    per_user: dict[int, int] = {}
    start = _history_start(conn)
    keys = conn.execute("SELECT id, user_id FROM vpn_keys").fetchall()
    for key in keys:
        rows = conn.execute(
            "SELECT snapshot_date, traffic_used FROM traffic_history WHERE key_id = ? ORDER BY snapshot_date",
            (key['id'],),
        ).fetchall()
        total, _, _ = _key_year_traffic(rows, year, start)
        if total:
            per_user[int(key['user_id'])] = per_user.get(int(key['user_id']), 0) + total
    totals = sorted(per_user.values())
    _RANK_CACHE.update(at=time.time(), year=year, totals=totals)
    return totals


def wrapped(telegram_id: int) -> dict[str, Any]:
    state = season(telegram_id)
    if not state:
        return {'available': False}
    start, _ = _window(_config())
    year = start.year
    from database.connection import get_db
    with get_db() as conn:
        user = _user(conn, telegram_id)
        if not user:
            return {'available': False}
        uid = int(user['id'])
        joined = str(user['created_at'] or '')[:10]
        try:
            days_with_us = max(1, (_today() - datetime.date.fromisoformat(joined)).days)
        except ValueError:
            days_with_us = None

        total, months, days = 0, {}, {}
        start = _history_start(conn)
        for key in conn.execute("SELECT id FROM vpn_keys WHERE user_id = ?", (uid,)).fetchall():
            rows = conn.execute(
                "SELECT snapshot_date, traffic_used FROM traffic_history WHERE key_id = ? ORDER BY snapshot_date",
                (key['id'],),
            ).fetchall()
            t, m, d = _key_year_traffic(rows, year, start)
            total += t
            for k, v in m.items():
                months[k] = months.get(k, 0) + v
            for k, v in d.items():
                days[k] = days.get(k, 0) + v

        totals = _all_totals(conn, year)
        beat = None
        if total and totals:
            below = sum(1 for v in totals if v < total)
            beat = int(round(100 * below / len(totals)))

        def count(sql: str, *args) -> int:
            try:
                row = conn.execute(sql, args).fetchone()
                return int(row[0] or 0) if row else 0
            except Exception:
                return 0

        y0, y1 = f'{year}-01-01', f'{year + 1}-01-01'
        referrals = count("SELECT COUNT(*) FROM referral_stats WHERE referrer_id = ? AND level = 1", uid)
        chats = count("SELECT COUNT(*) FROM support_threads WHERE user_id = ? AND created_at >= ? AND created_at < ?",
                      uid, y0, y1)
        spins = count("SELECT total_spins FROM wheel_spins WHERE user_id = ?", uid)
        payments = count("SELECT COUNT(*) FROM payments WHERE user_id = ? AND status = 'paid' "
                         "AND paid_at >= ? AND paid_at < ?", uid, y0, y1)
        try:
            gift = _gift_row(conn, uid, year)
        except Exception:
            gift = None
        try:
            _ensure_advent_table(conn)
            advent = count("SELECT COUNT(*) FROM mognu_advent WHERE user_id = ? AND season = ?", uid, year)
        except Exception:
            advent = 0

    top_month = max(months, key=months.get) if months else None
    best_day = max(days, key=days.get) if days else None
    rhythm = _rhythm(days)
    return {
        'available': True,
        'state': state,
        'year': year,
        'joined': joined,
        'days_with_us': days_with_us,
        'traffic_bytes': total,
        'top_month': top_month,
        'top_month_bytes': months.get(top_month, 0) if top_month else 0,
        'best_day': best_day,
        'best_day_bytes': days.get(best_day, 0) if best_day else 0,
        'beat_percent': beat,
        'referrals': referrals,
        'support_chats': chats,
        'wheel_spins': spins,
        'payments': payments,
        'advent_opened': advent,
        **rhythm,
        'community': _community(),
        'gift': gift,
    }
