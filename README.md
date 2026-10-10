<div align="center">

<img src="pamir/docs/logo.png" width="96" alt="Pamir VPN">

# Pamir VPN

**Защищённый интернет в одно касание — приложение для Android и Android TV**

[![Последняя версия](https://img.shields.io/github/v/release/Said240705/pamir-vpn-android?label=версия&color=2BEFC0&labelColor=0B1622)](https://github.com/Said240705/pamir-vpn-android/releases/latest)
[![Скачивания](https://img.shields.io/github/downloads/Said240705/pamir-vpn-android/total?label=скачиваний&color=2BEFC0&labelColor=0B1622)](https://github.com/Said240705/pamir-vpn-android/releases)
![Android](https://img.shields.io/badge/Android-7.0+-2BEFC0?labelColor=0B1622&logo=android&logoColor=white)

### [⬇️ Скачать приложение](https://github.com/Said240705/pamir-vpn-android/releases/latest/download/pamir-vpn-universal.apk)

<sub>Файл <code>pamir-vpn-universal.apk</code> подходит для всех телефонов и телевизоров на Android ·
<a href="https://app.pamirlink.ru">Личный кабинет</a> ·
<a href="https://t.me/pamirlink_bot">Telegram-бот</a></sub>

<br>

<img src="pamir/docs/start.jpg" width="200" alt="Первый запуск">&nbsp;
<img src="pamir/docs/home.jpg" width="200" alt="Главный экран">&nbsp;
<img src="pamir/docs/servers.jpg" width="200" alt="Выбор сервера">&nbsp;
<img src="pamir/docs/settings.jpg" width="200" alt="Настройки">

</div>

---

## ✨ Возможности

| | |
|---|---|
| ⚡ **Одна кнопка** | Подключение в одно касание, без настроек и ручного ввода конфигураций |
| 🔑 **Вход через Telegram или почту** | Подписка подключается сама — ссылки копировать не нужно |
| 🌍 **Серверы в Европе** | Приложение показывает отклик каждого сервера и само выбирает самый быстрый |
| 📶 **Работает на мобильном интернете** | Отдельные серверы для сетей с ограничениями и «умный режим», который включает их сам |
| 🏦 **Сайты РФ напрямую** | Госуслуги и банки открываются без шифрования, всё остальное — под защитой |
| 📱 **Приложения без VPN** | Можно выбрать программы, которые ходят в интернет напрямую |
| 💳 **Оплата внутри приложения** | Продление через СБП, карту или с баланса, промокоды, бесплатный пробный период |
| 🔁 **Автосмена сервера** | Если сервер перестал отвечать, приложение переключится на другой |
| 📺 **Android TV** | Отдельный интерфейс для пульта, вход по QR-коду, автозапуск вместе с телевизором |
| 🔔 **Плитка в шторке и виджет** | Включить и выключить защиту можно, не открывая приложение |

## 🚀 Как начать

1. **Скачайте** [`pamir-vpn-universal.apk`](https://github.com/Said240705/pamir-vpn-android/releases/latest/download/pamir-vpn-universal.apk) и установите его.
2. **Войдите** через Telegram или по почте — подписка и серверы загрузятся сами.
3. **Нажмите большую кнопку** — готово, интернет под защитой.

Нет подписки? В приложении можно оформить бесплатный пробный период или выбрать тариф.

## 🛡 Почему Android предупреждает при установке

Pamir VPN устанавливается из файла, а не из Google Play, поэтому Android и Play Защита могут показать предупреждение «Приложение из неизвестного источника». Это стандартное сообщение для любых приложений не из магазина.

Чтобы установить: нажмите **«Всё равно установить»** (или **«Подробнее» → «Всё равно установить»**). Обновления потом приходят прямо в приложении.

Исходный код приложения открыт — он целиком находится в этом репозитории.

## 💬 Поддержка

- Telegram-бот: [@pamirlink_bot](https://t.me/pamirlink_bot)
- Личный кабинет: [app.pamirlink.ru](https://app.pamirlink.ru)
- В приложении: **Настройки → Поддержка** или **Сообщить о проблеме**

---

<details>
<summary><b>🛠 Для разработчиков</b></summary>

<br>

Pamir VPN основан на открытом клиенте [v2rayNG](https://github.com/2dust/v2rayNG) и ядре [Xray](https://github.com/XTLS/Xray-core).

- `V2rayNG/` — Android-проект v2rayNG (Kotlin, Gradle).
- `pamir/src/` — интерфейс Pamir на Jetpack Compose: главный экран, кабинет, оплата, настройки, ТВ.
- `pamir/brand.py` — превращает v2rayNG в Pamir VPN: название, иконки, пакет `ru.pamirlink.vpn`, подключение экранов Pamir.
- `pamir/server/` — патчи для сервера кабинета и бота.
- `.github/workflows/pamir-build.yml` — сборка и публикация релиза (кнопка **Run workflow**: версия, тестовая сборка, важное обновление).
- `.github/workflows/pamir-emulator.yml` — проверка готового APK на эмуляторе Android.

Сборка вручную повторяет шаги из `pamir-build.yml`: подготовить ядро (`AndroidLibXrayLite`, `hev-socks5-tunnel`), запустить `python3 pamir/brand.py`, затем `./gradlew assemblePlaystoreRelease` в папке `V2rayNG`.

</details>

## 📄 Лицензия

Распространяется по лицензии [GNU GPL v3](LICENSE), как и исходный проект [v2rayNG](https://github.com/2dust/v2rayNG) (© 2dust и участники проекта).
