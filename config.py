"""
Configuration settings for 3D Printer Farm Telegram Bot.
"""
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(ENV_PATH, override=True)

# Environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "").strip()
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "./printers_storage")).resolve()
HTTP_PORT = int(os.getenv("HTTP_PORT", "8080"))
API_SECRET_KEY = os.getenv("API_SECRET_KEY", "").strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", f"http://localhost:{HTTP_PORT}").strip()

# Force UTF-8 encoding for Windows standard output streams
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure storage directory exists
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

from logging.handlers import RotatingFileHandler

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    force=True,
    handlers=[
        RotatingFileHandler(STORAGE_DIR / "printer_bot.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("PrinterBot")

def validate_config(strict: bool = True):
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

