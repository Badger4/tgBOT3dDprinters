# 3D Printer Farm Telegram Bot & WebApp (Bambu Lab)

**[ English ]** | [ Українська ](README_UA.md)

[![CI Tests](https://github.com/Badger4/tgBOT3dDprinters/actions/workflows/ci.yml/badge.svg)](https://github.com/Badger4/tgBOT3dDprinters/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)

A feature-rich, high-performance **Telegram Bot & WebApp SPA** written in **Python 3.10+** for monitoring, managing, and controlling Bambu Lab 3D printer farms in real-time over local MQTT, FTPS, and HTTP REST API.

---

## 🚀 Key Features

- **🔐 Enterprise-Grade Security & Privacy**:
  - Zero hardcoded secrets: All credentials managed via environment variables (`.env`).
  - Access Code Masking: LAN MQTT access codes are strictly masked in public REST API/WebApp responses (`••••••••`).
  - Log Sanitization: Built-in `SensitiveDataFilter` automatically scrubs bot tokens, API keys, and access codes from log files and standard output.
  - Safe Expression Evaluator: Eliminates security vulnerabilities by using Python's `ast` parser for safe math evaluation.

- **⚡ Async Architecture & Performance**:
  - Non-blocking asynchronous design built on `asyncio`, `aiogram 3.x`, `aiohttp`, and `aiofiles`.
  - SQLite WAL (Write-Ahead Logging) storage mode to protect MicroSD cards from flash wear when running on single-board computers like Raspberry Pi.

- **🖨️ Bambu Lab Fleet Management**:
  - MQTT Real-Time Telemetry: Monitor nozzle/bed temperatures, print progress, layer counts, speed profiles, and active AMS/Virtual Tray spools.
  - Direct FTPS Integration: Fast print file uploads (3MF / G-Code) and accurate filament weight parsing.
  - Automated Filament Consumption: Auto-deducts spent filament grams from active AMS slots upon print job completion.

- **📱 Telegram WebApp SPA & Real-Time Monitoring**:
  - Single-Page Application (SPA) dashboard for interactive printer farm management within Telegram.
  - Server-Sent Events (SSE) streaming live printer telemetry to WebApp browsers without polling overhead.
  - Commercial Pricing Calculator: Dynamic cost estimation tool based on material weight, electricity rates, machine depreciation, and customizable profit margins.

- **👥 Multi-User Access Control & Administration**:
  - User authorization whitelist with real-time approval/denial workflow for administrators.


---

## 🛠️ Installation & Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/Badger4/tgBOT3dDprinters.git
cd tgBOT3dDprinters
```

### 2. Set Up Virtual Environment
```bash
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables (`.env`)
Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

#### 📋 Complete `.env` Environment Variables Reference:

| Variable | Required? | Default Value | Description |
| :--- | :---: | :---: | :--- |
| `TELEGRAM_BOT_TOKEN` | 🔴 Yes | — | Your Telegram Bot Token obtained from [@BotFather](https://t.me/BotFather) |
| `ADMIN_CHAT_ID` | 🔴 Yes | — | Telegram Chat ID of the main bot administrator |
| `STORAGE_DIR` | 🟢 No | `./printers_storage` | Local directory path for SQLite DB, logs, and printer configs |
| `HTTP_PORT` | 🟢 No | `8080` | Port for the local REST API and WebApp server |
| `WEBAPP_URL` | 🟢 No | `http://localhost:8080` | Public HTTPS WebApp URL (e.g. Ngrok, Cloudflare Tunnel, or custom domain) |
| `API_SECRET_KEY` | 🟢 No | empty | Secret API key for protecting external REST API endpoints |
| `SSE_INTERVAL_SECONDS` | 🟢 No | `5.0` | Server-Sent Events live update frequency in seconds |
| `NGROK_AUTHTOKEN` | 🟢 No | empty | Ngrok authtoken for automatic WebApp HTTPS tunneling |

| `ELECTRICITY_COST_PER_KWH` | 🟢 No | `4.32` | Electricity rate (UAH/kWh) for commercial price calculation |
| `LOG_LEVEL` | 🟢 No | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### 5. Run the Application
```bash
python printer.py
```

---

## 🧪 Testing & CI

Run the automated `pytest` test suite:
```bash
pytest tests/ --verbose
```

All pushes and pull requests to `main` are automatically verified by [GitHub Actions CI](.github/workflows/ci.yml) across Python 3.10, 3.11, 3.12, and 3.13.

---

## 🔒 Security & Rate Limiting

The WebApp REST API enforces strict multi-tier IP rate limiting and security headers to protect physical 3D printers and server infrastructure from unauthorized abuse or flooding:

| Category | Endpoints / Methods | Rate Limit | Response Header | Status Code |
| :--- | :--- | :--- | :--- | :--- |
| **File Uploads** | `/api/files/upload` (POST) | **30 req/min** | `X-RateLimit-Limit: 30` | `429 Too Many Requests` |
| **Sensitive Control** | `/api/printers/{id}/control`, `/api/commercial/presets` | **20 req/min** | `X-RateLimit-Limit: 20` | `429 Too Many Requests` |
| **General Telemetry** | `/health`, `/api/printers`, `/api/history` | **300 req/min** | `X-RateLimit-Limit: 300` | `429 Too Many Requests` |

Security headers included on all responses:
- `Content-Security-Policy`: Modern W3C framing restrictions (`frame-ancestors 'self' https://web.telegram.org https://*.telegram.org;`)
- `Access-Control-Allow-Origin`: Strict whitelist origin validation (Telegram WebApp, `WEBAPP_URL`, localhost)
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`

### 📢 Reporting Vulnerabilities
If you discover a security vulnerability, please do **NOT** open a public issue. Instead, submit a private report via [GitHub Security Advisories](https://github.com/Badger4/tgBOT3dDprinters/security/advisories) or contact the repository maintainer directly. All security reports are reviewed promptly.

---

## 📄 License & Contributing



- **License**: Released under the open-source [MIT License](LICENSE).
- **Contributing**: Contributions are welcome! Please read the developer guidelines in [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a Pull Request.
