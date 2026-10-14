#!/usr/bin/env python3
"""Удаление ключа из личного кабинета: новый адрес бота и бэкенда сайта.

Бот: POST /mini-app-api/keys/delete {telegram_id, key_id} — те же шаги, что «Мои ключи» → удалить
(проверка владельца через get_key_details_for_user, клиент удаляется с панели 3X-UI, ключ — из базы, подписка
пересобирается). В отличие от бота, активный ключ тоже можно удалить: кабинет перед этим явно предупреждает.
Бэкенд сайта: POST /api/topup/keys/delete {key_id} — пересылает боту telegram_id вошедшего человека.

    python3 patch_key_delete.py          показать, что изменится (ничего не меняет)
    python3 patch_key_delete.py --apply  применить (копии файлов рядом, .bak-keydelete)
Потом перезапустить бота и бэкенд сайта.
"""
import py_compile
import shutil
import sys

BOT = '/root/YadrenoVPN/bot/services/mini_app_api.py'
SITE = '/root/pamir-vpn-miniapp/backend/routers/topup_router.py'
MARK = '# Mognu: cabinet key delete'

BOT_ROUTE_ANCHOR = "    app.router.add_post('/mini-app-api/keys/rename', _rename_key_handler)\n"
BOT_ROUTE_NEW = BOT_ROUTE_ANCHOR + "    app.router.add_post('/mini-app-api/keys/delete', _pamir_key_delete_handler)\n"
BOT_FUNC_ANCHOR = 'async def _rename_key_handler(request: web.Request) -> web.Response:\n'
BOT_FUNC = '''async def _pamir_key_delete_handler(request: web.Request) -> web.Response:
    """# Mognu: cabinet key delete — the steps of «Мои ключи» → удалить (owner check, 3X-UI client, DB row,
    subscription cleanup); an active key is allowed too, the cabinet warns before calling this."""
    if not _check_secret(request):
        return web.json_response({'ok': False, 'reason': 'forbidden'}, status=403)
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({'ok': False, 'reason': 'invalid_json'}, status=400)
    telegram_id = payload.get('telegram_id')
    key_id = payload.get('key_id')
    if not isinstance(telegram_id, int) or telegram_id == 0:
        return web.json_response({'ok': False, 'reason': 'telegram_id_required'}, status=400)
    if not isinstance(key_id, int):
        return web.json_response({'ok': False, 'reason': 'key_id_required'}, status=400)
    try:
        from database.requests import get_key_details_for_user, delete_vpn_key
        from bot.services.vpn_api import get_client
        from bot.utils.panel_email import is_managed_panel_email
        key = get_key_details_for_user(key_id, telegram_id)
        if not key:
            return web.json_response({'ok': False, 'reason': 'key_not_found'}, status=404)
        reconcile_host_ids = ()
        try:
            from bot.services.subscription_composition import list_key_subscription_reconcile_host_ids
            reconcile_host_ids = list_key_subscription_reconcile_host_ids(key_id=key_id, include_self=False)
        except Exception as error:
            logger.warning('Cabinet key delete: no reconcile targets key=%s type=%s', key_id, type(error).__name__)
        if key.get('server_id') and is_managed_panel_email(key.get('panel_email')):
            try:
                client = await get_client(key['server_id'])
                await client.delete_client(key['panel_email'])
            except Exception as error:
                logger.warning('Cabinet key delete: panel client not removed key=%s type=%s', key_id, type(error).__name__)
        if not delete_vpn_key(key_id):
            logger.error('Cabinet key delete: database delete failed key=%s', key_id)
            return web.json_response({'ok': False, 'reason': 'delete_failed'}, status=500)
        if reconcile_host_ids:
            try:
                from bot.services.subscription_composition import schedule_subscription_host_reconciles
                schedule_subscription_host_reconciles(host_key_ids=reconcile_host_ids)
            except Exception as error:
                logger.warning('Cabinet key delete: subscription cleanup not scheduled key=%s type=%s',
                               key_id, type(error).__name__)
        logger.info('Cabinet key delete: key=%s active=%s', key_id, bool(key.get('is_active')))
        return web.json_response({'ok': True})
    except Exception as error:
        logger.exception('Cabinet key delete unexpected error: %s', error)
        return web.json_response({'ok': False, 'reason': 'internal_error'}, status=500)


'''

SITE_MODEL_ANCHOR = 'class AutoRenewToggleIn(BaseModel):\n    key_id: int\n    enabled: bool\n'
SITE_MODEL_NEW = SITE_MODEL_ANCHOR + '\n\nclass KeyDeleteIn(BaseModel):  # Mognu: cabinet key delete\n    key_id: int\n'
SITE_ROUTE_ANCHOR = '@router.get("/notifications")\n'
SITE_ROUTE = '''@router.post("/keys/delete")
async def delete_key(payload: KeyDeleteIn, user=Depends(auth.current_user)):
    """# Mognu: cabinet key delete — the bot checks that the key belongs to this person."""
    telegram_id = user.get("telegram_id")
    if not telegram_id:
        raise HTTPException(400, "У пользователя нет привязанного Telegram ID")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                os.getenv("BOT_MINI_APP_KEY_DELETE_URL", "http://127.0.0.1:8088/mini-app-api/keys/delete"),
                json={"telegram_id": telegram_id, "key_id": payload.key_id},
                headers={"X-Pamir-MiniApp-Secret": MINI_APP_API_SECRET},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json()
        except Exception:
            raise HTTPException(502, "Не удалось связаться с сервисом бота")

    if not data.get("ok"):
        raise HTTPException(404 if data.get("reason") == "key_not_found" else 400, "Не удалось удалить ключ")

    return {"status": "ok"}


'''


def plan():
    bot, site = open(BOT, encoding='utf-8').read(), open(SITE, encoding='utf-8').read()
    out = []
    if MARK not in bot:
        for a in (BOT_ROUTE_ANCHOR, BOT_FUNC_ANCHOR):
            if bot.count(a) != 1:
                sys.exit(f'Бот: не нашёл место для правки ({a.strip()[:50]}…, совпадений {bot.count(a)})')
        out.append((BOT, bot.replace(BOT_ROUTE_ANCHOR, BOT_ROUTE_NEW).replace(BOT_FUNC_ANCHOR, BOT_FUNC + BOT_FUNC_ANCHOR)))
    if MARK not in site:
        for a in (SITE_MODEL_ANCHOR, SITE_ROUTE_ANCHOR):
            if site.count(a) != 1:
                sys.exit(f'Сайт: не нашёл место для правки ({a.strip()[:50]}…, совпадений {site.count(a)})')
        out.append((SITE, site.replace(SITE_MODEL_ANCHOR, SITE_MODEL_NEW).replace(SITE_ROUTE_ANCHOR, SITE_ROUTE + SITE_ROUTE_ANCHOR)))
    return out


def main():
    changes = plan()
    if not changes:
        print('Уже применён — ничего не делаю.'); return
    if '--apply' not in sys.argv:
        print('Будут изменены:\n' + '\n'.join(f'  {p}' for p, _ in changes) + '\nЧтобы применить: --apply'); return
    done = []
    for path, text in changes:
        shutil.copy2(path, path + '.bak-keydelete')
        open(path, 'w', encoding='utf-8').write(text)
        done.append(path)
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as e:
            for p in done:
                shutil.copy2(p + '.bak-keydelete', p)
            sys.exit(f'Ошибка компиляции, вернул всё как было: {e}')
    print('Готово. Копии: *.bak-keydelete\nПерезапусти бота и бэкенд сайта.')


if __name__ == '__main__':
    main()
