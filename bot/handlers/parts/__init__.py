"""
Parts warehouse modular router package.
"""

from aiogram import Router
from bot.handlers.parts.view import router as view_router, handle_parts_warehouse_btn, open_parts_list, send_part_info
from bot.handlers.parts.add import router as add_router, handle_add_part_start
from bot.handlers.parts.edit import router as edit_router, handle_edit_part_start
from bot.handlers.parts.delete import router as delete_router, handle_delete_part_start
from bot.handlers.parts.print_job import router as print_router, handle_print_part_start

router = Router()
router.include_router(view_router)
router.include_router(add_router)
router.include_router(edit_router)
router.include_router(delete_router)
router.include_router(print_router)

__all__ = [
    "router",
    "handle_parts_warehouse_btn",
    "open_parts_list",
    "send_part_info",
    "handle_add_part_start",
    "handle_edit_part_start",
    "handle_delete_part_start",
    "handle_print_part_start",
]
