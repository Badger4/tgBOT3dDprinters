"""
Router registration package for Telegram Bot.
"""
from aiogram import Router

from bot.handlers.start import router as start_router
from bot.handlers.dashboard import router as dashboard_router
from bot.handlers.printers import router as printers_router
from bot.handlers.control import router as control_router
from bot.handlers.filament import router as filament_router
from bot.handlers.notifications import router as notifications_router
from bot.handlers.admin import router as admin_router
from bot.handlers.files import router as files_router
from bot.handlers.callbacks import router as callbacks_router
from bot.handlers.common import router as common_router

def setup_routers() -> Router:
    main_router = Router()
    main_router.include_router(start_router)
    main_router.include_router(dashboard_router)
    main_router.include_router(printers_router)
    main_router.include_router(control_router)
    main_router.include_router(filament_router)
    main_router.include_router(notifications_router)
    main_router.include_router(admin_router)
    main_router.include_router(files_router)
    main_router.include_router(callbacks_router)
    main_router.include_router(common_router)
    return main_router
