import re, glob, os, sys
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
SRC = "/home/user/pamir-vpn-android/pamir/src"
WHERE = {
 "Home":"Главный экран","HomeHeader":"Главный экран","HomeNotice":"Главный экран","Settings":"Настройки","ServerCard":"Главный экран",
 "StubCard":"Главный экран","WhitelistCard":"Главный экран","SpeedLine":"Главный экран","AdsLine":"Главный экран",
 "toggle":"Подключение","startVpn":"Подключение","fetchIp":"Подключение","selectServer":"Подключение","pickBest":"Подключение",
 "updateSubscription":"Обновление серверов","importFromClipboard":"Добавление подписки","checkAppUpdate":"Обновление приложения",
 "Root":"Навигация","TvFooter":"Телевизор",
}
WHERE.update({
 "AppsScreen":"Приложения без VPN","AutopayCard":"Кабинет: автоплатёж","BalanceCard":"Кабинет: баланс","CabinetScreen":"Кабинет",
 "CardOffer":"Кабинет: привязка карты","CardUnlinkSheet":"Кабинет: отвязка карты","DevicesCard":"Кабинет: устройства",
 "EmailCodeStep":"Вход по почте","EmailLoginSheet":"Вход по почте","HomeCard":"Кабинет","KeyCard":"Кабинет: ключ",
 "KeyPickerSheet":"Выбор ключа","NewsSheet":"Новости","NoKeyHome":"Главный экран (нет ключа)","OnboardingActions":"Первый запуск",
 "OnboardingIntro":"Первый запуск","PamirApi":"Ошибки связи","PamirTheme":"Оформление","PaymentsCard":"Кабинет: платежи",
 "PromoCard":"Кабинет: промокод","ReferralCard":"Кабинет: пригласить друга","RenameKeySheet":"Переименование ключа",
 "RenewContent":"Продление и тарифы","RenewSheet":"Продление и тарифы","ReportSheet":"Сообщить о проблеме",
 "RequiredUpdate":"Обязательное обновление","ServerItem":"Список серверов","ServerSheet":"Список серверов",
 "TopupSheet":"Пополнение баланса","TrialCard":"Пробный период","UpdateSheet":"Обновление приложения",
 "activateTrial":"Пробный период","afterPurchase":"Оплата","agoText":"Время («минуту назад»)","applyAppsIfChanged":"Приложения без VPN",
 "applyDeviceKey":"Выбор ключа","applyLastChance":"Предложения","applyPromo":"Кабинет: промокод","ask":"Поддержка: частые вопросы",
 "askNotifications":"Разрешение на уведомления","bindCard":"Кабинет: привязка карты","closeTicket":"Поддержка","connectedFor":"Главный экран",
 "copyText":"Копирование","finishEmailLogin":"Вход по почте","fmtBytes":"Скорость и трафик","forgotPassword":"Вход по почте",
 "greet":"Главный экран: приветствие","homeToggle":"Главный экран","installUpdate":"Обновление приложения","keyExpiry":"Кабинет: ключ",
 "keyName":"Кабинет: ключ","loginEmail":"Вход по почте","loginTelegram":"Вход через Telegram","mbit":"Скорость и трафик",
 "onLoggedIn":"Вход","onReceive":"Подключение","onResume":"Главный экран","openUrl":"Открытие ссылок","pay":"Оплата",
 "pingText":"Список серверов","proxyPort":"Подключение","registerEmail":"Регистрация по почте","reloadServers":"Список серверов",
 "removeDevice":"Кабинет: устройства","renameKey":"Переименование ключа","resendEmailCode":"Вход по почте","sendReport":"Сообщить о проблеме",
 "sendSupport":"Поддержка","shareKey":"Кабинет: поделиться ключом","signOut":"Выход из аккаунта","toggleAutoRenew":"Кабинет: автоплатёж",
 "toggleFavorite":"Список серверов","topUp":"Пополнение баланса","unlinkCard":"Кабинет: отвязка карты","verifyEmailCode":"Вход по почте",
 "watchLteReturn":"Подключение","watchPayment":"Оплата","setAds":"Без рекламы","—":"Разное",
})
cyr = re.compile(r"[А-Яа-яЁё]")
lit = re.compile(r'"((?:[^"\\]|\\.)*)"')
rows, seen = [], {}
for f in sorted(glob.glob(os.path.join(SRC, "*.kt"))):
    fn = "—"; name = os.path.basename(f)[:-3]
    for i, line in enumerate(open(f, encoding="utf-8"), 1):
        m = re.search(r"\bfun\s+(?:[A-Za-z_.<>]+\.)?([A-Za-z_][A-Za-z0-9_]*)\s*\(", line)
        if m: fn = m.group(1)
        st = line.strip()
        if st.startswith(("//", "*", "/*")) or "Log." in line: continue
        code = line.split("//")[0] if '"' not in line.split("//")[-1] else line
        for s in lit.findall(code):
            if not cyr.search(s): continue
            key = s
            where = WHERE.get(fn, fn)
            if name != "PamirActivity": where = {"PamirWatch":"Уведомления","PamirNews":"Новости","PamirSeason":"Новый год",
                "PamirSupport":"Поддержка","PamirOffers":"Предложения","PamirUpdater":"Обновление приложения","PamirPay":"Оплата",
                "PamirAds":"Без рекламы","PamirApi":"Ошибки связи","PamirTheme":"Оформление","PamirTv":"Телевизор","QSTileService":"Плитка в шторке","WidgetProvider":"Виджет"}.get(name, name)
            if key in seen: continue
            seen[key] = True
            rows.append((where, s.replace('\\n', '\n').replace('\\"', '"')))
wb = Workbook(); ws = wb.active; ws.title = "Приложение Android"
ws.append(["№", "Где в приложении", "Русский", "Шугнанский (кириллица)"])
for c in ws[1]: c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="5A3FB0"); c.alignment = Alignment(vertical="center")
for n, (w, s) in enumerate(rows, 1):
    ws.append([n, w, s, ""])
for col, wdt in zip("ABCD", (6, 22, 60, 60)): ws.column_dimensions[col].width = wdt
for r in ws.iter_rows(min_row=2):
    for c in r: c.alignment = Alignment(wrap_text=True, vertical="top")
ws.freeze_panes = "C2"
h = wb.create_sheet("Как заполнять")
for line in [
 "Как заполнять таблицу",
 "",
 "1. Пишите перевод в колонку «Шугнанский (кириллица)» напротив русской строки.",
 "2. Всё в фигурных скобках со знаком $ оставляйте как есть, не переводите и не удаляйте: ${name}, $count и т. п. — туда приложение подставит имя сервера, число и т. д.",
 "3. Эмодзи (👑, 🔄, 🎄) оставляйте на своих местах.",
 "4. Названия Mognu, LTE, VPN, Telegram, Android, iPhone, Windows не переводятся.",
 "5. Строки короткие (кнопки) должны остаться короткими: на экране телефона мало места.",
 "6. Если строка непонятна, оставьте пустой и отметьте — разберём.",
]:
    h.append([line])
h.column_dimensions["A"].width = 120; h["A1"].font = Font(bold=True, size=14)
out = sys.argv[1]; wb.save(out); print(len(rows), "строк ->", out)
