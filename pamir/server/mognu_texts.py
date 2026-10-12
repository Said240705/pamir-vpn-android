#!/usr/bin/env python3
"""Тексты бота и писем: «Pamir VPN» → «Mognu». Меняются только строки, которые видят люди.

    python3 mognu_texts.py          показать каждую замену (файл:строка, было → стало), ничего не меняет
    python3 mognu_texts.py apply    применить; копии *.bak-mognu, проверка синтаксиса, при ошибке — откат файла
    python3 mognu_texts.py rollback вернуть все файлы из *.bak-mognu

Правила (только внутри строковых литералов Python, комментарии и имена в коде не трогаются):
  • «Pamir VPN» / «Памир VPN» → «Mognu» (слитное «PamirVPN-Android» — метка приложения для сервера, не трогается);
  • описания модулей и функций (docstring) не трогаются — их видят только разработчики;
  • отдельное слово «Pamir» / «Памир» → «Mognu» — только в строках с русским текстом (сообщения людям),
    служебные строки вроде логов и ключей настроек остаются как есть;
  • ссылки на страницы сайта (кабинет, лендинг, iPhone) → https://mognu.app/…;
    API, APK, страница возврата из оплаты и юзернейм бота @pamirlink_bot не меняются.
После apply: systemctl restart yadreno-vpn pamir-backend
Тексты, заданные в админке (приветствие, рассылки), хранятся в базе — их поправить вручную в админке.
"""
import io
import py_compile
import re
import shutil
import sys
import tokenize
from pathlib import Path

ROOTS = [Path('/root/YadrenoVPN/bot'), Path('/root/pamir-vpn-miniapp/backend')]
CYR = re.compile('[А-Яа-яЁё]')
# only with a space: «PamirVPN-Android/» is the app's User-Agent the server checks — must stay
PHRASE = re.compile(r'Pamir VPN|Памир VPN|PAMIR VPN')
WORD = re.compile(r'(?<![\w/.@-])(Pamir|Памир)(?![\w_.-])')
PAGES = [('https://app.pamirlink.ru/index.html', 'https://mognu.app/index.html'),
         ('https://app.pamirlink.ru/welcome.html', 'https://mognu.app/welcome.html'),
         ('https://app.pamirlink.ru/iphone.html', 'https://mognu.app/iphone.html')]


def fix_string(tok: str) -> str:
    new = PHRASE.sub('Mognu', tok)
    if CYR.search(new):
        new = WORD.sub('Mognu', new)
    for a, b in PAGES:
        new = new.replace(a, b)
    if 'Mognu' in new:
        new = new.replace('🏔', '👑')  # mountains belonged to Pamir; the crown is Mognu's
    return new


def plan(path: Path):
    src = path.read_text(encoding='utf-8')
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, SyntaxError):
        return src, []
    lines = src.splitlines(keepends=True)
    changes = []
    # work bottom-up so positions stay valid
    skip = {tokenize.NEWLINE, tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING, tokenize.COMMENT}
    docstrings = set()
    for i, t in enumerate(toks):  # a string that is a whole statement is a docstring: for developers only
        if t.type == tokenize.STRING:
            prev = next((x for x in reversed(toks[:i]) if x.type not in (tokenize.NL, tokenize.COMMENT)), None)
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            if (prev is None or prev.type in skip) and (nxt is None or nxt.type in (tokenize.NEWLINE, tokenize.ENDMARKER)):
                docstrings.add(t.start)
    for t in reversed(toks):
        if t.type != tokenize.STRING and getattr(tokenize, 'FSTRING_MIDDLE', -1) != t.type:
            continue
        if t.start in docstrings:
            continue
        new = fix_string(t.string)
        if new == t.string:
            continue
        (r0, c0), (r1, c1) = t.start, t.end
        if r0 != r1:  # multi-line string: replace inside the joined block
            block = ''.join(lines[r0 - 1:r1])
            start = c0
            end = len(block) - (len(lines[r1 - 1]) - c1)
            block = block[:start] + new + block[end:]
            new_lines = block.splitlines(keepends=True)
            lines[r0 - 1:r1] = new_lines
        else:
            ln = lines[r0 - 1]
            lines[r0 - 1] = ln[:c0] + new + ln[c1:]
        changes.append((r0, t.string.strip()[:90], new.strip()[:90]))
    return ''.join(lines), list(reversed(changes))


def files():
    for root in ROOTS:
        if root.exists():
            for p in sorted(root.rglob('*.py')):
                if '.bak' not in p.name and 'venv' not in p.parts and '__pycache__' not in p.parts:
                    yield p


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'check'
    if mode == 'rollback':
        n = 0
        for root in ROOTS:
            for bak in root.rglob('*.py.bak-mognu'):
                shutil.copy2(bak, bak.with_name(bak.name[:-len('.bak-mognu')])); n += 1
        print(f'Возвращено файлов: {n}. Перезапустите: systemctl restart yadreno-vpn pamir-backend'); return
    total = 0
    for p in files():
        new_src, ch = plan(p)
        if not ch:
            continue
        total += len(ch)
        print(f'\n{p}  ({len(ch)})')
        for r, a, b in ch:
            print(f'  {r}: {a}\n      → {b}')
        if mode == 'apply':
            bak = p.with_name(p.name + '.bak-mognu')
            if not bak.exists():
                shutil.copy2(p, bak)
            p.write_text(new_src, encoding='utf-8')
            try:
                py_compile.compile(str(p), doraise=True)
            except py_compile.PyCompileError as e:
                shutil.copy2(bak, p); print(f'  !! ошибка синтаксиса, файл возвращён: {e}')
    print(f'\nВсего замен: {total}.', 'Применено — перезапустите: systemctl restart yadreno-vpn pamir-backend'
          if mode == 'apply' else 'Это только просмотр. Применить: python3 mognu_texts.py apply')


if __name__ == '__main__':
    main()
