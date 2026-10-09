#!/usr/bin/env python3
"""Пробный период из приложения и сайта: ключ сразу ставится в панель.

Меняет bot/services/mini_app_api.py, обработчик /mini-app-api/trial-activate (его вызывает
бэкенд кабинета на «Попробовать бесплатно» в приложении и на сайте).

Было: обработчик только записывал пробный ключ в базу (claim_trial_offer создаёт черновик
без сервера) и отвечал «ok». Настройку ключа — выбор сервера и создание клиента в 3x-ui —
делает только кнопка в Telegram-боте, поэтому из приложения ключ оставался черновиком:
в кабинете он есть, в панели нет, подписка пустая, приложению нечего подключать.

Стало: после записи — то же, что бот делает после оплаты из приложения
(_run_key_setup_without_delivery: выбор сервера и создание клиента в панели), плюс
событие key_created, как у пробного периода из бота. Ошибка настройки не ломает ответ:
ключ остаётся в базе, в журнале бота — строка «Pamir trial key setup».

Копия перед изменением: mini_app_api.py.bak-trial. Повторный запуск ничего не меняет.
"""
import py_compile
import shutil
import sys
from pathlib import Path

PATH = Path(sys.argv[1] if len(sys.argv) > 1 else "/root/YadrenoVPN/bot/services/mini_app_api.py")
src = PATH.read_text(encoding="utf-8")
if "_pamir_setup_trial_key" in src:
    sys.exit("Правка уже применена — ничего не меняю.")

OLD = """        result = await activate_trial_offer(user['id'], offer_id)
        if not result.get('ok'):
            return web.json_response({'ok': False, 'reason': result.get('reason') or 'unavailable'}, status=400)
        return web.json_response({'ok': True})
"""
NEW = """        result = await activate_trial_offer(user['id'], offer_id)
        if not result.get('ok'):
            return web.json_response({'ok': False, 'reason': result.get('reason') or 'unavailable'}, status=400)
        await _pamir_setup_trial_key(result, telegram_id=telegram_id, user_id=int(user['id']), offer_id=offer_id)
        return web.json_response({'ok': True})
"""
HANDLER = "async def _trial_activate_handler(request: web.Request) -> web.Response:\n"
HELPER = '''# --- Pamir: пробный ключ из приложения/сайта сразу ставится в панель ---
async def _pamir_setup_trial_key(result, *, telegram_id: int, user_id: int, offer_id: int) -> None:
    """Same as the Telegram trial button: configure the claimed draft key on a server right away."""
    order_id = str(result.get('order_id') or '')
    key_id = result.get('key_id')
    offer = result.get('offer') or {}
    try:
        from bot.services.key_lifecycle import emit_key_lifecycle_event_safe

        await emit_key_lifecycle_event_safe(
            'key_created',
            {
                'key_id': int(key_id),
                'user_id': user_id,
                'tariff_id': int(offer.get('tariff_id') or 0),
                'days': max(0, int(offer.get('duration_days') or 0)),
                'traffic_limit': max(0, int(offer.get('traffic_limit_gb') or 0)) * 1024 ** 3,
                'order_id': order_id,
                'payment_type': 'trial',
                'source': 'trial',
                'trial_offer_id': int(offer_id),
            },
        )
    except Exception as error:
        logger.warning('Pamir trial key lifecycle failed key=%s: %s', key_id, error)
    if not order_id:
        logger.warning('Pamir trial key setup skipped: no order for key=%s', key_id)
        return
    try:
        from bot.services.payment_completion import _run_key_setup_without_delivery

        setup = await _run_key_setup_without_delivery(order_id, telegram_id=telegram_id)
        status = getattr(getattr(setup, 'status', None), 'value', setup)
        logger.info('Pamir trial key setup order=%s key=%s status=%s', order_id, key_id, status)
    except Exception as error:
        logger.exception('Pamir trial key setup failed order=%s key=%s: %s', order_id, key_id, error)


'''

if src.count(OLD) != 1 or src.count(HANDLER) != 1:
    sys.exit("Не нашёл обработчик trial-activate в ожидаемом виде — файл отличается, ничего не меняю.")

backup = PATH.with_name(PATH.name + ".bak-trial")
shutil.copy2(PATH, backup)
new = src.replace(OLD, NEW).replace(HANDLER, HELPER + HANDLER)
PATH.write_text(new, encoding="utf-8")
try:
    py_compile.compile(str(PATH), doraise=True)
except py_compile.PyCompileError as error:
    shutil.copy2(backup, PATH)
    sys.exit(f"Ошибка синтаксиса, вернул копию: {error}")
print(f"Готово: {PATH} (копия: {backup}). Перезапустите бота: systemctl restart yadreno-vpn")
