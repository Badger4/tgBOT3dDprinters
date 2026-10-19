"""
3D Printer Farm Telegram Bot (Modular Aiogram 3 Architecture)
Main entrypoint script.
"""

import asyncio
import signal
import sys

from app import PrinterBotApp


def main() -> None:
    if hasattr(signal, "SIGTERM"):
        try:
            signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
        except Exception:
            pass

    app = PrinterBotApp()
    try:
        asyncio.run(app.run())
    except (KeyboardInterrupt, SystemExit):
        print("\n👋 Bot stopped gracefully.")


if __name__ == "__main__":
    main()
