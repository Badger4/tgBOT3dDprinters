"""
3D Printer Farm Telegram Bot (Modular Aiogram 3 Architecture)
Entrypoint script.
"""

import asyncio

from app import PrinterBotApp


def main() -> None:
    app = PrinterBotApp()
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped gracefully.")


if __name__ == "__main__":
    main()
