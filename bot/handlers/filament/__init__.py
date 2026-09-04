"""
Filament and spool management modular router package.
"""

from aiogram import Router
from bot.handlers.filament.view import router as view_router, handle_filament_menu, handle_rfid_sync
from bot.handlers.filament.mount import router as mount_router, handle_mount_spool_start, handle_unmount_spool_start, get_mounted_spools_or_trays, parse_slot_key_from_text
from bot.handlers.filament.add import router as add_router, handle_add_spool_start, handle_preset_callback
from bot.handlers.filament.edit import router as edit_router, handle_edit_spool_start
from bot.handlers.filament.delete import router as delete_router, handle_delete_spool_start

router = Router()
router.include_router(view_router)
router.include_router(mount_router)
router.include_router(add_router)
router.include_router(edit_router)
router.include_router(delete_router)

__all__ = [
    "router",
    "handle_filament_menu",
    "handle_rfid_sync",
    "handle_mount_spool_start",
    "handle_unmount_spool_start",
    "get_mounted_spools_or_trays",
    "parse_slot_key_from_text",
    "handle_add_spool_start",
    "handle_preset_callback",
    "handle_edit_spool_start",
    "handle_delete_spool_start",
]
