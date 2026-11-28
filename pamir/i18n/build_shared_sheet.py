"""Таблица перевода под телефон: лист на язык, две широкие колонки «Русский» / «Перевод», разделы — заголовками."""
import json, sys
from collections import OrderedDict
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
rows = json.load(open(sys.argv[1], encoding="utf-8")); out = sys.argv[2]
VIOLET, DEEP, LIME, GOLD, INK = "5A3FB0", "1E1640", "C8FF2E", "FFC93C", "14102A"
groups = OrderedDict()
for n, (where, s) in enumerate(rows, 1): groups.setdefault(where, []).append((n, s))
wb = Workbook()
h = wb.active; h.title = "Начать тут"; h.sheet_view.showGridLines = False; h.sheet_view.zoomScale = 130
h.column_dimensions["A"].width = 46
txt = [("👑 Перевод Mognu", Font(bold=True, size=20, color=LIME), 34),
 ("Спасибо, что помогаете!", Font(size=13, color="FFFFFF"), 20), ("", None, 8),
 ("1. Внизу выберите лист своего языка: «English» или «Шугнанский».", Font(size=13, color="FFFFFF"), 36),
 ("2. Слева русский текст, справа — пишите перевод.", Font(size=13, color="FFFFFF"), 36),
 ("3. Не уверены — поставьте «?» в последней колонке.", Font(size=13, color="FFFFFF"), 36), ("", None, 8),
 ("Важно", Font(bold=True, size=15, color=GOLD), 24),
 ("• {сервер}, {число}, {…} — не переводить: сюда приложение подставит своё. Оставьте их на месте.", Font(size=13, color="FFFFFF"), 52),
 ("• Эмодзи 👑 🔄 оставляйте.", Font(size=13, color="FFFFFF"), 20),
 ("• Mognu, VPN, LTE, Telegram не переводятся.", Font(size=13, color="FFFFFF"), 20),
 ("• Кнопки — коротко, экран маленький.", Font(size=13, color="FFFFFF"), 20),
 ("• Шугнанский — кириллицей: ғ ӯ ҷ ӣ ҳ ќ", Font(size=13, color="FFFFFF"), 20), ("", None, 8),
 ("Пора могнуть! 💚", Font(bold=True, size=14, color=LIME), 22)]
for i, (t, f, ht) in enumerate(txt, 1):
    c = h[f"A{i}"]; c.value = t; c.fill = PatternFill("solid", fgColor=DEEP)
    if f: c.font = f
    c.alignment = Alignment(wrap_text=True, vertical="center"); h.row_dimensions[i].height = ht
for i in range(len(txt) + 1, 60): h[f"A{i}"].fill = PatternFill("solid", fgColor=DEEP)
line = Side(style="thin", color="E4DDF7")
for lang, color in (("English", "2F5FD0"), ("Шугнанский", "B8860B")):
    ws = wb.create_sheet(lang); ws.sheet_view.zoomScale = 120
    for col, w in (("A", 4), ("B", 34), ("C", 34), ("D", 4)): ws.column_dimensions[col].width = w
    ws.column_dimensions["A"].hidden = True   # № строки — для сборки обратно
    ws.append(["№", "Русский", lang, "?"])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF", size=13); c.fill = PatternFill("solid", fgColor=VIOLET)
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws["C1"].fill = PatternFill("solid", fgColor=color); ws.row_dimensions[1].height = 28
    for where, items in groups.items():
        ws.append(["", f"▸ {where}", "", ""]); r = ws.max_row
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
        ws.cell(r, 2).font = Font(bold=True, color=VIOLET, size=12); ws.cell(r, 2).fill = PatternFill("solid", fgColor="EEE9FB")
        ws.row_dimensions[r].height = 22
        for n, s in items:
            ws.append([n, s, "", ""]); r = ws.max_row
            ws.cell(r, 2).font = Font(size=13, color=INK); ws.cell(r, 3).font = Font(size=13, color=INK)
            ws.cell(r, 3).fill = PatternFill("solid", fgColor="FFFBE8")
            for col in (2, 3, 4):
                ws.cell(r, col).alignment = Alignment(wrap_text=True, vertical="top"); ws.cell(r, col).border = Border(bottom=line)
            ws.cell(r, 4).alignment = Alignment(horizontal="center", vertical="top"); ws.cell(r, 4).font = Font(bold=True, color="C0392B", size=13)
            ws.row_dimensions[r].height = max(20, 18 * (1 + len(s) // 30 + s.count("\n")))
    ws.freeze_panes = "B2"
wb.save(out); print(len(rows), "строк,", len(groups), "разделов ->", out)
