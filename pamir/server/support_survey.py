#!/usr/bin/env python3
"""Только чтение: куда бот отправляет входящий текст — в поддержку или в автоответ «Всё управление — в личном
кабинете». Нужно, чтобы ответ на сообщение из админки («Написать через бота») попадал в поддержку.

Печатает обработчики текстовых сообщений, работу с обращениями (support_threads) и адрес ответа из админки.
Похожее на токены и пароли заменяется на ***.

    python3 support_survey.py > /root/support_survey.txt; wc -l /root/support_survey.txt
"""
import re
import sqlite3
from pathlib import Path

BOT = Path("/root/YadrenoVPN")
DB = BOT / "database" / "vpn_bot.db"
LONG = re.compile(r"(?<![\w/.-])[A-Za-z0-9_\-:]{40,}(?![\w/.-])")
ASSIGN = re.compile(r"((?:token|secret|password|passwd|api_key|apikey)\w*\s*[=:]\s*)(['\"])[^'\"]{6,}\2", re.I)
FILES = [p for p in sorted((BOT / "bot").rglob("*.py")) + sorted((BOT / "database").rglob("*.py"))
         if "venv" not in p.parts and ".bak" not in p.name]


def clean(line):
    return LONG.sub("***", ASSIGN.sub(lambda m: m.group(1) + m.group(2) + "***" + m.group(2), line))


def section(title):
    print(f"\n===== {title}")


def func(path, name, limit=70):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, l in enumerate(lines):
        m = re.match(r"^(\s*)(async\s+)?def\s+" + re.escape(name) + r"\b", l)
        if not m:
            continue
        indent = len(m.group(1))
        start = i
        while start > 0 and lines[start - 1].strip().startswith("@"):
            start -= 1
        out = lines[start:i + 1]
        for l2 in lines[i + 1:]:
            if l2.strip() and len(l2) - len(l2.lstrip()) <= indent and not l2.strip().startswith((")", "]", "}")):
                break
            out.append(l2)
            if len(out) >= limit:
                out.append("    …")
                break
        print(f"\n-- {path.relative_to(BOT)}:{start + 1}")
        print("\n".join(clean(x) for x in out))
        return True
    return False


# 1. откуда текст «Всё управление — в личном кабинете»
section("где задан автоответ «Всё управление»")
conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
for table, key, cols in (("pages", "page_key", "text_default, text_custom"), ("user_ui_texts", "text_key", "text_default, text_custom")):
    try:
        for r in conn.execute(f"SELECT {key} FROM {table} WHERE ({cols.replace(',', ' LIKE ? OR')} LIKE ?)", ("%Всё управление%",) * 2):
            print(f"  {table}: {r[0]}")
    except sqlite3.Error as e:
        print(f"  {table}: {e}")
for f in FILES:
    for i, l in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines()):
        if "Всё управление" in l or "Все управление" in l:
            print(f"  {f.relative_to(BOT)}:{i + 1}: {clean(l.strip())[:160]}")

# 2. обработчики любого текста и ответы на сообщения
section("обработчики текстовых сообщений (F.text / message без фильтра / reply_to_message)")
names = []
for f in FILES:
    if "handlers" not in f.parts and "services" not in f.parts:
        continue
    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, l in enumerate(lines):
        if re.search(r"@\w+\.message\((\s*\)|F\.text|.*~|.*StateFilter\(None\)|F\.chat)|reply_to_message|router\.message\(\)", l):
            nxt = next((x for x in lines[i + 1:i + 6] if re.match(r"\s*(async\s+)?def ", x)), "")
            print(f"  {f.relative_to(BOT)}:{i + 1}: {clean(l.strip())[:140]}   {nxt.strip()[:100]}")
            m = re.search(r"def (\w+)", nxt)
            if m and "reply_to_message" not in l:
                names.append((f, m.group(1)))

section("эти обработчики целиком")
for f, n in names[:12]:
    func(f, n, 60)

# 3. обращения в поддержку: как бот понимает, что текст — в поддержку
section("функции поддержки (открытое обращение, приём текста пользователя)")
for f in FILES:
    if f.name not in ("support.py", "db_support.py", "extension_support.py"):
        continue
    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    print(f"\n  {f.relative_to(BOT)}: " + " ".join(re.findall(r"^(?:async )?def (\w+)\(", "\n".join(lines), re.M)))
for f in FILES:
    if "handlers" in f.parts and "support" in f.name:
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, l in enumerate(lines):
            if re.search(r"@\w+\.message\(", l):
                nxt = next((x for x in lines[i + 1:i + 6] if re.match(r"\s*(async\s+)?def ", x)), "")
                m = re.search(r"def (\w+)", nxt)
                if m:
                    print(f"  {f.relative_to(BOT)}:{i + 1}: {clean(l.strip())[:160]}")
                    func(f, m.group(1), 60)

# 4. ответ из веб-админки в обращение
section("ответ из админки в обращение (mini_app_api)")
mini = BOT / "bot" / "services" / "mini_app_api.py"
for n in ("_admin_support_reply_handler",):
    func(mini, n, 80)
section("support_threads: статусы и как создаются админом")
print([r for r in conn.execute("SELECT initiator_type, status, COUNT(*) FROM support_threads GROUP BY 1, 2")])
