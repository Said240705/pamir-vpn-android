#!/usr/bin/env python3
"""Регистрация по почте: код из письма, без него — в кабинет не пускает.

Меняет routers/auth_router.py бэкенда кабинета:
- POST /auth/email/register: создаёт аккаунт и отправляет на почту 6-значный код
  (действует 15 минут, 5 попыток). Вход не выдаёт: ответ {"status": "code_sent"}.
- POST /auth/email/login: если почта нового аккаунта не подтверждена — шлёт код
  (не чаще раза в минуту) и отвечает 403 «email_not_verified».
- POST /auth/email/verify-code {email, code}: подтверждает почту и выдаёт вход.
- POST /auth/email/send-code {email}: отправить код ещё раз.

Кого не касается:
- аккаунты, созданные до установки патча (PAMIR_CODE_SINCE), — входят как раньше;
- старые версии Android-приложения (до 1.6.5, по User-Agent) — у них нет экрана ввода
  кода, поэтому для них всё по-старому: вход сразу, письмо со ссылкой.

Коды хранятся в таблице pamir_email_codes (только хэш). Копия перед изменением:
auth_router.py.bak-emailcode. Повторный запуск ничего не меняет.
"""
import datetime
import py_compile
import shutil
import sys
from pathlib import Path

PATH = Path(sys.argv[1] if len(sys.argv) > 1 else "/root/pamir-vpn-miniapp/backend/routers/auth_router.py")
src = PATH.read_text(encoding="utf-8")
if "PAMIR_CODE_SINCE" in src:
    sys.exit("Правка уже применена — ничего не меняю.")

SINCE = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

OLD_LOGIN = """    if not auth.verify_password(payload.password, user["password_hash"]):
        raise HTTPException(401, "Неверный email или пароль")

    token = auth.issue_app_token(user["id"], user.get("telegram_id"))
    return TokenOut(access_token=token)
"""
NEW_LOGIN = """    if not auth.verify_password(payload.password, user["password_hash"]):
        raise HTTPException(401, "Неверный email или пароль")
    if await _pamir_needs_code(user["id"], request):
        await _pamir_send_code(user["id"], payload.email, quiet=True)
        raise HTTPException(403, "email_not_verified")

    token = auth.issue_app_token(user["id"], user.get("telegram_id"))
    return TokenOut(access_token=token)
"""

OLD_REG = """@router.post("/email/register", response_model=TokenOut)
async def register_via_email(payload: EmailRegisterIn, request: Request):"""
NEW_REG = """@router.post("/email/register")
async def register_via_email(payload: EmailRegisterIn, request: Request):"""

OLD_REG_TAIL = """    public_url = os.getenv("PUBLIC_APP_URL", "").rstrip("/")
    verify_url = f"{public_url}/api/auth/verify-email?token={verify_token}"
    try:
        await mailer.send_verification_email(payload.email, verify_url)
    except Exception as e:
        print(f"[mailer] Ошибка отправки письма при регистрации: {e!r}")

    token = auth.issue_app_token(user["id"], user.get("telegram_id"))
    return TokenOut(access_token=token)
"""
NEW_REG_TAIL = """    if not _pamir_legacy_client(request):
        # Pamir: вход — только после кода из письма
        try:
            await _pamir_send_code(user["id"], payload.email)
        except Exception as e:
            print(f"[mailer] Ошибка отправки кода при регистрации: {e!r}")
            raise HTTPException(502, "Не удалось отправить письмо с кодом. Попробуйте через минуту")
        return {"status": "code_sent", "email": payload.email}

    public_url = os.getenv("PUBLIC_APP_URL", "").rstrip("/")
    verify_url = f"{public_url}/api/auth/verify-email?token={verify_token}"
    try:
        await mailer.send_verification_email(payload.email, verify_url)
    except Exception as e:
        print(f"[mailer] Ошибка отправки письма при регистрации: {e!r}")

    token = auth.issue_app_token(user["id"], user.get("telegram_id"))
    return TokenOut(access_token=token)


@router.post("/email/verify-code", response_model=TokenOut)
async def verify_email_code(payload: EmailCodeIn, request: Request):
    \"\"\"Pamir: код из письма → почта подтверждена, вход выдан.\"\"\"
    enforce_rate_limit(request, "email_code", max_requests=20, window_seconds=900)
    user = await db.get_user_by_email(payload.email)
    if not user:
        raise HTTPException(400, "Неверный код")
    await _pamir_check_code(user["id"], payload.code)
    token = auth.issue_app_token(user["id"], user.get("telegram_id"))
    return TokenOut(access_token=token)


@router.post("/email/send-code")
async def send_email_code(payload: ForgotPasswordIn, request: Request):
    \"\"\"Pamir: отправить код ещё раз (не чаще раза в минуту).\"\"\"
    enforce_rate_limit(request, "email_send_code", max_requests=6, window_seconds=3600)
    user = await db.get_user_by_email(payload.email)
    if user and not await _pamir_is_verified(user["id"]):
        await _pamir_send_code(user["id"], payload.email)
    return {"status": "ok"}
"""

ANCHOR = 'BOT_USERNAME = "pamirlink_bot"\n'
HELPERS = '''BOT_USERNAME = "pamirlink_bot"


# --- Pamir: подтверждение почты кодом из письма ---
# Аккаунты, созданные раньше этого момента (UTC), входят как раньше — без кода.
PAMIR_CODE_SINCE = "%s"
PAMIR_CODE_TTL = 15 * 60
PAMIR_CODE_TRIES = 5
PAMIR_CODE_COOLDOWN = 60


class EmailCodeIn(BaseModel):
    email: EmailStr
    code: str


def _pamir_legacy_client(request: Request) -> bool:
    """Android-приложение до 1.6.5 не умеет вводить код — для него всё по-старому."""
    ua = request.headers.get("user-agent", "")
    if not ua.startswith("PamirVPN-Android/"):
        return False
    ver = ua.split("/", 1)[1].split()[0]
    try:
        parts = [int(x) for x in ver.split(".")[:3]]
    except ValueError:
        return False
    return (parts + [0, 0, 0])[:3] < [1, 6, 5]


def _pamir_hash(code: str) -> str:
    import hashlib
    return hashlib.sha256(("pamir:" + code).encode()).hexdigest()


async def _pamir_db():
    conn = await db.get_db()
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS pamir_email_codes ("
        "user_id INTEGER PRIMARY KEY, code_hash TEXT NOT NULL, expires_at INTEGER NOT NULL, "
        "attempts INTEGER NOT NULL DEFAULT 0, sent_at INTEGER NOT NULL)"
    )
    return conn


async def _pamir_is_verified(user_id: int) -> bool:
    conn = await db.get_db()
    try:
        cur = await conn.execute(f"SELECT {db.COL_EMAIL_VERIFIED} FROM users WHERE id = ?", (user_id,))
        row = await cur.fetchone()
    finally:
        await conn.close()
    return bool(row and row[0])


async def _pamir_needs_code(user_id: int, request: Request) -> bool:
    if _pamir_legacy_client(request):
        return False
    conn = await db.get_db()
    try:
        cur = await conn.execute(
            f"SELECT {db.COL_EMAIL_VERIFIED}, created_at FROM users WHERE id = ?", (user_id,)
        )
        row = await cur.fetchone()
    finally:
        await conn.close()
    if not row or row[0]:
        return False
    created = str(row[1] or "")
    return bool(created) and created >= PAMIR_CODE_SINCE


async def _pamir_send_code(user_id: int, email: str, quiet: bool = False) -> None:
    import secrets
    import time
    now = int(time.time())
    conn = await _pamir_db()
    try:
        cur = await conn.execute("SELECT sent_at FROM pamir_email_codes WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if row and now - int(row[0]) < PAMIR_CODE_COOLDOWN:
            if quiet:
                return
            raise HTTPException(429, "Код уже отправлен — новый можно запросить через минуту")
        code = f"{secrets.randbelow(10 ** 6):06d}"
        await conn.execute(
            "INSERT OR REPLACE INTO pamir_email_codes (user_id, code_hash, expires_at, attempts, sent_at) "
            "VALUES (?, ?, ?, 0, ?)",
            (user_id, _pamir_hash(code), now + PAMIR_CODE_TTL, now),
        )
        await conn.commit()
    finally:
        await conn.close()
    body = (
        "Здравствуйте!\\n\\n"
        f"Ваш код для входа в Pamir VPN: {code}\\n\\n"
        "Введите его в приложении или на сайте. Код действует 15 минут.\\n\\n"
        "Если вы не регистрировались в Pamir VPN — просто проигнорируйте письмо."
    )
    try:
        await mailer.send_email(email, f"Код подтверждения: {code} — Pamir VPN", body)
    except Exception as e:
        print(f"[mailer] Ошибка отправки кода: {e!r}")
        if not quiet:
            raise


async def _pamir_check_code(user_id: int, code: str) -> None:
    import hmac
    import time
    code = "".join(ch for ch in str(code) if ch.isdigit())
    conn = await _pamir_db()
    try:
        cur = await conn.execute(
            "SELECT code_hash, expires_at, attempts FROM pamir_email_codes WHERE user_id = ?", (user_id,)
        )
        row = await cur.fetchone()
        if not row or int(row[1]) < int(time.time()) or int(row[2]) >= PAMIR_CODE_TRIES:
            raise HTTPException(400, "Код устарел — отправьте новый")
        if not hmac.compare_digest(row[0], _pamir_hash(code)):
            await conn.execute("UPDATE pamir_email_codes SET attempts = attempts + 1 WHERE user_id = ?", (user_id,))
            await conn.commit()
            left = PAMIR_CODE_TRIES - int(row[2]) - 1
            raise HTTPException(400, "Неверный код" + (f" — осталось попыток: {left}" if left > 0 else " — отправьте новый"))
        await conn.execute(f"UPDATE users SET {db.COL_EMAIL_VERIFIED} = 1 WHERE id = ?", (user_id,))
        await conn.execute("DELETE FROM pamir_email_codes WHERE user_id = ?", (user_id,))
        await conn.commit()
    finally:
        await conn.close()
''' % SINCE

for name, old, cnt in (("вход", OLD_LOGIN, 1), ("регистрация", OLD_REG, 1), ("письмо регистрации", OLD_REG_TAIL, 1), ("BOT_USERNAME", ANCHOR, 1)):
    if src.count(old) != cnt:
        sys.exit(f"Не нашёл «{name}» в ожидаемом виде — файл отличается, ничего не меняю.")

backup = PATH.with_name(PATH.name + ".bak-emailcode")
shutil.copy2(PATH, backup)
new = (src.replace(ANCHOR, HELPERS, 1).replace(OLD_LOGIN, NEW_LOGIN, 1)
       .replace(OLD_REG, NEW_REG, 1).replace(OLD_REG_TAIL, NEW_REG_TAIL, 1))
PATH.write_text(new, encoding="utf-8")
try:
    py_compile.compile(str(PATH), doraise=True)
except py_compile.PyCompileError as error:
    shutil.copy2(backup, PATH)
    sys.exit(f"Ошибка синтаксиса, вернул копию: {error}")
print(f"Готово: {PATH} (копия: {backup}). Аккаунты с {SINCE} UTC — вход по коду из письма.")
print("Перезапустите бэкенд: systemctl restart pamir-backend")
