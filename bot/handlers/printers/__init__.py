"""
Printers and AMS management modular router package.
"""

from aiogram import Router
from bot.handlers.printers.view import router as view_router, build_printer_status_card, handle_list_printers
from bot.handlers.printers.add import router as add_router, handle_printer_states, handle_add_printer_start
from bot.handlers.printers.edit import router as edit_router, handle_edit_printer_menu
from bot.handlers.printers.ams import router as ams_router, handle_calibrate_start

router = Router()
router.include_router(view_router)
router.include_router(add_router)
router.include_router(edit_router)
router.include_router(ams_router)

__all__ = [
    "router",
    "handle_printer_states",
    "handle_add_printer_start",
    "handle_list_printers",
    "build_printer_status_card",
    "handle_edit_printer_menu",
    "handle_calibrate_start",
]
