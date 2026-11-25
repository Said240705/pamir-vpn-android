"""Тексты приложения для перевода: шаблоны Kotlin (${...}, $name, %.1f) превращаются в понятные {метки}."""
import re, glob, os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
SRC = "/home/user/pamir-vpn-android/pamir/src"
exec(open(os.path.join(os.path.dirname(__file__), "extract.py")).read().split("cyr = re.compile")[0].split("from openpyxl")[0])  # noqa
WH = {}
src_where = open(os.path.join(os.path.dirname(__file__), "extract.py")).read()
ns = {}; exec("WHERE={}\n" + src_where[src_where.index("WHERE.update("):src_where.index("cyr = re.compile")], ns); WHERE = ns["WHERE"]
FILEWHERE = {"PamirWatch":"Уведомления","PamirNews":"Новости","PamirSeason":"Новый год","PamirSupport":"Поддержка","PamirOffers":"Предложения",
  "PamirUpdater":"Обновление приложения","PamirPay":"Оплата","PamirAds":"Без рекламы","PamirApi":"Ошибки связи","PamirTheme":"Оформление",
  "PamirTv":"Телевизор","QSTileService":"Плитка в шторке","WidgetProvider":"Виджет"}
HINT = {"from":"сервер","to":"сервер","name":"название","n":"число","count":"число","topic":"тема","link":"ссылка","email":"почта","pct":"процент",
        "b":"число","t":"текст","d":"дней","days":"дней","min":"минут","h":"часов","price":"цена","rub":"сумма","balance":"сумма","ip":"адрес",
        "server":"сервер","title":"название","key":"ключ","keyName":"ключ","version":"версия","v":"версия","phrase":"число"}
def hint(expr):
    e = expr.strip()
    for w, h in HINT.items():
        if re.search(r'\b' + re.escape(w) + r'\b', e, re.I): return "{" + h + "}"
    if re.search(r'rub|minor|balance|price|amount', e, re.I): return "{сумма}"
    if re.search(r'name', e, re.I): return "{название}"
    if re.search(r'day|date|ago|time', e, re.I): return "{время}"
    return "{…}"
def strings_in(line):
    """Строковые литералы строки с заменой ${...} (с учётом вложенных скобок и кавычек) на метки."""
    out, i = [], 0
    while i < len(line):
        if line[i] == '"' and not line.startswith('"""', i):
            j, buf = i + 1, []
            while j < len(line) and line[j] != '"':
                if line[j] == '\\' and j + 1 < len(line): buf.append(line[j:j+2]); j += 2; continue
                if line.startswith("${", j):
                    depth, m = 0, j + 1
                    while m < len(line):
                        if line[m] == '{': depth += 1
                        elif line[m] == '}':
                            depth -= 1
                            if depth == 0: break
                        m += 1
                    buf.append(hint(line[j+2:m])); j = m + 1; continue
                mm = re.match(r'\$([A-Za-z_][A-Za-z0-9_]*)', line[j:])
                if mm: buf.append(hint(mm.group(1))); j += len(mm.group(0)); continue
                buf.append(line[j]); j += 1
            out.append("".join(buf)); i = j + 1
        else: i += 1
    return out
cyr = re.compile(r"[А-Яа-яЁё]")
rows, seen = [], set()
for f in sorted(glob.glob(os.path.join(SRC, "*.kt"))):
    fn, name = "—", os.path.basename(f)[:-3]
    for line in open(f, encoding="utf-8"):
        m = re.search(r"\bfun\s+(?:[A-Za-z_.<>]+\.)?([A-Za-z_][A-Za-z0-9_]*)\s*\(", line)
        if m: fn = m.group(1)
        st = line.strip()
        if st.startswith(("//", "*", "/*")) or "Log." in line: continue
        for s in strings_in(line):
            s = re.sub(r'%[-0-9.]*[dfs]', '{число}', s).replace('\\n', '\n').replace('\\"', '"').strip()
            if not cyr.search(s) or len(re.sub(r'\{[^}]*\}|[\s\W\d]', '', s)) < 2: continue
            if s in seen: continue
            seen.add(s)
            where = WHERE.get(fn, fn) if name == "PamirActivity" else FILEWHERE.get(name, name)
            if where and where.isascii(): where = "Разное"
            rows.append((where, s))
json.dump(rows, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(len(rows))
