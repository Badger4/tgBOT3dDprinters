# 3D Printer Farm Telegram Bot (Python Version)

[ English ](README.md) | **[ Українська ]**

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/Badger4/tgBOT3dDprinters/releases/tag/v1.0.0)
[![CI Tests](https://github.com/Badger4/tgBOT3dDprinters/actions/workflows/ci.yml/badge.svg)](https://github.com/Badger4/tgBOT3dDprinters/actions/workflows/ci.yml)
[![License: Proprietary](https://img.shields.io/badge/License-Proprietary-red.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)


Повна версія Telegram-бота для управління фермою 3D-принтерів Bambu Lab на мові **Python 3.10+**.


---

## 🚀 Основні переваги та виправлення:
1. **Безпека (Security)**:
   - Відсутність хардкоду токенів та адмін-прав. Все винесено в `.env`.
   - Повна відмова від `eval()`. Використовується безпечний `ast`-парсер для обчислення ваги філаменту.
   - Маскування мережевих кодів доступу (`accessCode`) у REST API відповідей.
   - Клапан санітизації логів `SensitiveDataFilter` для захисту від витоку токенів.
2. **Асинхронність (Async I/O)**:
   - Побудовано на `asyncio`, `aiogram 3.x` та `aiofiles`.
   - Немає блокуючих синхронних операцій читання/запису файлів, що зберігає Event Loop чутливим та швидким.
3. **Надійне управління принтерами**:
   - Використання унікальних `UUID` для вибору та видалення принтерів (відсутній баг із зсувом індексів масиву).
   - Автоматичне оновлення залишків філаменту після завершення друку.
   - Підтримка моніторингу температури сопла/столу, прогресу, шарів та матеріалу з AMS/Virtual Tray.
4. **Telegram WebApp SPA & Commercial Calculator**:
   - Інтегроване односторінкове WebApp рішення з підтримкою реального часу через Server-Sent Events (SSE).
   - Калькулятор собівартості 3D-друку з гнучкими комерційними пресетами.
5. **Управління доступом та Адмінка**:
   - Автоматичне підтвердження нових користувачів адміністратором.
   - Користувачі без доступу мають лише кнопку заявки.

---

## 🛠️ Встановлення та запуск

### 1. Перехід у папку проєкту
```bash
cd /path/to/your/project
```

### 2. Створення та активація віртуального середовища (опціонально)
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
```

### 3. Встановлення залежностей
```bash
pip install -r requirements.txt
```

### 4. Налаштування `.env`
Скопіюйте `.env.example` у `.env` та вкажіть потрібні параметри:

```bash
cp .env.example .env
```

#### 📋 Повний список змінних середовища:

| Змінна | Обов'язкова? | Значення за замовчуванням | Опис |
| :--- | :---: | :---: | :--- |
| `TELEGRAM_BOT_TOKEN` | 🔴 Так | — | Токен вашого Telegram-бота від [@BotFather](https://t.me/BotFather) |
| `ADMIN_CHAT_ID` | 🔴 Так | — | Telegram ID головного адміністратора бота |
| `STORAGE_DIR` | 🟢 Ні | `./printers_storage` | Шлях до папки збереження БД, логів та конфігурації принтерів |
| `HTTP_PORT` | 🟢 Ні | `8080` | Порт локального REST API та WebApp сервера |
| `WEBAPP_URL` | 🟢 Ні | `http://localhost:8080` | HTTPS URL адреса WebApp (Ngrok або домен) |
| `API_SECRET_KEY` | 🟢 Ні | порожньо | Ключ авторизації для захисту REST API |
| `SSE_INTERVAL_SECONDS` | 🟢 Ні | `5.0` | Періодичність оновлення живих даних телеметрії WebApp (сек) |


| `ELECTRICITY_COST_PER_KWH` | 🟢 Ні | `4.32` | Тариф електроенергії (грн/кВт·год) для калькулятора себевартості |
| `LOG_LEVEL` | 🟢 Ні | `INFO` | Рівень деталізації логування (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |


### 5. Запуск бота
```bash
python printer.py
```

---

## 🔒 Безпека та Обмеження Запитів (Rate Limiting)

REST API WebApp підтримує багаторівневе IP-лімітування запитів та заголовки безпеки для захисту фізичного обладнання 3D-принтерів від спаму та зловживань:

| Категорія ендпоінтів | Маршрути / Методи | Ліміт | Заголовок відповіді | Код помилки |
| :--- | :--- | :--- | :--- | :--- |
| **Завантаження файлів** | `/api/files/upload` (POST) | **30 зап/хв** | `X-RateLimit-Limit: 30` | `429 Too Many Requests` |
| **Команди управління** | `/api/printers/{id}/control`, `/api/commercial/presets` | **20 зап/хв** | `X-RateLimit-Limit: 20` | `429 Too Many Requests` |
| **Телеметрія та читання** | `/health`, `/api/printers`, `/api/history` | **300 зап/хв** | `X-RateLimit-Limit: 300` | `429 Too Many Requests` |

Заголовки безпеки у кожній відповіді:
- `Content-Security-Policy`: W3C обмеження вбудовування в іфрейми (`frame-ancestors 'self' https://web.telegram.org https://*.telegram.org;`)
- `Access-Control-Allow-Origin`: Перевірка білого списку дозволених Origin (Telegram WebApp, `WEBAPP_URL`, localhost)
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`

### 📢 Повідомлення про Вразливості (Reporting Vulnerabilities)
Якщо ви виявили потенційну вразливість безпеки, будь ласка, **НЕ створюйте публічних Issue**. Надішліть приватне повідомлення через вкладку [GitHub Security Advisories](https://github.com/Badger4/tgBOT3dDprinters/security/advisories) або зв'яжіться напряму з автором репозиторію. Усі повідомлення розглядаються у найкоротші терміни.

---

## 📄 Ліцензія & Контриб'ютинг



- **Ліцензія**: Закрита комерційна ліцензія (All Rights Reserved). Деталі у файлі [LICENSE](LICENSE).
- **Контриб'юторам**: Будь ласка, ознайомтеся з керівництвом для розробників у файлі [CONTRIBUTING.md](CONTRIBUTING.md) перед відправкою Pull Request.
