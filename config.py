"""
Configuration settings for 3D Printer Farm Telegram Bot.
"""

__version__ = "1.0.0"

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(ENV_PATH, override=True)


# Helper functions for safe type conversion
def _get_env_int(key: str, default: int) -> int:
    val = os.getenv(key, "").strip()
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        sys.stderr.write(f"⚠️ Invalid integer for {key}: '{val}'. Using default {default}.\n")
        return default


def _get_env_float(key: str, default: float) -> float:
    val = os.getenv(key, "").strip()
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        sys.stderr.write(f"⚠️ Invalid float for {key}: '{val}'. Using default {default}.\n")
        return default


def update_env_key(key: str, val: str) -> None:
    """Safely sets or updates a key=val pair in the project's .env file."""
    lines = []
    if ENV_PATH.exists():
        content = ENV_PATH.read_text(encoding="utf-8")
        lines = content.splitlines()

    found = False
    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={val}")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"{key}={val}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# Environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "").strip()
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "./printers_storage")).resolve()
HTTP_PORT = _get_env_int("HTTP_PORT", 8080)
API_SECRET_KEY = os.getenv("API_SECRET_KEY", "").strip()
WEB_ADMIN_PASSWORD = os.getenv("WEB_ADMIN_PASSWORD", os.getenv("API_SECRET_KEY", "")).strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", f"http://localhost:{HTTP_PORT}").strip()
SSE_INTERVAL_SECONDS = _get_env_float("SSE_INTERVAL_SECONDS", 5.0)
NGROK_AUTHTOKEN = os.getenv("NGROK_AUTHTOKEN", "").strip()
NGROK_DOMAIN = os.getenv("NGROK_DOMAIN", "").strip()
ELECTRICITY_COST_PER_KWH = _get_env_float("ELECTRICITY_COST_PER_KWH", 4.32)



# Logging level configuration
LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)

# Force UTF-8 encoding for Windows standard output streams
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import re


# Sensitive data filter for secure log rotation
class SensitiveDataFilter(logging.Filter):
    """
    Sanitizes log messages before writing to file or console.
    Replaces raw access_code, Telegram bot tokens, API keys, and secret tokens with masked placeholders.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = self._sanitize(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: self._sanitize(v) if isinstance(v, str) else v for k, v in record.args.items()}
                elif isinstance(record.args, tuple):
                    record.args = tuple(self._sanitize(a) if isinstance(a, str) else a for a in record.args)
        except Exception:
            pass
        return True

    def _sanitize(self, text: str) -> str:
        if not text:
            return text
        text = re.sub(r"\b[0-9]{8,10}:[a-zA-Z0-9_-]{35}\b", "[TELEGRAM_BOT_TOKEN_MASKED]", text)
        text = re.sub(r"\b3Hg[a-zA-Z0-9_-]{40,50}\b", "[NGROK_AUTHTOKEN_MASKED]", text)
        if TELEGRAM_BOT_TOKEN and len(TELEGRAM_BOT_TOKEN) > 5 and TELEGRAM_BOT_TOKEN in text:
            text = text.replace(TELEGRAM_BOT_TOKEN, "[TELEGRAM_BOT_TOKEN_MASKED]")
        if API_SECRET_KEY and len(API_SECRET_KEY) > 3 and API_SECRET_KEY in text:
            text = text.replace(API_SECRET_KEY, "[API_SECRET_KEY_MASKED]")
        if NGROK_AUTHTOKEN and len(NGROK_AUTHTOKEN) > 5 and NGROK_AUTHTOKEN in text:
            text = text.replace(NGROK_AUTHTOKEN, "[NGROK_AUTHTOKEN_MASKED]")

        text = re.sub(
            r'(access[_-]?code["\']?\s*[:=]\s*["\']?)([^"\'\s,}{&]+)', r"\1••••••••", text, flags=re.IGNORECASE
        )
        text = re.sub(
            r'([?&](?:access[_-]?code|token|api[_-]?key|init[_-]?data|tgWebAppInitData)=)([^"\'\s,&]+)',
            r"\1••••••••",
            text,
            flags=re.IGNORECASE,
        )
        return text


# Ensure storage directory exists
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

from logging.handlers import RotatingFileHandler

# Setup logging with SensitiveDataFilter
sensitive_filter = SensitiveDataFilter()
file_handler = RotatingFileHandler(
    STORAGE_DIR / "printer_bot.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
file_handler.addFilter(sensitive_filter)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.addFilter(sensitive_filter)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=LOG_LEVEL,
    force=True,
    handlers=[file_handler, stream_handler],
)

# Explicitly attach filter to Root logger and third-party library loggers (aiohttp, aiogram)
root_lg = logging.getLogger()
root_lg.addFilter(sensitive_filter)

for lg_name in ("PrinterBot", "aiohttp.access", "aiohttp.server", "aiohttp.web", "aiogram"):
    sub_lg = logging.getLogger(lg_name)
    sub_lg.addFilter(sensitive_filter)

logger = logging.getLogger("PrinterBot")


def validate_config(strict: bool = True) -> None:
    """Validates essential environment variables on startup."""
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not ADMIN_CHAT_ID:
        missing.append("ADMIN_CHAT_ID")

    if missing:
        msg = f"❌ Missing required environment variables: {', '.join(missing)}. Please set them in your .env file."
        if strict:
            logger.critical(msg)
            raise ValueError(msg)
        else:
            logger.warning(msg)


if not TELEGRAM_BOT_TOKEN or not ADMIN_CHAT_ID:
    validate_config(strict=False)
