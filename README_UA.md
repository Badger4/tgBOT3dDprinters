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


| `ELECTRICITY_COST_PER_KWH` | 🟢 Ні | `4.32` | Тариф електроенергії (грн/кВт·год) для калькулятора собівартості |
| `TRUSTED_PROXIES` | 🟢 Ні | `127.0.0.1,::1` | Список IP/CIDR довірених reverse proxy через кому для валідації `X-Forwarded-For` |
| `COOKIE_SECURE` | 🟢 Ні | auto | Примусовий прапорець `Secure` для сесійних cookie (`true`/`false`, автовизначення при HTTPS) |
| `COOKIE_SAMESITE` | 🟢 Ні | `Lax` | Політика SameSite для сесійних cookie (`Lax`, `Strict`, `None`) |
| `SSL_CERT_FILE` | 🟢 Ні | порожньо | Шлях до PEM-файлу SSL-сертифіката для вбудованого HTTPS |
| `SSL_KEY_FILE` | 🟢 Ні | порожньо | Шлях до файлу приватного ключа SSL для вбудованого HTTPS |
| `LOG_LEVEL` | 🟢 Ні | `INFO` | Рівень деталізації логування (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |


### 5. Запуск бота
```bash
python printer.py
```

---

## 🔒 Безпека, Серверний RBAC та Довірені Проксі

REST API WebApp використовує багаторівневе обмеження швидкості запитів (Rate Limiting), серверне розмежування прав (RBAC) та заголовки безпеки:

### Серверний контроль доступу (RBAC)
- **👑 ADMIN**: Повний доступ до керування командою (`/api/users`, `/api/users/access`, `/api/users/delete`), налаштувань ферми (`POST /api/settings`), очищення історії друку (`DELETE /api/history`) та скидання/переналаштування (`POST /api/setup`).
- **👤 USER (Оператор)**: Схвалені члени команди. Можуть моніторити принтери, запускати завдання друку, керувати складом котушок і надрукованих деталей. Прямі виклики адміністративних endpoint повертають `403 Forbidden`.
- **🚫 UNAPPROVED**: Неавторизовані користувачі або користувачі зі скасованим доступом отримують `401 Unauthorized`.

### Блокування повторного налаштування (Setup Lock)
`POST /api/setup` відкритий без авторизації виключно під час першого запуску для встановлення пароля адміністратора. Після завершення початкового налаштування будь-які наступні спроби виклику без активної сесії адміністратора відхиляються з кодом `403 Forbidden`.

### Безпека Cookie та HTTPS
Сесійні cookie (`3d_farm_session`) строго захищені атрибутами `HttpOnly` (захист від викрадення через XSS), `SameSite=Lax` (захист від CSRF) та `Secure` (передача виключно через зашифроване HTTPS-з'єднання). Підтримується як робота за reverse proxy (Nginx, Caddy, Cloudflare, Ngrok), так і прямий HTTPS через `SSL_CERT_FILE` та `SSL_KEY_FILE`.

### Валідація довірених Reverse Proxy
Заголовок `X-Forwarded-For` враховується **виключно** тоді, коли безпосереднє мережеве з'єднання надійшло від довіреного проксі-сервера з конфігурації `TRUSTED_PROXIES` (`127.0.0.1,::1` за замовчуванням). Прямі клієнтські запити не можуть підробити заголовки для обходу Rate Limit.

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
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`

### 📢 Повідомлення про Вразливості (Reporting Vulnerabilities)
Якщо ви виявили потенційну вразливість безпеки, будь ласка, **НЕ створюйте публічних Issue**. Надішліть приватне повідомлення через вкладку [GitHub Security Advisories](https://github.com/Badger4/tgBOT3dDprinters/security/advisories) або зв'яжіться напряму з автором репозиторію. Усі повідомлення розглядаються у найкоротші терміни.

---

## 📄 Ліцензія & Контриб'ютинг



- **Ліцензія**: Закрита комерційна ліцензія (All Rights Reserved). Деталі у файлі [LICENSE](LICENSE).
- **Контриб'юторам**: Будь ласка, ознайомтеся з керівництвом для розробників у файлі [CONTRIBUTING.md](CONTRIBUTING.md) перед відправкою Pull Request.
