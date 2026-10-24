#!/usr/bin/env python3
"""Новая админка Mognu VPN: серверная часть.

1. Бэкенд кабинета: admin_mognu.py (лежит рядом) → routers/pamir_admin_mognu.py и подключение в main.py
   сразу после pamir_admin_extra (адреса /api/admin/m/...).
2. Бот: два адреса для админки в bot/services/mini_app_api.py (тот же секрет, что у остальных):
   POST /mini-app-api/mognu-admin/fix-order {order_id, telegram_id} — поставить ключ заказа в панель так же, как
        после оплаты из приложения (_run_key_setup_without_delivery, как fix_draft_keys.py);
   POST /mini-app-api/mognu-admin/key-sync {key_id} — отправить срок и лимиты ключа из базы в панель (push_key_to_panel).
3. main.py: pamir_admin_mognu.track_clients(app) — отметка, с чего человек заходит и платит (копия main.py.bak-adminclients).
4. Тариф «На весь дом»: router_links.py → routers/pamir_router_links.py и в main.py app.include_router(pamir_admin_mognu.user_router)
   (адреса кабинета /api/topup/router/keys и /links — прямые ссылки ключа для роутера).

    python3 patch_admin_mognu.py          показать, что изменится (ничего не меняет)
    python3 patch_admin_mognu.py --apply  применить; копии рядом: main.py.bak-adminmognu, mini_app_api.py.bak-adminmognu
Потом: systemctl restart yadreno-vpn pamir-backend. Повторный запуск обновляет роутер и не трогает уже поправленное.
"""
import os
import py_compile
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = Path(os.getenv("PAMIR_BACKEND", "/root/pamir-vpn-miniapp/backend"))
MAIN = BACKEND / "main.py"
ROUTER = BACKEND / "routers" / "pamir_admin_mognu.py"
LINKS = BACKEND / "routers" / "pamir_router_links.py"
BOT = Path(os.getenv("PAMIR_BOT_SERVICES", "/root/YadrenoVPN/bot/services")) / "mini_app_api.py"
APPLY = "--apply" in sys.argv
MARK = "# Mognu: admin endpoints"

MAIN_ANCHOR = "app.include_router(pamir_admin_extra.router)\n"
MAIN_NEW = MAIN_ANCHOR + "from routers import pamir_admin_mognu  # новая админка /admin/m\napp.include_router(pamir_admin_mognu.router)\n"

BOT_ROUTE_ANCHOR = "    app.router.add_post('/mini-app-api/keys/delete', _pamir_key_delete_handler)\n"
BOT_ROUTE_NEW = BOT_ROUTE_ANCHOR + (
    "    app.router.add_post('/mini-app-api/mognu-admin/fix-order', _mognu_admin_fix_order_handler)  " + MARK + "\n"
    "    app.router.add_post('/mini-app-api/mognu-admin/key-sync', _mognu_admin_key_sync_handler)\n")
BOT_FUNC_ANCHOR = "async def _pamir_key_delete_handler(request: web.Request) -> web.Response:\n"
BOT_FUNC = '''async def _mognu_admin_fix_order_handler(request: web.Request) -> web.Response:
    """''' + MARK + ''': set the order's key up on the panel, as after an in-app payment (fix_draft_keys.py).
    A key that is already set up comes back with its current status and is not changed."""
    if not _check_secret(request):
        return web.json_response({'ok': False, 'reason': 'forbidden'}, status=403)
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({'ok': False, 'reason': 'invalid_json'}, status=400)
    order_id, telegram_id = payload.get('order_id'), payload.get('telegram_id')
    if not isinstance(order_id, str) or not order_id or not isinstance(telegram_id, int):
        return web.json_response({'ok': False, 'reason': 'bad_params'}, status=400)
    try:
        from bot.services.payment_completion import _run_key_setup_without_delivery
        result = await _run_key_setup_without_delivery(order_id, telegram_id=telegram_id)
    except Exception as error:
        logger.exception('Mognu admin fix-order failed order=%s: %s', order_id, type(error).__name__)
        return web.json_response({'ok': False, 'reason': 'internal_error'}, status=500)
    status = getattr(getattr(result, 'status', None), 'value', getattr(result, 'status', None))
    error_code = getattr(result, 'error_code', None)
    return web.json_response({'ok': not error_code, 'status': str(status), 'key_id': getattr(result, 'key_id', None),
                              'error_code': error_code})


async def _mognu_admin_key_sync_handler(request: web.Request) -> web.Response:
    """''' + MARK + ''': push the key's expiry and limits from the database to the panel."""
    if not _check_secret(request):
        return web.json_response({'ok': False, 'reason': 'forbidden'}, status=403)
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({'ok': False, 'reason': 'invalid_json'}, status=400)
    key_id = payload.get('key_id')
    if not isinstance(key_id, int):
        return web.json_response({'ok': False, 'reason': 'bad_params'}, status=400)
    try:
        from bot.services.vpn_api import push_key_to_panel
        ok = await push_key_to_panel(key_id)
    except Exception as error:
        logger.warning('Mognu admin key-sync failed key=%s: %s', key_id, type(error).__name__)
        return web.json_response({'ok': False, 'reason': 'panel_error'}, status=502)
    return web.json_response({'ok': bool(ok)})


'''


def step(title):
    print(("ПРИМЕНЯЮ: " if APPLY else "ИЗМЕНИТСЯ: ") + title)


def backup(path):
    dst = path.with_name(path.name + ".bak-adminmognu")
    if not dst.exists():
        shutil.copy2(path, dst)
    return dst


# 1. роутер и main.py
for p in (MAIN, BOT, HERE / "admin_mognu.py", HERE / "router_links.py"):
    if not p.exists():
        sys.exit(f"Не нашёл {p} — ничего не менял.")
step(f"{ROUTER} ← admin_mognu.py, {LINKS.name} ← router_links.py")
if APPLY:
    shutil.copyfile(HERE / "router_links.py", LINKS)
    py_compile.compile(str(LINKS), doraise=True)
    shutil.copyfile(HERE / "admin_mognu.py", ROUTER)
    py_compile.compile(str(ROUTER), doraise=True)

main = MAIN.read_text(encoding="utf-8")
if "pamir_admin_mognu" in main:
    print("main.py уже подключает новую админку — не трогаю.")
elif main.count(MAIN_ANCHOR) != 1:
    sys.exit("В main.py нет строки app.include_router(pamir_admin_extra.router) — ничего не менял в main.py и боте.")
else:
    step("main.py: подключить pamir_admin_mognu после pamir_admin_extra")
    if APPLY:
        print("  копия:", backup(MAIN))
        MAIN.write_text(main.replace(MAIN_ANCHOR, MAIN_NEW, 1), encoding="utf-8")
        py_compile.compile(str(MAIN), doraise=True)

# 1б. отметки «откуда заходят и платят» (телефон, компьютер, Telegram, браузер)
main = MAIN.read_text(encoding="utf-8")
TRACK_ANCHOR = "app.include_router(pamir_admin_mognu.router)\n"
if "track_clients" in main:
    print("main.py уже отмечает, откуда заходят, — не трогаю.")
elif TRACK_ANCHOR in main or APPLY:
    step("main.py: отметки, с чего заходят и платят (pamir_admin_mognu.track_clients)")
    if APPLY:
        main = MAIN.read_text(encoding="utf-8")
        if main.count(TRACK_ANCHOR) != 1:
            sys.exit("Не нашёл подключение pamir_admin_mognu в main.py — отметки не включены.")
        dst = MAIN.with_name("main.py.bak-adminclients")
        if not dst.exists():
            shutil.copy2(MAIN, dst)
        print("  копия:", dst)
        MAIN.write_text(main.replace(TRACK_ANCHOR, TRACK_ANCHOR + "pamir_admin_mognu.track_clients(app)\n", 1), encoding="utf-8")
        py_compile.compile(str(MAIN), doraise=True)
else:
    step("main.py: отметки, с чего заходят и платят (после подключения роутера)")

# 1в. ссылки для роутера (тариф «На весь дом»)
main = MAIN.read_text(encoding="utf-8")
USER_ANCHOR = "pamir_admin_mognu.track_clients(app)\n"
if "pamir_admin_mognu.user_router" in main:
    print("main.py уже подключает ссылки для роутера — не трогаю.")
elif USER_ANCHOR in main or APPLY:
    step("main.py: ссылки для роутера (pamir_admin_mognu.user_router)")
    if APPLY:
        main = MAIN.read_text(encoding="utf-8")
        if main.count(USER_ANCHOR) != 1:
            sys.exit("Не нашёл pamir_admin_mognu.track_clients(app) в main.py — ссылки для роутера не подключены.")
        dst = MAIN.with_name("main.py.bak-routerlinks")
        if not dst.exists():
            shutil.copy2(MAIN, dst)
        print("  копия:", dst)
        MAIN.write_text(main.replace(USER_ANCHOR, USER_ANCHOR + "app.include_router(pamir_admin_mognu.user_router)\n", 1), encoding="utf-8")
        py_compile.compile(str(MAIN), doraise=True)
else:
    step("main.py: ссылки для роутера (после подключения админки)")

# 2. бот
bot = BOT.read_text(encoding="utf-8")
if MARK in bot:
    print("Бот уже знает адреса новой админки — не трогаю.")
elif bot.count(BOT_ROUTE_ANCHOR) != 1 or bot.count(BOT_FUNC_ANCHOR) != 1 or "_run_key_setup_without_delivery" not in (
        BOT.parent / "payment_completion.py").read_text(encoding="utf-8"):
    sys.exit("mini_app_api.py или payment_completion.py отличаются от ожидаемого — бот не тронут (бэкенд уже обновлён, если было --apply).")
else:
    step("mini_app_api.py: /mognu-admin/fix-order и /mognu-admin/key-sync")
    if APPLY:
        print("  копия:", backup(BOT))
        new = bot.replace(BOT_ROUTE_ANCHOR, BOT_ROUTE_NEW, 1).replace(BOT_FUNC_ANCHOR, BOT_FUNC + BOT_FUNC_ANCHOR, 1)
        BOT.write_text(new, encoding="utf-8")
        try:
            py_compile.compile(str(BOT), doraise=True)
        except py_compile.PyCompileError as error:
            shutil.copy2(BOT.with_name(BOT.name + ".bak-adminmognu"), BOT)
            sys.exit(f"Ошибка синтаксиса в боте, вернул копию: {error}")

print("Готово. Перезапустите: systemctl restart yadreno-vpn pamir-backend" if APPLY else "Это был просмотр. Чтобы применить: python3 patch_admin_mognu.py --apply")
