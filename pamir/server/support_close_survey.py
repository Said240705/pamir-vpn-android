#!/usr/bin/env python3
"""Только чтение: откуда сообщение «Обращение №… закрыто. Если вопрос остался — просто напишите снова» и как
устроены кнопки поддержки — чтобы заменить его на понятное с кнопкой «Написать в поддержку».

    python3 support_close_survey.py > /root/support_close.txt; wc -l /root/support_close.txt
"""
import re
import sqlite3
from pathlib import Path

BOT = Path("/root/YadrenoVPN")
DB = BOT / "database" / "vpn_bot.db"
LONG = re.compile(r"(?<![\w/.-])[A-Za-z0-9_\-:]{40,}(?![\w/.-])")
FILES = [p for p in sorted((BOT / "bot").rglob("*.py")) + sorted((BOT / "database").rglob("*.py"))
         if "venv" not in p.parts and ".bak" not in p.name]


def section(t):
    print(f"\n===== {t}")


def func(path, name, limit=60):
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
        print("\n".join(LONG.sub("***", x) for x in out))
        return


section("тексты в базе со словами «закрыто» / «напишите снова»")
conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
for table, key in (("pages", "page_key"), ("user_ui_texts", "text_key")):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    for r in conn.execute(f"SELECT * FROM {table}"):
        row = dict(zip(cols, r))
        blob = " ".join(str(row.get(c) or "") for c in ("text_default", "text_custom"))
        if re.search(r"закрыт|напишите снова", blob, re.I):
            print(f"\n  {table}.{row[key]}")
            for c in ("text_default", "text_custom", "buttons_default", "buttons_custom", "text_format", "description"):
                if c in row and row[c]:
                    print(f"    {c}: {str(row[c])[:400]}")

section("в коде")
for f in FILES:
    for i, l in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines()):
        if re.search(r"напишите снова|support_closed|thread_closed|close.*page_key|page_key=.support", l):
            print(f"  {f.relative_to(BOT)}:{i + 1}: {LONG.sub('***', l.strip())[:170]}")

section("кнопки поддержки (keyboards/support.py)")
kb = BOT / "bot" / "keyboards" / "support.py"
if kb.exists():
    print(LONG.sub("***", kb.read_text(encoding="utf-8", errors="replace"))[:5000])

section("обработчики кнопок поддержки у пользователя")
us = BOT / "bot" / "handlers" / "user" / "support.py"
for n in ("_start_support_dialog", "support_start_callback", "support_reply_callback"):
    func(us, n, 50)

section("как обращение закрывается и что отправляется человеку")
for f in FILES:
    text = f.read_text(encoding="utf-8", errors="replace")
    for n in re.findall(r"^(?:async )?def (\w*close\w*)\(", text, re.M):
        if "support" in f.name or "support" in n:
            func(f, n, 50)
