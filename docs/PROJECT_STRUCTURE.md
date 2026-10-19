# 🗺️ Повна Структура та Архітектура Проєкту (PROJECT_STRUCTURE.md)

> **Статус**: Оновлено після масштабного рефакторингу модульності.  
> **Призначення**: Вичерпний навігатор по архітектурі, модулях, пакетах та просторах імен системи управління 3D-фермою Bambu Lab.

---

## ⚡ Швидкий пошук: «Де що лежить?»

| Завдання / Доменна зона | Головний модуль / пакет | Допоміжні компоненти |
| :--- | :--- | :--- |
| **Точка входу та запуск** | `main.py` | `app.py` (`PrinterBotApp`) |
| **Telegram-бот: Клавіатури** | `bot/keyboards/` (`common.py`, `printers.py`, `filament.py`, `notifications.py`, `parts.py`, `admin.py`, `history.py`) | `bot/keyboards/__init__.py` |
| **Telegram-бот: FSM Стани** | `bot/states/` (`printers.py`, `filament.py`, `parts.py`, `admin.py`) | `bot/states/__init__.py` |
| **Telegram-бот: Обробники (Handlers)** | `bot/handlers/` (`printers/`, `filament/`, `parts/`, `commercial.py`, `notifications.py`, `admin.py`) | `bot/handlers/__init__.py` |
| **Bambu Lab MQTT & Моделі** | `models/printer.py` (`BambuPrinter`) | `services/mqtt_message_parser.py` |
| **REST API & WebApp HTTP Сервер** | `services/http/` (`server.py`, `auth.py`, `middleware.py`, `routes_*.py`) | `services/http_server.py` (facade) |
| **Сховище та Репозиторії (SQLite WAL)** | `storage/` (`base.py`, `users.py`, `printers.py`, `spools.py`, `parts.py`, `commercial.py`, `settings.py`) | `storage/manager.py` (`StorageManager` facade) |
| **Frontend WebApp: Стилі** | `webapp/static/css/` (`auth.css`, `base.css`, `components.css`, `dashboard.css`, `modals.css`) | `webapp/static/css/style.css` (bundle) |
| **Frontend WebApp: Скрипти** | `webapp/static/js/` (`login.js`, `setup.js`, `app.js`, `modules/api.js`, `modules/utils.js`, `modules/cockpit.js`) | `webapp/index.html` |
| **Скрипти розгортання та хуки** | `scripts/` (`deploy_to_pi.py`, `orca_hook.py`, `run_orca_hook.bat`, `printer_bot.service`) | `scripts/start_cloudflared_quick_tunnel.py` |
| **Документація проєкту** | `docs/` (`PROJECT_STRUCTURE.md`, `ARCHITECTURE_AND_FEATURES.md`, `BOT_STRUCTURE.md`) | `README.md`, `README_UA.md` |

---

## 📂 Детальний опис модулів

### 1. Корінь проєкту
* **`main.py`**: Єдина канонічна точка входу в систему. Ініціалізує `PrinterBotApp()` і запускає головний асинхронний цикл.
* **`app.py`**: Ядро оркестрації (`class PrinterBotApp`). Координує Telegram-бота, MQTT-клієнти принтерів, HTTP REST API сервер та фонові цикли моніторингу.
* **`config.py`**: Завантаження та валідація змінних оточення `.env`, налаштувань портів, Cloudflare Tunnel, адмінів і шляхів.
* **`pyproject.toml`**: Єдине джерело правди (Single Source of Truth) для залежностей (PEP 621), конфігурацій `pytest`, `coverage` та лінтера `ruff`.
* **`requirements.txt`**: Дзеркальний експорт залежностей з `pyproject.toml` для стандартної інсталяції через `pip install -r requirements.txt`.

### 2. `bot/` — Пакет Telegram-бота (Aiogram 3)
* **`bot/handlers/`**: Обробники подій, структуровані за предметними областями:
  * `printers/`: список принтерів, картка статусу, телеметрія, керування соплами.
  * `filament/`: AMS слоти, монтаж/зняття котушок, RFID.
  * `parts/`: склад надрукованих деталей, надсилання на друк.
  * `commercial.py`: калькулятор собівартості та комерційної вартості друку.
  * `notifications.py`: налаштування сповіщень та вибір мови.
  * `admin.py`: керування користувачами та правами доступу.
* **`bot/keyboards/`**: Модульний пакет побудови клавіатур:
  * `common.py`: головне меню, перехід у WebApp, статус ферми.
  * `printers.py`: вибір принтера, керування рухом осей, екструдером, калібрування.
  * `filament.py`: сітка слотів AMS, типи пластику, кольори, вага.
  * `notifications.py`: інлайн-кнопки сповіщень про друк, помилки HMS.
  * `parts.py`: бібліотека деталей та фільтри пошуку.
  * `admin.py`: адмін-панель.
  * `history.py`: фільтри історії друку та аудиту котушок.
* **`bot/states/`**: Модульний пакет FSM станів Aiogram 3:
  * `printers.py`: `AddPrinterStates`, `PrinterMenuStates`.
  * `filament.py`: `SpoolManagementStates`, `AddSpoolStates`, `MountSpoolStates`.
  * `parts.py`: `AddPartStates`, `PartEditingStates`, `PrintPartStates`.
  * `admin.py`: `AdminStates`.

### 3. `services/` — Служби та зовнішні інтеграції
* **`services/http/`**: Модульний HTTP-сервер Aiohttp для WebApp та REST API:
  * `server.py`: фабрика додатку `create_http_app` та запуск `start_http_server`.
  * `auth.py`: криптографічна валідація Telegram WebApp `initData` HMAC-SHA256 та веб-сесій.
  * `middleware.py`: захисні заголовки, rate-limiting, захист від брутфорсу.
  * `routes_printers.py`: ендпоінти списку принтерів, телеметрії, стрімів камери.
  * `routes_spools.py`: склад котушок та аудит переміщень.
  * `routes_parts.py`: каталог 3D-деталей та запуск друку.
  * `routes_settings.py`: комерційні пресети, експорт PDF/CSV, налаштування.
  * `routes_control.py`: команди керування підсвіткою, калібруванням, рухами.
* **`services/http_server.py`**: Зворотна сумісність: фасадний модуль, що делегує виклики до `services.http`.
* **`services/mqtt_message_parser.py`**: Парсер бінарних та JSON телеметричних пакетів Bambu Lab MQTT.
* **`services/hms_resolver.py`**: База знань кодів несправностей HMS (Health Management System).
* **`services/gcode_parser.py`**: Парсер файлів 3MF/G-code (шари, розрахункова вага, час).
* **`services/ftps_client.py`**: FTPS-клієнт для обміну файлами з принтером через локальну мережу.

### 4. `storage/` — Рівень збереження даних (SQLite WAL)
* **`storage/base.py`**: Базовий клас `BaseStorage`: підключення до `printer_farm.db` з режимом WAL (Write-Ahead Logging), блокування файлів, транзакційні замки `load_json` та `save_json`.
* **`storage/users.py`**: `UserRepository` — збереження профілів, ролей та преференцій мови.
* **`storage/printers.py`**: `PrinterRepository` — список принтерів, серійні номери, коди доступу.
* **`storage/spools.py`**: `SpoolRepository` — склад котушок та журнал аудиту ваги.
* **`storage/parts.py`**: `PartRepository` — каталог готових виробів та 3MF моделі.
* **`storage/commercial.py`**: `CommercialRepository` — пресети вартості, історія друку, облік браку.
* **`storage/settings.py`**: `SettingsRepository` — глобальні параметри ферми та вартість електрики.
* **`storage/manager.py`**: Уніфікований фасад `StorageManager`, який поєднує всі репозиторії.

### 5. `webapp/` — Telegram Mini App (Frontend)
* **`webapp/index.html`**: Головна сторінка WebApp (Single Page Application).
* **`webapp/login.html`**: Автономна сторінка входу адміністратора.
* **`webapp/setup.html`**: Майстер початкового налаштування нової ферми (Setup Wizard).
* **`webapp/static/css/`**: Модульні таблиці стилів:
  * `auth.css`: стилі для `login.html` та `setup.html`.
  * `base.css`: змінні теми, скидання стилів, типографіка, темна тема.
  * `components.css`: скляні картки, кнопки, бейджі, інпути, вкладки.
  * `dashboard.css`: сітка принтерів, картки стану, індикатори температури.
  * `modals.css`: модальні вікна керування, стрім камери, вибір AMS слотів.
  * `style.css`: головний бандл-імпортер усіх модулів.
* **`webapp/static/js/`**:
  * `login.js`: логіка автентифікації `login.html`.
  * `setup.js`: логіка майстра налаштувань `setup.html`.
  * `app.js`: основний клієнтський SPA-контролер.
  * `modules/api.js`: обгортка fetch з прокиданням сесійних токенів та SSE.
  * `modules/utils.js`: форматування часу, назв пластиків та моделей Bambu.
  * `modules/cockpit.js`: компоненти карток статусу принтера.

### 6. `scripts/` — Скрипти автоматизації та інфраструктури
* **`scripts/deploy_to_pi.py`**: Безпечний деплой коду на Raspberry Pi через SFTP без комітів у Git.
* **`scripts/orca_hook.py`**: Скрипт-хук для OrcaSlicer.
* **`scripts/run_orca_hook.bat`**: Windows batch-файл для запуску хука зі слайсера.
* **`scripts/printer_bot.service`**: Systemd unit-файл для автозапуску `main.py` на Linux.
* **`scripts/start_cloudflared_quick_tunnel.py`**: Запуск та автосинхронізація Cloudflare Tunnel.
