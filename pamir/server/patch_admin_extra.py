#!/usr/bin/env python3
"""Промокоды и аналитика в веб-админке: ставит роутер в бэкенд кабинета.

Копирует admin_extra.py (лежит рядом) в routers/pamir_admin_extra.py и подключает его
в main.py сразу после admin_router. Копия main.py перед изменением: main.py.bak-adminextra.
Повторный запуск обновляет роутер, а main.py второй раз не трогает.
После — systemctl restart pamir-backend.
"""
import shutil
import sys
from pathlib import Path

BACKEND = Path(sys.argv[1] if len(sys.argv) > 1 else "/root/pamir-vpn-miniapp/backend")
HERE = Path(__file__).resolve().parent

shutil.copyfile(HERE / "admin_extra.py", BACKEND / "routers" / "pamir_admin_extra.py")
print("routers/pamir_admin_extra.py — записан")

main = BACKEND / "main.py"
src = main.read_text(encoding="utf-8")
if "pamir_admin_extra" in src:
    sys.exit("main.py уже подключает роутер — не меняю.")
anchor = "app.include_router(admin_router.router)\n"
if anchor not in src:
    sys.exit("Не нашёл в main.py строку app.include_router(admin_router.router) — ничего не менял.")
shutil.copyfile(main, main.with_name("main.py.bak-adminextra"))
src = src.replace(anchor, anchor + "from routers import pamir_admin_extra  # промокоды и аналитика\n"
                  "app.include_router(pamir_admin_extra.router)\n", 1)
main.write_text(src, encoding="utf-8")
print("main.py — роутер подключён (копия: main.py.bak-adminextra)")
