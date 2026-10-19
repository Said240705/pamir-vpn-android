#!/usr/bin/env python3
"""Новогодний сезон Mognu на сервере: скидка на год, адвент-календарь и «Твой год с Mognu».

Что ставит (файлы лежат рядом с этим скриптом):
  • custom_extensions/mognu_newyear.py → /root/YadrenoVPN/custom_extensions/ — скидка при оплате (pricing policy)
    и настройки в админке бота → Расширения: вкл/выкл, процент, даты, «видят заранее» (Telegram ID).
  • mognu_season.py → /root/YadrenoVPN/bot/services/ — цена со скидкой для списков, календарь, итоги года.
Что правит:
  • бот, bot/services/mini_app_api.py: /mini-app-api/tariffs отдаёт sale_price_minor (и принимает telegram_id,
    чтобы «видят заранее» видели скидку в кабинете); новые /mini-app-api/mognu/advent, …/advent/open, …/wrapped,
    …/wrapped/gift (подарок в конце итогов — добавляется и туда, где первая версия патча уже стоит);
  • бот, bot/utils/page_button_items.py: в списке тарифов бота «🎄 было → стало»;
  • бэкенд сайта, routers/topup_router.py: /api/topup/tariffs передаёт telegram_id; /api/topup/mognu/advent,
    …/advent/open, …/wrapped, …/wrapped/gift пересылают боту telegram_id вошедшего человека.

    python3 patch_mognu_newyear.py          показать, что изменится (ничего не меняет)
    python3 patch_mognu_newyear.py --apply  применить (копии рядом, .bak-newyear); при ошибке всё вернётся
    python3 patch_mognu_newyear.py --undo   вернуть файлы из копий и убрать новые
Потом: systemctl restart yadreno-vpn pamir-backend
"""
import os
import py_compile
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get('MOGNU_ROOT', '')   # для проверки на копии: MOGNU_ROOT=/tmp/copy
BOT = ROOT + '/root/YadrenoVPN'
API = BOT + '/bot/services/mini_app_api.py'
ITEMS = BOT + '/bot/utils/page_button_items.py'
SITE = ROOT + '/root/pamir-vpn-miniapp/backend/routers/topup_router.py'
NEW_FILES = [
    (os.path.join(HERE, 'mognu_season.py'), BOT + '/bot/services/mognu_season.py'),
    (os.path.join(HERE, 'custom_extensions', 'mognu_newyear.py'), BOT + '/custom_extensions/mognu_newyear.py'),
]
BAK = '.bak-newyear'
MARK = '# Mognu: New Year season'
GIFT_MARK = '# Mognu: wrapped gift'

# ── бот: адреса ───────────────────────────────────────────────────────────────
API_ROUTE_ANCHOR = "    app.router.add_get('/mini-app-api/tariffs', _tariffs_handler)\n"
API_ROUTE_NEW = API_ROUTE_ANCHOR + (
    "    app.router.add_get('/mini-app-api/mognu/advent', _mognu_advent_handler)  " + MARK + "\n"
    "    app.router.add_post('/mini-app-api/mognu/advent/open', _mognu_advent_open_handler)\n"
    "    app.router.add_get('/mini-app-api/mognu/wrapped', _mognu_wrapped_handler)\n"
)

# ── бот: цена со скидкой в /tariffs ───────────────────────────────────────────
API_TARIFFS_OLD = """            tariffs = [dict(row) for row in rows]
        return web.json_response({'ok': True, 'tariffs': tariffs, 'currency': get_base_currency()})
"""
API_TARIFFS_NEW = """            tariffs = [dict(row) for row in rows]
        # Mognu: New Year sale price next to the regular one (bot/services/mognu_season.py)
        try:
            from bot.services.mognu_season import sale_for, user_id_for_telegram
            sale_user_id = user_id_for_telegram(request.query.get('telegram_id'))
            for tariff in tariffs:
                sale = sale_for(tariff, sale_user_id)
                if sale:
                    tariff.update(sale)
        except Exception as error:
            logger.warning('Mini app tariffs: New Year sale skipped: %s', error)
        return web.json_response({'ok': True, 'tariffs': tariffs, 'currency': get_base_currency()})
"""

# ── бот: обработчики календаря и итогов ───────────────────────────────────────
API_FUNC_ANCHOR = 'async def _tariffs_handler(request: web.Request) -> web.Response:\n'
API_FUNC = '''def _mognu_telegram_id(value):
    """# Mognu: New Year season — the Telegram ID from a query string or JSON, or None."""
    try:
        telegram_id = int(value)
    except (TypeError, ValueError):
        return None
    return telegram_id if telegram_id else None


async def _mognu_advent_handler(request: web.Request) -> web.Response:
    if not _check_secret(request):
        return web.json_response({'ok': False, 'reason': 'forbidden'}, status=403)
    telegram_id = _mognu_telegram_id(request.query.get('telegram_id'))
    if not telegram_id:
        return web.json_response({'ok': False, 'reason': 'telegram_id_required'}, status=400)
    try:
        from bot.services.mognu_season import advent_status
        return web.json_response({'ok': True, **advent_status(telegram_id)})
    except Exception as error:
        logger.exception('Mognu advent status error: %s', error)
        return web.json_response({'ok': False, 'reason': 'internal_error'}, status=500)


async def _mognu_advent_open_handler(request: web.Request) -> web.Response:
    if not _check_secret(request):
        return web.json_response({'ok': False, 'reason': 'forbidden'}, status=403)
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({'ok': False, 'reason': 'invalid_json'}, status=400)
    telegram_id = payload.get('telegram_id')
    if not isinstance(telegram_id, int) or telegram_id == 0:
        return web.json_response({'ok': False, 'reason': 'telegram_id_required'}, status=400)
    try:
        from bot.services.mognu_season import advent_open
        result = await advent_open(telegram_id)
        return web.json_response(result, status=200 if result.get('ok') else 400)
    except Exception as error:
        logger.exception('Mognu advent open error: %s', error)
        return web.json_response({'ok': False, 'reason': 'internal_error'}, status=500)


async def _mognu_wrapped_handler(request: web.Request) -> web.Response:
    if not _check_secret(request):
        return web.json_response({'ok': False, 'reason': 'forbidden'}, status=403)
    telegram_id = _mognu_telegram_id(request.query.get('telegram_id'))
    if not telegram_id:
        return web.json_response({'ok': False, 'reason': 'telegram_id_required'}, status=400)
    try:
        from bot.services.mognu_season import wrapped
        return web.json_response({'ok': True, **wrapped(telegram_id)})
    except Exception as error:
        logger.exception('Mognu wrapped error: %s', error)
        return web.json_response({'ok': False, 'reason': 'internal_error'}, status=500)


'''

# ── подарок в конце итогов: бот и сайт ───────────────────────────────────────
GIFT_ROUTE_ANCHOR = "    app.router.add_get('/mini-app-api/mognu/wrapped', _mognu_wrapped_handler)\n"
GIFT_ROUTE_NEW = GIFT_ROUTE_ANCHOR + (
    "    app.router.add_post('/mini-app-api/mognu/wrapped/gift', _mognu_gift_handler)  " + GIFT_MARK + "\n"
)
GIFT_FUNC = '''async def _mognu_gift_handler(request: web.Request) -> web.Response:
    """# Mognu: wrapped gift — opens the gift at the end of the year in review, once per season."""
    if not _check_secret(request):
        return web.json_response({'ok': False, 'reason': 'forbidden'}, status=403)
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({'ok': False, 'reason': 'invalid_json'}, status=400)
    telegram_id = payload.get('telegram_id')
    if not isinstance(telegram_id, int) or telegram_id == 0:
        return web.json_response({'ok': False, 'reason': 'telegram_id_required'}, status=400)
    try:
        from bot.services.mognu_season import gift_open
        result = await gift_open(telegram_id)
        return web.json_response(result, status=200 if result.get('ok') or result.get('gift') else 400)
    except Exception as error:
        logger.exception('Mognu gift error: %s', error)
        return web.json_response({'ok': False, 'reason': 'internal_error'}, status=500)


'''
SITE_GIFT = '''@router.post("/mognu/wrapped/gift")
async def mognu_wrapped_gift(request: Request, user=Depends(auth.current_user)):
    """# Mognu: wrapped gift"""
    telegram_id = user.get("telegram_id")
    if not telegram_id:
        raise HTTPException(400, "У пользователя нет привязанного Telegram ID")
    enforce_rate_limit(request, "mognu_wrapped_gift", max_requests=10, window_seconds=60)
    data = await _mognu_bot("POST", "/mognu/wrapped/gift", telegram_id, timeout=40)
    if not data.get("ok") and not data.get("gift"):
        return {"ok": False, "reason": data.get("reason") or "failed"}
    return data


'''

# ── бот: цена в кнопках тарифов ───────────────────────────────────────────────
ITEMS_ANCHOR = """        callback_data = (
            f"payment_intent_tariff:{purpose}:{tariff_id}:{int(key_id or 0)}"
        )
"""
ITEMS_NEW = """        """ + MARK + """: New Year sale price (bot/services/mognu_season.py)
        try:
            from bot.services.mognu_season import sale_for
            sale = sale_for(dict(tariff), user_id)
        except Exception:
            sale = None
        if sale:
            from bot.services.promotions import discounted_amount_minor as _mognu_discounted
            sale_minor = int(sale['sale_price_minor'])
            if discount_percent:
                sale_minor = min(sale_minor, _mognu_discounted(price_minor, discount_percent))
            price_text = (
                f"🎄 {format_money_minor(price_minor, currency)} → "
                f"{format_money_minor(sale_minor, currency)}"
            )
""" + ITEMS_ANCHOR

# ── сайт: telegram_id для /tariffs и новые адреса ─────────────────────────────
SITE_TARIFFS_OLD = """                os.getenv("BOT_MINI_APP_TARIFFS_URL", "http://127.0.0.1:8088/mini-app-api/tariffs"),
                headers={"X-Pamir-MiniApp-Secret": MINI_APP_API_SECRET},
"""
SITE_TARIFFS_NEW = """                os.getenv("BOT_MINI_APP_TARIFFS_URL", "http://127.0.0.1:8088/mini-app-api/tariffs"),
                params={"telegram_id": user.get("telegram_id")} if user.get("telegram_id") else None,  """ + MARK + """
                headers={"X-Pamir-MiniApp-Secret": MINI_APP_API_SECRET},
"""
SITE_ROUTE_ANCHOR = '@router.get("/notifications")\n'
SITE_ROUTES = '''async def _mognu_bot(method: str, path: str, telegram_id: int, timeout: int = 20) -> dict:
    """# Mognu: New Year season — one call to the bot's /mini-app-api/mognu/* with the signed-in Telegram ID."""
    url = os.getenv("BOT_MINI_APP_BASE_URL", "http://127.0.0.1:8088/mini-app-api") + path
    headers = {"X-Pamir-MiniApp-Secret": MINI_APP_API_SECRET}
    async with aiohttp.ClientSession() as session:
        try:
            if method == "GET":
                ctx = session.get(url, params={"telegram_id": telegram_id}, headers=headers,
                                  timeout=aiohttp.ClientTimeout(total=timeout))
            else:
                ctx = session.post(url, json={"telegram_id": telegram_id}, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=timeout))
            async with ctx as resp:
                return await resp.json()
        except Exception:
            return {"ok": False, "reason": "bot_unreachable"}


@router.get("/mognu/advent")
async def mognu_advent(user=Depends(auth.current_user)):
    telegram_id = user.get("telegram_id")
    if not telegram_id:
        return {"available": False}
    data = await _mognu_bot("GET", "/mognu/advent", telegram_id)
    return data if data.get("ok") else {"available": False}


@router.post("/mognu/advent/open")
async def mognu_advent_open(request: Request, user=Depends(auth.current_user)):
    telegram_id = user.get("telegram_id")
    if not telegram_id:
        raise HTTPException(400, "У пользователя нет привязанного Telegram ID")
    enforce_rate_limit(request, "mognu_advent_open", max_requests=10, window_seconds=60)
    data = await _mognu_bot("POST", "/mognu/advent/open", telegram_id, timeout=40)
    if not data.get("ok"):
        return {"ok": False, "reason": data.get("reason") or "failed"}
    return data


@router.get("/mognu/wrapped")
async def mognu_wrapped(user=Depends(auth.current_user)):
    telegram_id = user.get("telegram_id")
    if not telegram_id:
        return {"available": False}
    data = await _mognu_bot("GET", "/mognu/wrapped", telegram_id, timeout=40)
    return data if data.get("ok") else {"available": False}


'''


def edits():
    """(path, old text, new text) for every file that is not patched yet."""
    out = []
    api = open(API, encoding='utf-8').read()
    new = api
    if MARK not in api:
        for anchor in (API_ROUTE_ANCHOR, API_TARIFFS_OLD, API_FUNC_ANCHOR):
            if api.count(anchor) != 1:
                sys.exit(f'Бот (mini_app_api.py): не нашёл место для правки «{anchor.strip()[:60]}…» '
                         f'(совпадений {api.count(anchor)}). Файл менялся — пришли его Claude.')
        new = (api.replace(API_ROUTE_ANCHOR, API_ROUTE_NEW).replace(API_TARIFFS_OLD, API_TARIFFS_NEW)
               .replace(API_FUNC_ANCHOR, API_FUNC + API_FUNC_ANCHOR))
    if GIFT_MARK not in new:
        for anchor in (GIFT_ROUTE_ANCHOR, API_FUNC_ANCHOR):
            if new.count(anchor) != 1:
                sys.exit(f'Бот (mini_app_api.py): не нашёл место для подарка «{anchor.strip()[:60]}…» '
                         f'(совпадений {new.count(anchor)}). Пришли файл Claude.')
        new = new.replace(GIFT_ROUTE_ANCHOR, GIFT_ROUTE_NEW).replace(API_FUNC_ANCHOR, GIFT_FUNC + API_FUNC_ANCHOR)
    if new != api:
        out.append((API, api, new))
    items = open(ITEMS, encoding='utf-8').read()
    if MARK not in items:
        if items.count(ITEMS_ANCHOR) != 1:
            sys.exit(f'Бот (page_button_items.py): не нашёл место для правки (совпадений {items.count(ITEMS_ANCHOR)}).')
        out.append((ITEMS, items, items.replace(ITEMS_ANCHOR, ITEMS_NEW)))
    site = open(SITE, encoding='utf-8').read()
    new_site = site
    if MARK not in site:
        for anchor in (SITE_TARIFFS_OLD, SITE_ROUTE_ANCHOR):
            if site.count(anchor) != 1:
                sys.exit(f'Сайт (topup_router.py): не нашёл место для правки «{anchor.strip()[:60]}…» '
                         f'(совпадений {site.count(anchor)}).')
        for need in ('from rate_limit import enforce_rate_limit', 'Request'):
            if need not in site:
                sys.exit(f'Сайт (topup_router.py): нет «{need}» — файл менялся, пришли его Claude.')
        new_site = (site.replace(SITE_TARIFFS_OLD, SITE_TARIFFS_NEW)
                    .replace(SITE_ROUTE_ANCHOR, SITE_ROUTES + SITE_ROUTE_ANCHOR))
    if GIFT_MARK not in new_site:
        if new_site.count(SITE_ROUTE_ANCHOR) != 1 or '_mognu_bot(' not in new_site:
            sys.exit('Сайт (topup_router.py): не нашёл место для подарка — пришли файл Claude.')
        new_site = new_site.replace(SITE_ROUTE_ANCHOR, SITE_GIFT + SITE_ROUTE_ANCHOR)
    if new_site != site:
        out.append((SITE, site, new_site))
    return out


def undo():
    for path in (API, ITEMS, SITE):
        if os.path.exists(path + BAK):
            shutil.copy2(path + BAK, path)
            print(f'вернул {path}')
    for _, dst in NEW_FILES:
        if os.path.exists(dst):
            os.remove(dst)
            print(f'убрал {dst}')
    print('Перезапусти: systemctl restart yadreno-vpn pamir-backend')


def main():
    if '--undo' in sys.argv:
        return undo()
    for src, _ in NEW_FILES:
        if not os.path.exists(src):
            sys.exit(f'Нет файла {src} — скачай его рядом со скриптом.')
    changes = edits()
    new_files = [(s, d) for s, d in NEW_FILES
                 if not os.path.exists(d) or open(s, 'rb').read() != open(d, 'rb').read()]
    if not changes and not new_files:
        print('Уже применён — ничего не делаю.'); return
    if '--apply' not in sys.argv:
        print('Будут изменены:\n' + '\n'.join(f'  {p}' for p, _, _ in changes)
              + '\nБудут поставлены:\n' + '\n'.join(f'  {d}' for _, d in new_files)
              + '\nЧтобы применить: --apply'); return
    done = []
    try:
        for path, old, new in changes:
            if not os.path.exists(path + BAK):   # the copy from before the first version of this patch stays for --undo
                shutil.copy2(path, path + BAK)
            done.append((path, old))
            open(path, 'w', encoding='utf-8').write(new)
            py_compile.compile(path, doraise=True)
        for src, dst in new_files:
            if os.path.exists(dst):
                shutil.copy2(dst, dst + BAK)
            shutil.copy2(src, dst)
            py_compile.compile(dst, doraise=True)
    except Exception as error:
        for path, old in done:
            open(path, 'w', encoding='utf-8').write(old)
        sys.exit(f'Ошибка, вернул правки как были: {error}')
    print('Готово. Копии: *' + BAK + '\nПерезапусти: systemctl restart yadreno-vpn pamir-backend\n'
          'Потом админка бота → Расширения → mognu_newyear: впиши свой Telegram ID в «Видят заранее».')


if __name__ == '__main__':
    main()
