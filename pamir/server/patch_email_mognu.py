#!/usr/bin/env python3
"""Письма в стиле Mognu: перекрашивает шаблон писем (patch_email_design.py) — код входа и сброс пароля.

    python3 patch_email_mognu.py          применить (копия mailer.py.bak-mognumail, проверка синтаксиса, откат при ошибке)
    python3 patch_email_mognu.py rollback вернуть mailer.py из копии

Шапка: почти чёрная с фиолетовым свечением, логотип с короной, «Mog·nu» с лаймовым «nu».
Тело светлое (письма читают и в светлой, и в тёмной почте), ссылки фиолетовые, код — в лаймовой рамке,
кнопка «Задать новый пароль» — лаймовая с тёмным текстом. Подпись: mognu.app, «быстрее, чем моргнёшь».
Работает и до, и после mognu_texts.py. Повторный запуск ничего не меняет.
После: systemctl restart pamir-backend
"""
import py_compile
import re
import shutil
import sys
from pathlib import Path

MAILER = Path(sys.argv[2] if len(sys.argv) > 2 else "/root/pamir-vpn-miniapp/backend/mailer.py")
BAK = MAILER.with_name(MAILER.name + ".bak-mognumail")
MODE = sys.argv[1] if len(sys.argv) > 1 else "apply"

if MODE == "rollback":
    if not BAK.exists():
        sys.exit("Нет копии mailer.py.bak-mognumail — нечего возвращать.")
    shutil.copy2(BAK, MAILER)
    sys.exit("Возвращено. Перезапустите: systemctl restart pamir-backend")

src = MAILER.read_text(encoding="utf-8")
if "Mognu mail" in src:
    sys.exit("Письма уже в стиле Mognu — ничего не меняю.")
if "_pamir_layout" not in src:
    sys.exit("Не нашёл шаблон писем (patch_email_design.py) — ничего не меняю.")

# literal swaps inside the e-mail template (these values occur only there)
SWAPS = [
    ('PAMIR_MAIL_LOGO = "https://app.pamirlink.ru/assets/logo.png"', 'PAMIR_MAIL_LOGO = "https://mognu.app/assets/logo.png"  # Mognu mail'),
    ('PAMIR_MAIL_SITE = "https://app.pamirlink.ru"', 'PAMIR_MAIL_SITE = "https://mognu.app"'),
    ('>app.pamirlink.ru</a>', '>mognu.app</a>'),
    ('background:#0B1622;background-image:radial-gradient(circle at 15% 0%,rgba(43,239,192,0.28),rgba(11,22,34,0) 60%);',
     'background:#09090F;background-image:radial-gradient(circle at 15% 0%,rgba(139,92,255,0.45),rgba(9,9,15,0) 62%);'),
    ('style="display:block;border:0;">', 'style="display:block;border:0;border-radius:10px;">'),
    ('background:#F1FBF8;border:2px solid #2BEFC0;', 'background:#F7FFE6;border:2px solid #A3E000;'),
    ('background:#17B896;background-image:linear-gradient(160deg,#2BEFC0,#17B896);', 'background:#C8FF2E;background-image:linear-gradient(160deg,#D8FF5A,#A3E000);'),
    ('color:#05241D;text-decoration:none;">Задать', 'color:#0A0A10;text-decoration:none;">Задать'),
    ('#0B8F70', '#6A3DF5'),     # links
    ('#EEF2F6', '#F4F3F8'),     # page and chip background
    ('#0E1A28', '#12111A'),     # main text
    ('#4A5B6C', '#4F4C63'),     # secondary text
    ('#6B7B8C', '#6E6B82'),     # footer text
    ('#8A99A8', '#8E8BA3'),
    ('#E3E9EF', '#E5E2EE'),     # divider
    ('rgba(14,26,40,0.08)', 'rgba(18,17,26,0.08)'),
    ('<title>Pamir VPN</title>', '<title>Mognu</title>'),
    ('<title>Mognu</title>', '<title>Mognu</title>'),
]
new = src
for a, b in SWAPS:
    new = new.replace(a, b)
# header wordmark: «Pamir VPN» (or «Mognu VPN» after mognu_texts.py) → Mog + lime «nu»
new = re.sub(r'(?:Pamir|Mognu) <span style="color:#2BEFC0;">VPN</span>', 'Mog<span style="color:#C8FF2E;">nu</span>', new)
# footer line and any remaining product name inside the template
new = re.sub(r'© (?:Pamir VPN|Mognu) — [^<\n]*', '© Mognu — быстрее, чем моргнёшь', new)
new = new.replace('Pamir VPN', 'Mognu')

if new == src or "Mognu mail" not in new:
    sys.exit("Шаблон отличается от ожидаемого — ничего не меняю.")
shutil.copy2(MAILER, BAK)
MAILER.write_text(new, encoding="utf-8")
try:
    py_compile.compile(str(MAILER), doraise=True)
except py_compile.PyCompileError as error:
    shutil.copy2(BAK, MAILER)
    sys.exit(f"Ошибка синтаксиса, вернул копию: {error}")
print(f"Готово: {MAILER} (копия: {BAK}). Перезапустите: systemctl restart pamir-backend")
