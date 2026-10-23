#!/usr/bin/env python3
"""Только чтение: как бот применяет скидку (active_promo_code_id) при покупке — для исправления потерянной скидки.

Случай 003W/003X: код «Последнего шанса» был активен и не использован, но второй заказ через 34 секунды и покупка
с баланса прошли без скидки. Печатает места, где бот берёт активный промокод пользователя, и функции покупки.
Похожее на токены и пароли заменяется на ***.

    python3 promo_survey.py > /root/promo_survey.txt; wc -l /root/promo_survey.txt
"""
import re
from pathlib import Path

BOT = Path("/root/YadrenoVPN")
LONG = re.compile(r"(?<![\w/.-])[A-Za-z0-9_\-:]{40,}(?![\w/.-])")
ASSIGN = re.compile(r"((?:token|secret|password|passwd|api_key|apikey)\w*\s*[=:]\s*)(['\"])[^'\"]{6,}\2", re.I)
FILES = [p for p in sorted((BOT / "bot").rglob("*.py")) + sorted((BOT / "database").rglob("*.py"))
         if "venv" not in p.parts and ".bak" not in p.name]


def clean(line):
    return LONG.sub("***", ASSIGN.sub(lambda m: m.group(1) + m.group(2) + "***" + m.group(2), line))


def section(title):
    print(f"\n===== {title}")


def func_at(path, lines, i, limit):
    """Функция, в которой стоит строка i: от её def до следующего def на том же уровне."""
    start = i
    while start > 0 and not re.match(r"^\s*(async\s+)?def\s", lines[start]):
        start -= 1
    indent = len(lines[start]) - len(lines[start].lstrip())
    out = [lines[start]]
    for l in lines[start + 1:]:
        if l.strip() and len(l) - len(l.lstrip()) <= indent and not l.strip().startswith((")", "]", "}")):
            break
        out.append(l)
        if len(out) >= limit:
            out.append("    …")
            break
    return start, out


section("где бот читает или меняет активный промокод пользователя")
seen = set()
for f in FILES:
    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, l in enumerate(lines):
        if re.search(r"active_promo_code_id|promo_code_id\s*=|discount_percent", l):
            print(f"  {f.relative_to(BOT)}:{i + 1}: {clean(l.strip())[:180]}")

section("функции целиком (до 90 строк), где применяется скидка к заказу")
for f in FILES:
    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, l in enumerate(lines):
        if re.search(r"active_promo_code_id|def .*(promo|discount|price|amount).*\(", l):
            start, body = func_at(f, lines, i, 90)
            key = (f, start)
            if key in seen or not body[0].lstrip().startswith(("def", "async")):
                continue
            seen.add(key)
            text = "\n".join(body)
            if not re.search(r"active_promo_code_id|promo_code_id", text) or len(seen) > 40:
                continue
            print(f"\n-- {f.relative_to(BOT)}:{start + 1}")
            print("\n".join(clean(x) for x in body))

section("покупка и продление из приложения/кабинета (mini_app_api)")
mini = BOT / "bot" / "services" / "mini_app_api.py"
if mini.exists():
    lines = mini.read_text(encoding="utf-8", errors="replace").splitlines()
    for name in ("_purchase_handler", "_renew_handler", "_promo_handler", "_last_chance_offer_handler"):
        for i, l in enumerate(lines):
            if re.match(r"^async def " + name + r"\b", l):
                _, body = func_at(mini, lines, i, 120)
                print(f"\n-- mini_app_api.py:{i + 1}")
                print("\n".join(clean(x) for x in body))
                break
