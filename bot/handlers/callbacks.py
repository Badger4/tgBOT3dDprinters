"""
Callback query handlers for inline button interactions.
"""
from aiogram import Router, types
from aiogram.enums import ParseMode

router = Router()

@router.callback_query()
async def handle_callback_query(callback: types.CallbackQuery, app):
    data = callback.data or ""
    if data.startswith("deduct_"):
        parts = data.split("_")
        if len(parts) >= 3:
            p_id = parts[1]
            try:
                grams = float(parts[2])
            except ValueError:
                grams = 0.0

            printer = app.printers.get(p_id)
            if printer and grams > 0:
                old_w = printer.filament_grams
                printer.filament_grams = round(printer.filament_grams - grams, 2)
                await app.save_printers_config()
                await callback.answer(f"✅ Списано {grams}g! Новий залишок: {printer.filament_grams}g", show_alert=True)
                try:
                    await callback.message.reply(
                        f"✅ **Списано {grams}g для {printer.name}!**\n📦 Старий залишок: *{old_w}g* ➔ Новий залишок: *{printer.filament_grams}g*",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception:
                    pass
                return
    await callback.answer()
