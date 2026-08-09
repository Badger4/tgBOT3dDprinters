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
from bot.handlers.commercial import router as commercial_router
from bot.handlers.common import router as common_router

def setup_routers() -> Router:
    main_router = Router()
    all_routers = [
        start_router, dashboard_router, commercial_router, printers_router,
        control_router, filament_router, notifications_router, admin_router,
        files_router, callbacks_router, common_router
    ]
    for r in all_routers:
        r._parent_router = None
        main_router.include_router(r)
    return main_router
