#!/usr/bin/env python3
"""Защита входа в админку кабинета Pamir VPN.

Меняет backend/auth.py и backend/routers/admin_router.py:
- вход админа живёт ADMIN_TOKEN_TTL_SECONDS (по умолчанию 12 часов) вместо 30 дней;
- в токене админа есть время выдачи (iat); токены без него (выданные до правки)
  больше не принимаются — админам нужно один раз войти заново;
- POST /admin/auth/logout-all — «выйти на всех устройствах»: все входы этого админа,
  выданные раньше, перестают работать (время отзыва хранится в admin_sessions.json).
Перед изменением кладёт копии рядом: *.bak-adminauth. Повторный запуск ничего не меняет.
"""
import shutil
import sys
from pathlib import Path

BACKEND = Path(sys.argv[1] if len(sys.argv) > 1 else "/root/pamir-vpn-miniapp/backend")
AUTH = BACKEND / "auth.py"
ROUTER = BACKEND / "routers" / "admin_router.py"

auth_src = AUTH.read_text(encoding="utf-8")
router_src = ROUTER.read_text(encoding="utf-8")
if "revoke_admin_tokens" in auth_src or "logout-all" in router_src:
    sys.exit("Правка уже применена — ничего не меняю.")

AUTH_EDITS = [
    (
        'JWT_TTL_SECONDS = 30 * 24 * 3600  # токен приложения живёт 30 дней\n',
        '''JWT_TTL_SECONDS = 30 * 24 * 3600  # токен приложения живёт 30 дней
# Вход админа короче: при утечке браузера/токена доступ к админке живёт часы, а не месяц
ADMIN_TOKEN_TTL_SECONDS = int(os.getenv("ADMIN_TOKEN_TTL_SECONDS", str(12 * 3600)))
# «Выйти на всех устройствах»: telegram_id админа -> время, раньше которого его токены недействительны
ADMIN_SESSIONS_FILE = Path(__file__).with_name("admin_sessions.json")


def _admin_sessions() -> dict:
    try:
        data = json.loads(ADMIN_SESSIONS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def revoke_admin_tokens(telegram_id) -> None:
    """Все входы этого админа, выданные до этого момента, перестают работать."""
    data = _admin_sessions()
    data[str(telegram_id)] = int(time.time())
    tmp = ADMIN_SESSIONS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, ADMIN_SESSIONS_FILE)
''',
    ),
    (
        '''def issue_admin_token(telegram_id: int) -> str:
    payload = {
        "sub": f"admin:{telegram_id}",
        "tg_id": telegram_id,
        "is_admin": True,
        "exp": int(time.time()) + JWT_TTL_SECONDS,
    }
''',
        '''def issue_admin_token(telegram_id: int) -> str:
    now = int(time.time())
    payload = {
        "sub": f"admin:{telegram_id}",
        "tg_id": telegram_id,
        "is_admin": True,
        "iat": now,
        "exp": now + ADMIN_TOKEN_TTL_SECONDS,
    }
''',
    ),
    (
        '''    if not payload.get("is_admin"):
        raise HTTPException(403, "Требуются права администратора")
    return payload
''',
        '''    if not payload.get("is_admin"):
        raise HTTPException(403, "Требуются права администратора")
    issued_at = payload.get("iat")
    if not isinstance(issued_at, (int, float)):
        # токен выдан до введения короткого срока (30 дней) — просим войти заново
        raise HTTPException(401, "Сессия устарела, войди заново")
    if issued_at < _admin_sessions().get(str(payload.get("tg_id")), 0):
        raise HTTPException(401, "Сессия завершена, войди заново")
    return payload
''',
    ),
]

ROUTER_EDITS = [
    (
        '''    admin_token = auth.issue_admin_token(telegram_id)
    return {"status": "approved", "access_token": admin_token}
''',
        '''    admin_token = auth.issue_admin_token(telegram_id)
    return {"status": "approved", "access_token": admin_token}


@router.post("/auth/logout-all")
async def admin_logout_all(admin=Depends(auth.current_admin)):
    """Выйти на всех устройствах: все входы этого админа, включая текущий, перестают работать."""
    auth.revoke_admin_tokens(admin.get("tg_id"))
    return {"ok": True}
''',
    ),
]


def apply(src, edits, name):
    for old, new in edits:
        count = src.count(old)
        if count != 1:
            sys.exit(f"{name}: не нашёл нужное место (найдено {count} раз), ничего не меняю:\n{old[:200]}")
        src = src.replace(old, new)
    return src


new_auth = apply(auth_src, AUTH_EDITS, "auth.py")
# json/os/Path нужны новым функциям — добавляем импорты, если их нет
imports = []
if "\nimport json" not in "\n" + new_auth:
    imports.append("import json")
if "\nimport os" not in "\n" + new_auth:
    imports.append("import os")
if "from pathlib import Path" not in new_auth:
    imports.append("from pathlib import Path")
if imports:
    anchor = "from jose import jwt, JWTError\n"
    if new_auth.count(anchor) != 1:
        sys.exit("auth.py: не нашёл строку импорта jose, ничего не меняю")
    new_auth = new_auth.replace(anchor, anchor + "\n".join(imports) + "\n")
new_router = apply(router_src, ROUTER_EDITS, "admin_router.py")

for path, text in ((AUTH, new_auth), (ROUTER, new_router)):
    shutil.copy2(path, path.with_name(path.name + ".bak-adminauth"))
    path.write_text(text, encoding="utf-8")
print("Готово. Копии старых файлов: auth.py.bak-adminauth, routers/admin_router.py.bak-adminauth")
