#!/usr/bin/env python3
"""Ставит в панель ключи, застрявшие черновиками (пробный период из приложения до patch_trial_provision.py).

Запуск — из папки бота его же Python, по паре «заказ:telegram_id» на каждый ключ
(заказ — тот, которым ключ был создан, обычно пробный):

    cd /root/YadrenoVPN && venv/bin/python /root/fix_draft_keys.py 002o:111 002r:222

Делает ровно то, что бот делает после оплаты из приложения (_run_key_setup_without_delivery):
выбирает сервер и создаёт клиента в 3x-ui. Сроки и оплаты не трогает. Для уже настроенного
ключа бот ответит статусом, отличным от provisioning, и ничего не изменит.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.getcwd())


async def main(pairs):
    from bot.services.payment_completion import _run_key_setup_without_delivery

    for pair in pairs:
        order_id, _, tg = pair.partition(":")
        try:
            r = await _run_key_setup_without_delivery(order_id, telegram_id=int(tg))
            status = getattr(getattr(r, "status", None), "value", r)
            print(f"{order_id}: {status} key={getattr(r, 'key_id', '?')} error={getattr(r, 'error_code', None)}")
        except Exception as error:
            print(f"{order_id}: ОШИБКА {type(error).__name__}: {error}")
    try:
        from bot.services.vpn_api import _clients

        for c in list(_clients.values()):
            res = c.close()
            if asyncio.iscoroutine(res):
                await res
    except Exception:
        pass


if __name__ == "__main__":
    if len(sys.argv) < 2 or not os.path.isdir("bot"):
        sys.exit("Запустите из /root/YadrenoVPN: venv/bin/python /root/fix_draft_keys.py ЗАКАЗ:TELEGRAM_ID ...")
    asyncio.run(main(sys.argv[1:]))
