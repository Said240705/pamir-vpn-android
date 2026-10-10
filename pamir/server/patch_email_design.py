#!/usr/bin/env python3
"""Оформленные письма Pamir VPN: код подтверждения и восстановление пароля.

Меняет бэкенд кабинета:
- mailer.py: send_email умеет отправлять HTML (вместе с обычным текстом); добавлен шаблон
  (тёмная шапка с логотипом, светлое тело), письмо с кодом и письмо восстановления пароля
  в этом шаблоне;
- routers/auth_router.py: код подтверждения уходит оформленным письмом,
  тема — «123456 — код для входа в Pamir VPN» (код виден прямо в уведомлении).

Ставить после patch_email_code.py. Копии перед изменением: *.bak-maildesign.
Повторный запуск ничего не меняет.
"""
import py_compile
import shutil
import sys
from pathlib import Path

BACKEND = Path(sys.argv[1] if len(sys.argv) > 1 else "/root/pamir-vpn-miniapp/backend")
MAILER = BACKEND / "mailer.py"
ROUTER = BACKEND / "routers" / "auth_router.py"
m = MAILER.read_text(encoding="utf-8")
r = ROUTER.read_text(encoding="utf-8")
if "pamir_code_email" in m:
    sys.exit("Правка уже применена — ничего не меняю.")
if "_pamir_send_code" not in r:
    sys.exit("Сначала поставьте patch_email_code.py — ничего не меняю.")

OLD_SIG = "async def send_email(to_address: str, subject: str, body_text: str) -> None:"
NEW_SIG = "async def send_email(to_address: str, subject: str, body_text: str, html: str | None = None) -> None:"
OLD_JSON = '                "text": body_text,\n'
NEW_JSON = '                "text": body_text,\n                **({"html": html} if html else {}),\n'
OLD_SEND = '        await mailer.send_email(email, f"Код подтверждения: {code} — Pamir VPN", body)\n'
NEW_SEND = '        subject, html, body = mailer.pamir_code_email(code)\n        await mailer.send_email(email, subject, body, html=html)\n'
for name, src, old in (("send_email", m, OLD_SIG), ("json письма", m, OLD_JSON), ("отправка кода", r, OLD_SEND)):
    if src.count(old) != 1:
        sys.exit(f"Не нашёл «{name}» в ожидаемом виде — файлы отличаются, ничего не меняю.")

TEMPLATE = 'PAMIR_MAIL_LOGO = "https://app.pamirlink.ru/assets/logo.png"\nPAMIR_MAIL_SITE = "https://app.pamirlink.ru"\nPAMIR_MAIL_SUPPORT = "https://t.me/pamirlink_bot"\n\n\ndef _pamir_layout(preheader: str, body_html: str, logo: str = PAMIR_MAIL_LOGO) -> str:\n    return f"""<!doctype html>\n<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n<meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light only"><title>Pamir VPN</title></head>\n<body style="margin:0;padding:0;background:#EEF2F6;-webkit-text-size-adjust:100%;">\n<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:#EEF2F6;">{preheader}&#8199;&#65279;&#847;&#8199;&#65279;&#847;&#8199;&#65279;&#847;</div>\n<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#EEF2F6;">\n<tr><td align="center" style="padding:28px 12px;">\n<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:480px;background:#FFFFFF;border-radius:20px;overflow:hidden;box-shadow:0 6px 24px rgba(14,26,40,0.08);">\n<tr><td style="background:#0B1622;background-image:radial-gradient(circle at 15% 0%,rgba(43,239,192,0.28),rgba(11,22,34,0) 60%);padding:22px 28px;">\n<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>\n<td style="vertical-align:middle;"><img src="{logo}" width="40" height="40" alt="" style="display:block;border:0;"></td>\n<td style="vertical-align:middle;padding-left:12px;font:800 20px/1 \'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;color:#FFFFFF;letter-spacing:-0.2px;">Pamir <span style="color:#2BEFC0;">VPN</span></td>\n</tr></table></td></tr>\n<tr><td style="padding:32px 28px 8px;font-family:\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;color:#0E1A28;">{body_html}</td></tr>\n<tr><td style="padding:8px 28px 28px;font-family:\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;">\n<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-top:1px solid #E3E9EF;"><tr><td style="padding-top:18px;font-size:13px;line-height:20px;color:#6B7B8C;">\n<a href="{PAMIR_MAIL_SUPPORT}" style="color:#0B8F70;font-weight:700;text-decoration:none;">Поддержка в Telegram</a>\n&nbsp;&nbsp;·&nbsp;&nbsp;<a href="{PAMIR_MAIL_SITE}" style="color:#0B8F70;font-weight:700;text-decoration:none;">app.pamirlink.ru</a>\n<br>© Pamir VPN — защищённый интернет в одно касание</td></tr></table>\n</td></tr>\n</table></td></tr></table></body></html>"""\n\n\ndef pamir_code_email(code: str, logo: str = PAMIR_MAIL_LOGO) -> tuple[str, str, str]:\n    spaced = f"{code[:3]}&nbsp;{code[3:]}"\n    body = f"""\n<div style="font-size:24px;line-height:30px;font-weight:800;margin:0 0 8px;">Подтвердите почту</div>\n<div style="font-size:15px;line-height:22px;color:#4A5B6C;margin:0 0 24px;">Введите этот код в приложении Pamir VPN или на сайте:</div>\n<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td align="center" style="background:#F1FBF8;border:2px solid #2BEFC0;border-radius:16px;padding:20px 12px;">\n<div style="font:800 40px/1 \'SF Mono\',Menlo,Consolas,\'Roboto Mono\',monospace;letter-spacing:8px;color:#0E1A28;">{spaced}</div>\n</td></tr></table>\n<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center" style="margin:16px auto 24px;"><tr><td style="background:#EEF2F6;border-radius:999px;padding:7px 14px;font-size:13px;font-weight:700;color:#4A5B6C;">⏱&nbsp; Код действует 15 минут</td></tr></table>\n<div style="font-size:13px;line-height:20px;color:#6B7B8C;margin:0 0 8px;"><b style="color:#4A5B6C;">Это были не вы?</b> Просто проигнорируйте письмо — без кода никто не войдёт в аккаунт.</div>"""\n    text = (f"Ваш код для входа в Pamir VPN: {code}\\n\\nВведите его в приложении или на сайте. Код действует 15 минут.\\n\\n"\n            "Если вы не регистрировались в Pamir VPN — просто проигнорируйте письмо.")\n    return f"{code} — код для входа в Pamir VPN", _pamir_layout("Код действует 15 минут", body, logo), text\n\n\ndef pamir_reset_email(url: str, logo: str = PAMIR_MAIL_LOGO) -> tuple[str, str, str]:\n    body = f"""\n<div style="font-size:24px;line-height:30px;font-weight:800;margin:0 0 8px;">Новый пароль</div>\n<div style="font-size:15px;line-height:22px;color:#4A5B6C;margin:0 0 24px;">Вы запросили сброс пароля для входа в Pamir VPN. Нажмите кнопку, чтобы задать новый:</div>\n<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center" style="margin:0 auto 20px;"><tr><td style="border-radius:14px;background:#17B896;background-image:linear-gradient(160deg,#2BEFC0,#17B896);">\n<a href="{url}" style="display:inline-block;padding:15px 34px;font:800 16px \'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;color:#05241D;text-decoration:none;">Задать новый пароль</a></td></tr></table>\n<div style="font-size:12.5px;line-height:19px;color:#8A99A8;margin:0 0 20px;word-break:break-all;">Кнопка не работает? Откройте ссылку: <a href="{url}" style="color:#0B8F70;">{url}</a></div>\n<div style="font-size:13px;line-height:20px;color:#6B7B8C;margin:0 0 8px;"><b style="color:#4A5B6C;">Это были не вы?</b> Просто проигнорируйте письмо — пароль останется прежним.</div>"""\n    text = (f"Вы запросили сброс пароля для входа в Pamir VPN.\\nЧтобы задать новый пароль, перейдите по ссылке:\\n\\n{url}\\n\\n"\n            "Если вы не запрашивали это — просто проигнорируйте письмо, пароль останется прежним.")\n    return "Восстановление пароля — Pamir VPN", _pamir_layout("Ссылка для нового пароля", body, logo), text\n'
TAIL = """

# --- Pamir: восстановление пароля — оформленным письмом (заменяет функцию выше) ---
async def send_password_reset_email(to_address: str, reset_url: str) -> None:
    subject, html, text = pamir_reset_email(reset_url)
    await send_email(to_address, subject, text, html=html)
"""

backups = []
for p in (MAILER, ROUTER):
    b = p.with_name(p.name + ".bak-maildesign")
    shutil.copy2(p, b)
    backups.append((p, b))
m = m.replace(OLD_SIG, NEW_SIG).replace(OLD_JSON, NEW_JSON) + "\n\n# --- Pamir: шаблон писем ---\n" + TEMPLATE + TAIL
r = r.replace(OLD_SEND, NEW_SEND)
MAILER.write_text(m, encoding="utf-8")
ROUTER.write_text(r, encoding="utf-8")
try:
    for p, _ in backups:
        py_compile.compile(str(p), doraise=True)
except py_compile.PyCompileError as error:
    for p, b in backups:
        shutil.copy2(b, p)
    sys.exit(f"Ошибка синтаксиса, вернул копии: {error}")
print("Готово: письма с кодом и восстановления пароля теперь оформленные.")
print("Перезапустите бэкенд: systemctl restart pamir-backend")
