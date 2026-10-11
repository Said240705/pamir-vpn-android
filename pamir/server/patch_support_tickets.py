#!/usr/bin/env python3
"""Поддержка как тикеты: одна карточка на обращение, список открытых, закрытие кнопкой.

Меняет бота (/root/YadrenoVPN) и бэкенд кабинета (/root/pamir-vpn-miniapp/backend):

bot/keyboards/support.py — у карточки обращения кнопки «Ответить», «Закрыть» и «Все обращения».
bot/services/support.py
  - карточка нового обращения из приложения/сайта: «Обращение №N открыто»;
  - ответ из веб-админки человеку без Telegram (аккаунт по почте) только сохраняется, без ошибки.
bot/services/mini_app_api.py
  - следующие сообщения открытого обращения приходят админу коротко, ответом на карточку
    («💬 Обращение №N · имя» + текст), без новой карточки «Новое обращение» на каждое;
  - ответ /support/messages содержит номер обращения (thread_id) — приложение показывает «Обращение №N»;
  - закрытие из веб-админки сообщает пользователю (в Telegram, если он есть);
  - автозакрытие «молчащих» обращений: через 2 суток тишины предупреждение, ещё через сутки закрытие
    (было 30 + 30 минут — обращение закрывалось раньше, чем вы успевали ответить).
bot/handlers/admin/pamir_tickets.py (новый) + регистрация в bot/handlers/admin/__init__.py
  - /tickets и кнопка «📋 Все обращения»: список открытых обращений, просмотр истории,
    «Ответить», «Закрыть»; при закрытии пользователь получает сообщение (если есть Telegram),
    а приложение покажет «Обращение закрыто».
backend routers/topup_router.py — /topup/support/messages отдаёт thread_id.

Копии перед изменением: *.bak-tickets. Повторный запуск ничего не меняет.
После: systemctl restart yadreno-vpn pamir-backend
"""
import py_compile
import shutil
import sys
from pathlib import Path

BOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/root/YadrenoVPN")
BACKEND = Path(sys.argv[2] if len(sys.argv) > 2 else "/root/pamir-vpn-miniapp/backend")
MARK = "Pamir: tickets"

KB = BOT / "bot/keyboards/support.py"
SVC = BOT / "bot/services/support.py"
API = BOT / "bot/services/mini_app_api.py"
INIT = BOT / "bot/handlers/admin/__init__.py"
NEW = BOT / "bot/handlers/admin/pamir_tickets.py"
TOPUP = BACKEND / "routers/topup_router.py"

if MARK in API.read_text(encoding="utf-8"):
    sys.exit("Правка уже применена — ничего не меняю.")

EDITS = {
    KB: [(
        '''def admin_support_reply_kb(thread_id: int) -> InlineKeyboardMarkup:
    """Admin response button in the support chain."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💬 Ответить", callback_data=f"admin_support_reply:{thread_id}"))
    return builder.as_markup()
''',
        '''def admin_support_reply_kb(thread_id: int) -> InlineKeyboardMarkup:
    """Admin response button in the support chain (Pamir: tickets — plus close and the open list)."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💬 Ответить", callback_data=f"admin_support_reply:{thread_id}"),
        InlineKeyboardButton(text="🔒 Закрыть", callback_data=f"admin_ticket_close:{thread_id}"),
    )
    builder.row(InlineKeyboardButton(text="📋 Все обращения", callback_data="admin_tickets"))
    return builder.as_markup()
''',
    )],
    SVC: [
        (
            '''                    text=format_admin_support_card(
                        title="Новое обращение в поддержку",
''',
            '''                    text=format_admin_support_card(
                        title=f"Обращение №{int(thread['id'])} открыто",
''',
        ),
        (
            '''    """Delivers one extension-origin admin-side message to its support user."""
    delivered_message_id = message.get("delivered_message_id")
    if delivered_message_id:
        return {"sent": 1, "failed": 0, "status": "sent"}
''',
            '''    """Delivers one extension-origin admin-side message to its support user."""
    delivered_message_id = message.get("delivered_message_id")
    if delivered_message_id:
        return {"sent": 1, "failed": 0, "status": "sent"}
    # Pamir: tickets — no Telegram (e-mail account): the reply is already stored, the app shows it.
    if int(thread.get("user_telegram_id") or 0) <= 0:
        return {"sent": 0, "failed": 0, "status": "stored"}
''',
        ),
    ],
    API: [
        ("SUPPORT_WARN_AFTER_MINUTES = 30\n", "SUPPORT_WARN_AFTER_MINUTES = 48 * 60  # Pamir: tickets — 2 суток тишины\n"),
        ("SUPPORT_CLOSE_AFTER_WARN_MINUTES = 30\n", "SUPPORT_CLOSE_AFTER_WARN_MINUTES = 24 * 60\n"),
        (
            "                return web.json_response({'ok': True, 'thread_status': thread['status'], 'messages': []})\n",
            "                return web.json_response({'ok': True, 'thread_status': thread['status'], 'thread_id': thread['id'], 'messages': []})\n",
        ),
        (
            "        return web.json_response({'ok': True, 'thread_status': thread['status'], 'messages': messages})\n",
            "        return web.json_response({'ok': True, 'thread_status': thread['status'], 'thread_id': thread['id'], 'messages': messages})\n",
        ),
        (
            '''        from bot.services.support import send_generated_user_message_to_admins

        await send_generated_user_message_to_admins(
            bot,
            thread=dict(thread_row),
            user=dict(user_row),
            support_message_id=int(message_id),
            text_html=text_html,
        )
        return web.json_response({'ok': True})
''',
            '''        await _pamir_ticket_followup(bot, dict(thread_row), dict(user_row), text_html)
        return web.json_response({'ok': True})
''',
        ),
        (
            '''            conn.execute(
                "UPDATE support_threads SET status = 'closed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (thread_id,),
            )
            conn.execute("DELETE FROM support_inactivity WHERE thread_id = ?", (thread_id,))
        return web.json_response({'ok': True})
''',
            '''            conn.execute(
                "UPDATE support_threads SET status = 'closed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (thread_id,),
            )
            conn.execute("DELETE FROM support_inactivity WHERE thread_id = ?", (thread_id,))
        await _pamir_ticket_closed_notify(request.app.get("mini_app_bot"), thread_id)
        return web.json_response({'ok': True})
''',
        ),
    ],
    INIT: [
        (
            "from bot.handlers.admin.support import router as support_router\n",
            "from bot.handlers.admin.support import router as support_router\n"
            "from bot.handlers.admin.pamir_tickets import router as pamir_tickets_router  # Pamir: tickets\n",
        ),
        (
            "admin_router.include_router(support_router)\n",
            "admin_router.include_router(support_router)\nadmin_router.include_router(pamir_tickets_router)\n",
        ),
    ],
    TOPUP: [(
        '    return {"thread_status": data.get("thread_status"), "messages": data.get("messages", [])}\n',
        '    return {"thread_status": data.get("thread_status"), "thread_id": data.get("thread_id"), "messages": data.get("messages", [])}  # Pamir: tickets\n',
    )],
}

API_TAIL = '''


# --- Pamir: tickets ---
async def _pamir_ticket_followup(bot, thread, user, text_html):
    """Next message of an open ticket: a short note as a reply to the ticket card, no new card."""
    from bot.keyboards.support import admin_support_reply_kb
    from bot.services.support import format_support_user_line
    from database.requests import get_support_admin_notifications

    thread_id = int(thread["id"])
    assigned = thread.get("assigned_admin_id")
    recipients = [int(assigned)] if assigned else sorted({int(a) for a in ADMIN_IDS})
    cards = {}
    for n in get_support_admin_notifications(thread_id, active_only=False):
        if n.get("card_message_id"):
            cards.setdefault(int(n["admin_telegram_id"]), int(n["card_message_id"]))
    text = f"💬 <b>Обращение №{thread_id}</b> · {format_support_user_line(user)}\\n\\n{text_html}"
    for admin_id in recipients:
        kwargs = {}
        if admin_id in cards:
            try:
                from aiogram.types import ReplyParameters
                kwargs["reply_parameters"] = ReplyParameters(message_id=cards[admin_id], allow_sending_without_reply=True)
            except ImportError:
                kwargs["reply_to_message_id"] = cards[admin_id]
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML", reply_markup=admin_support_reply_kb(thread_id), **kwargs)
        except Exception as error:
            logger.warning("Pamir ticket %s: note to admin %s failed: %s", thread_id, admin_id, error)


async def _pamir_ticket_closed_notify(bot, thread_id):
    """Tells the user that support closed the ticket (Telegram only; the app sees thread_status)."""
    from database.connection import get_db

    with get_db() as conn:
        row = conn.execute("SELECT user_telegram_id FROM support_threads WHERE id = ?", (int(thread_id),)).fetchone()
    tg = int(row["user_telegram_id"] or 0) if row else 0
    if tg <= 0 or bot is None:
        return
    try:
        await bot.send_message(
            tg,
            f"🔒 Обращение №{int(thread_id)} закрыто.\\nЕсли вопрос остался — просто напишите снова.",
        )
    except Exception as error:
        logger.warning("Pamir ticket %s: close notice failed: %s", thread_id, error)
'''

NEW_ROUTER = '''"""Pamir: tickets — список открытых обращений, просмотр и закрытие из бота."""
import logging
import re
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.support import format_support_user_line, support_thread_operation
from bot.utils.admin import is_admin
from bot.utils.text import escape_html
from database.connection import get_db

logger = logging.getLogger(__name__)
router = Router()


def _ago(raw) -> str:
    try:
        t = datetime.strptime(str(raw)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return ""
    m = int((datetime.now(timezone.utc) - t).total_seconds() // 60)
    if m < 1:
        return "только что"
    if m < 60:
        return f"{m} мин назад"
    if m < 1440:
        return f"{m // 60} ч назад"
    return f"{m // 1440} дн назад"


def _plain(html: str, limit: int = 300) -> str:
    text = re.sub(r"<[^>]+>", "", html or "")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&amp;", "&").strip()
    if len(text) > limit:
        text = text[:limit] + "…"
    return escape_html(text)


def _email_sql(conn) -> str:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    return "u.email" if "email" in cols else "NULL"


def _who(t) -> str:
    """@username, else the e-mail of an account without Telegram, else name / ID."""
    if not t.get("username") and t.get("email"):
        return escape_html(str(t["email"]))
    return format_support_user_line(t)


def _open_threads(limit: int = 20):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT t.id, t.user_telegram_id, t.assigned_admin_id, t.last_message_at, "
            f"u.username, u.first_name, u.last_name, u.telegram_id, {_email_sql(conn)} AS email, "
            "(SELECT sender_type FROM support_messages m WHERE m.thread_id = t.id ORDER BY m.id DESC LIMIT 1) AS last_sender "
            "FROM support_threads t LEFT JOIN users u ON u.id = t.user_id "
            "WHERE t.status != 'closed' ORDER BY t.last_message_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


async def _show_list(target: Message, edit: bool):
    threads = _open_threads()
    builder = InlineKeyboardBuilder()
    if threads:
        lines = [f"📋 <b>Открытые обращения: {len(threads)}</b>", "", "🔴 — ждёт вашего ответа"]
        for t in threads:
            waiting = "🔴" if t.get("last_sender") == "user" else "🟢"
            label = f"{waiting} №{t['id']} · {_who(t)} · {_ago(t['last_message_at'])}"
            label = re.sub(r"<[^>]+>", "", label).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
            builder.row(InlineKeyboardButton(text=label[:60], callback_data=f"admin_ticket_view:{t['id']}"))
    else:
        lines = ["📋 <b>Открытых обращений нет</b>", "", "Новые обращения придут сюда сами."]
    builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_tickets"))
    text = "\\n".join(lines)
    if edit:
        try:
            await target.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            return
        except Exception:
            pass
    await target.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.message(Command("tickets"))
async def tickets_command(message: Message):
    if not is_admin(message.from_user.id):
        return
    await _show_list(message, edit=False)


@router.callback_query(F.data == "admin_tickets")
async def tickets_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await _show_list(callback.message, edit=callback.message.text is not None and callback.message.text.startswith("📋"))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_ticket_view:"))
async def ticket_view(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    try:
        thread_id = int(callback.data.split(":", 1)[1])
    except (TypeError, ValueError, IndexError):
        await callback.answer("❌ Некорректное обращение", show_alert=True)
        return
    with get_db() as conn:
        t = conn.execute(
            f"SELECT t.*, u.username, u.first_name, u.last_name, u.telegram_id, {_email_sql(conn)} AS email FROM support_threads t "
            "LEFT JOIN users u ON u.id = t.user_id WHERE t.id = ?",
            (thread_id,),
        ).fetchone()
        msgs = conn.execute(
            "SELECT sender_type, text_html, media_type, created_at FROM support_messages "
            "WHERE thread_id = ? ORDER BY id DESC LIMIT 12",
            (thread_id,),
        ).fetchall()
    if not t:
        await callback.answer("❌ Обращение не найдено", show_alert=True)
        return
    t = dict(t)
    status = "🔒 закрыто" if t["status"] == "closed" else "🟢 открыто"
    lines = [
        f"🧵 <b>Обращение №{thread_id}</b> · {status}",
        f"👤 {_who(t)}" + ("" if int(t["user_telegram_id"] or 0) > 0 else " · без Telegram (по почте)"),
        "",
    ]
    for m in reversed(msgs):
        who = "👤" if m["sender_type"] == "user" else "🛟"
        body = _plain(m["text_html"]) or ("📷 фото" if m["media_type"] == "photo" else "…")
        lines.append(f"{who} <i>{_ago(m['created_at'])}</i>\\n{body}")
        lines.append("")
    text = "\\n".join(lines)[:3900]
    builder = InlineKeyboardBuilder()
    if t["status"] != "closed":
        builder.row(
            InlineKeyboardButton(text="💬 Ответить", callback_data=f"admin_support_reply:{thread_id}"),
            InlineKeyboardButton(text="🔒 Закрыть", callback_data=f"admin_ticket_close:{thread_id}"),
        )
    builder.row(InlineKeyboardButton(text="⬅️ Все обращения", callback_data="admin_tickets"))
    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_ticket_close:"))
async def ticket_close(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    try:
        thread_id = int(callback.data.split(":", 1)[1])
    except (TypeError, ValueError, IndexError):
        await callback.answer("❌ Некорректное обращение", show_alert=True)
        return
    async with support_thread_operation(thread_id):
        with get_db() as conn:
            row = conn.execute("SELECT status, user_telegram_id FROM support_threads WHERE id = ?", (thread_id,)).fetchone()
            if not row:
                await callback.answer("❌ Обращение не найдено", show_alert=True)
                return
            if row["status"] == "closed":
                await callback.answer("Обращение уже закрыто", show_alert=True)
                return
            conn.execute(
                "UPDATE support_threads SET status = 'closed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (thread_id,),
            )
            try:
                conn.execute("DELETE FROM support_inactivity WHERE thread_id = ?", (thread_id,))
            except Exception:
                pass
    tg = int(row["user_telegram_id"] or 0)
    if tg > 0:
        try:
            await callback.bot.send_message(
                tg, f"🔒 Обращение №{thread_id} закрыто.\\nЕсли вопрос остался — просто напишите снова."
            )
        except Exception as error:
            logger.warning("Pamir ticket %s: close notice failed: %s", thread_id, error)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📋 Все обращения", callback_data="admin_tickets"))
    try:
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    except Exception:
        pass
    await callback.message.answer(
        f"🔒 <b>Обращение №{thread_id} закрыто</b>\\n"
        + ("Пользователь получил сообщение в Telegram." if tg > 0 else "Пользователь увидит это в приложении."),
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer("Обращение закрыто")
'''

for path, pairs in EDITS.items():
    src = path.read_text(encoding="utf-8")
    for old, _ in pairs:
        if src.count(old) != 1:
            sys.exit(f"{path}: не нашёл нужный кусок в ожидаемом виде — файлы отличаются, ничего не меняю.\n{old[:120]!r}")
if NEW.exists():
    sys.exit(f"{NEW} уже существует — ничего не меняю.")

backups = []
for path, pairs in EDITS.items():
    b = path.with_name(path.name + ".bak-tickets")
    shutil.copy2(path, b)
    backups.append((path, b))
    src = path.read_text(encoding="utf-8")
    for old, new in pairs:
        src = src.replace(old, new, 1)
    if path == API:
        src = src.rstrip("\n") + API_TAIL
    path.write_text(src, encoding="utf-8")
NEW.write_text(NEW_ROUTER, encoding="utf-8")

try:
    for path in [*EDITS, NEW]:
        py_compile.compile(str(path), doraise=True)
except py_compile.PyCompileError as error:
    for path, b in backups:
        shutil.copy2(b, path)
    NEW.unlink(missing_ok=True)
    sys.exit(f"Ошибка синтаксиса, вернул копии: {error}")
print("Готово: обращения как тикеты. Перезапустите: systemctl restart yadreno-vpn pamir-backend")
