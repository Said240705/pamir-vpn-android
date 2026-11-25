import sys
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule
from openpyxl.utils import get_column_letter
src, out = sys.argv[1], sys.argv[2]
rows = [r for r in load_workbook(src)["Приложение Android"].iter_rows(min_row=2, values_only=True)]
VIOLET, DEEP, LIME, GOLD, INK = "5A3FB0", "1E1640", "C8FF2E", "FFC93C", "14102A"
thin = Side(style="thin", color="DDD6F3")
wb = Workbook()
# ---- лист 1: как помочь
h = wb.active; h.title = "Как помочь"
h.sheet_view.showGridLines = False
h.column_dimensions["A"].width = 4; h.column_dimensions["B"].width = 100
for r in range(1, 40):
    for c in ("A", "B"): h[f"{c}{r}"].fill = PatternFill("solid", fgColor=DEEP)
lines = [
 ("👑 Mognu VPN — перевод приложения", Font(bold=True, size=22, color=LIME), 40),
 ("Спасибо, что помогаете! Здесь все тексты приложения Mognu для Android.", Font(size=13, color="FFFFFF"), 22),
 ("", None, 10),
 ("Как переводить", Font(bold=True, size=15, color=GOLD), 26),
 ("1. Откройте лист «Перевод». Слева — где в приложении текст и русский оригинал.", Font(size=12, color="FFFFFF"), 20),
 ("2. Пишите перевод в колонку своего языка: English или Шугнанский (кириллица).", Font(size=12, color="FFFFFF"), 20),
 ("3. В колонке «Статус» выберите: Готово / Есть вопрос. В «Кто перевёл» — ваше имя.", Font(size=12, color="FFFFFF"), 20),
 ("4. Сомневаетесь — напишите вопрос в «Комментарий», разберёмся вместе.", Font(size=12, color="FFFFFF"), 20),
 ("", None, 10),
 ("Важно", Font(bold=True, size=15, color=GOLD), 26),
 ("• Всё со знаком $ не переводите и не удаляйте: ${name}, $count — туда приложение подставит имя, число и т. п.", Font(size=12, color="FFFFFF"), 20),
 ("• Эмодзи (👑 🔄 🎄) оставляйте на своих местах.", Font(size=12, color="FFFFFF"), 20),
 ("• Mognu, VPN, LTE, Telegram, Android, iPhone, Windows — не переводятся.", Font(size=12, color="FFFFFF"), 20),
 ("• Кнопки должны остаться короткими: на экране телефона мало места.", Font(size=12, color="FFFFFF"), 20),
 ("• Шугнанский — кириллицей, с буквами ғ, ӯ, ҷ, ӣ и др.", Font(size=12, color="FFFFFF"), 20),
 ("", None, 10),
 ("Пора могнуть! 💚", Font(bold=True, size=14, color=LIME), 24),
]
for i, (txt, font, height) in enumerate(lines, start=2):
    c = h[f"B{i}"]; c.value = txt
    if font: c.font = font
    c.alignment = Alignment(wrap_text=True, vertical="center")
    h.row_dimensions[i].height = height
# ---- лист 2: перевод
ws = wb.create_sheet("Перевод")
head = ["№", "Где в приложении", "Русский", "English", "Шугнанский (кириллица)", "Статус", "Кто перевёл", "Комментарий"]
widths = [6, 22, 48, 48, 48, 14, 16, 30]
ws.append(head)
for col, w in enumerate(widths, 1): ws.column_dimensions[get_column_letter(col)].width = w
for c in ws[1]:
    c.font = Font(bold=True, color="FFFFFF", size=12); c.fill = PatternFill("solid", fgColor=VIOLET)
    c.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
ws["D1"].fill = PatternFill("solid", fgColor="2F5FD0"); ws["E1"].fill = PatternFill("solid", fgColor="B8860B")
ws.row_dimensions[1].height = 34
prev = None
for n, (_, where, ru, _sh) in enumerate(rows, 1):
    ws.append([n, where, ru, "", "", "Не переведено", "", ""])
    r = ws.max_row
    zebra = "F6F3FF" if n % 2 else "FFFFFF"
    for col in range(1, 9):
        c = ws.cell(r, col); c.alignment = Alignment(wrap_text=True, vertical="top"); c.border = Border(bottom=thin)
        if col <= 3: c.fill = PatternFill("solid", fgColor=zebra)
    ws.cell(r, 1).font = Font(color="8D86B5"); ws.cell(r, 2).font = Font(color="5A3FB0", bold=where != prev)
    ws.cell(r, 3).font = Font(color=INK)
    prev = where
last = ws.max_row
dv = DataValidation(type="list", formula1='"Не переведено,Готово,Есть вопрос"', allow_blank=False)
ws.add_data_validation(dv); dv.add(f"F2:F{last}")
for status, color in (("Готово", "D9F99D"), ("Есть вопрос", "FFE8A3"), ("Не переведено", "EEEAF8")):
    ws.conditional_formatting.add(f"F2:F{last}", FormulaRule(formula=[f'$F2="{status}"'], fill=PatternFill("solid", fgColor=color)))
ws.conditional_formatting.add(f"D2:E{last}", FormulaRule(formula=['LEN(D2)>0'], fill=PatternFill("solid", fgColor="F0FDE4")))
ws.freeze_panes = "D2"; ws.auto_filter.ref = f"A1:H{last}"
# ---- лист 3: прогресс
p = wb.create_sheet("Прогресс"); p.sheet_view.showGridLines = False
p.column_dimensions["A"].width = 30; p.column_dimensions["B"].width = 14
p["A1"] = "Сколько уже переведено"; p["A1"].font = Font(bold=True, size=16, color=VIOLET)
data = [("Всего строк", f"=COUNTA(Перевод!C2:C{last})"),
        ("English готово", f"=COUNTA(Перевод!D2:D{last})"),
        ("Шугнанский готово", f"=COUNTA(Перевод!E2:E{last})"),
        ("Со статусом «Есть вопрос»", f'=COUNTIF(Перевод!F2:F{last},"Есть вопрос")')]
for i, (a, b) in enumerate(data, start=3):
    p[f"A{i}"] = a; p[f"B{i}"] = b; p[f"A{i}"].font = Font(size=13); p[f"B{i}"].font = Font(size=13, bold=True)
wb.active = 0
wb.save(out); print(len(rows), "строк ->", out)
