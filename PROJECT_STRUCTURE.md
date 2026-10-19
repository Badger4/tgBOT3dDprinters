# 🗺️ НАВІГАТОР ПО ПРОЄКТУ (PROJECT_STRUCTURE.md)

> **Статус**: Оновлено після рефакторингу модульності.  
> **Призначення**: Швидка навігація по структурі файлів та модулів 3D Printer Farm Bot.  
> **Повна деталізована документація**: дивіться у папці [docs/](docs/):
> * [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) — Повний каталог файлів, класів та модулів системи.
> * [docs/ARCHITECTURE_AND_FEATURES.md](docs/ARCHITECTURE_AND_FEATURES.md) — Архітектурні рішення, протоколи Bambu Lab MQTT, WebApp та безпека.
> * [docs/BOT_STRUCTURE.md](docs/BOT_STRUCTURE.md) — Двомовне навігаційне дерево кнопок, FSM-станів та сценаріїв Telegram-бота.

---

## ⚡ Швидкий пошук: «Де що лежить?»

| Завдання / Функціонал | Головний файл | Допоміжні модулі |
| :--- | :--- | :--- |
| **Точка входу (Запуск бота і сервера)** | `main.py` | `app.py` (`PrinterBotApp`) |
| **Картка статусу принтера (`/status`, кольори, слоти AMS)** | `bot/handlers/printers/view.py` | `models/printer.py`, `utils/filament_utils.py` |
| **Клавіатури Telegram (Reply / Inline)** | `bot/keyboards/` | `bot/keyboards/__init__.py` |
| **Стани FSM Aiogram** | `bot/states/` | `bot/states/__init__.py` |
| **Керування AMS: прогрес-бари, активне сопло, список слотів** | `bot/handlers/filament/view.py` | `models/printer.py`, `services/mqtt_message_parser.py` |
| **Монтування та зняття котушок зі складу на принтер** | `bot/handlers/filament/mount.py` | `storage/spools.py` |
| **Парсинг телеметрії Bambu Lab MQTT** | `services/mqtt_message_parser.py` | `models/printer.py` |
| **Розшифровка HMS помилок Bambu Wiki** | `services/hms_resolver.py` | `bot/handlers/printers/view.py` |
| **WebApp Фронтенд (інтерфейс, модальні вікна, камери)** | `webapp/index.html` | `webapp/static/js/app.js` |
| **Модульні стилі WebApp** | `webapp/static/css/` | `auth.css`, `base.css`, `components.css`, `dashboard.css`, `modals.css` |
| **Модульні скрипти WebApp** | `webapp/static/js/` | `login.js`, `setup.js`, `modules/api.js`, `modules/utils.js` |
| **REST API бекенд для WebApp** | `services/http/` | `services/http/server.py`, `services/http/routes_*.py` |
| **Сховище даних (SQLite WAL + репозиторії)** | `storage/` | `storage/manager.py` (фасад), `users.py`, `spools.py`, `parts.py` |
| **Деплой на Raspberry Pi без коміту в Git** | `scripts/deploy_to_pi.py` | `scripts/printer_bot.service` |
| **Хук OrcaSlicer** | `scripts/orca_hook.py` | `scripts/run_orca_hook.bat` |
| **Конфігурація та залежності** | `pyproject.toml` | `requirements.txt`, `config.py`, `.env` |
