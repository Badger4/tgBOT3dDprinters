import html
import uuid

from aiogram import Router, F
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent

from bot.handlers.printers.view import build_printer_status_card

router = Router()

@router.inline_query()
async def inline_query_handler(inline_query: InlineQuery, app):
    chat_id = str(inline_query.from_user.id)
    
    if not await app.is_user_approved(chat_id):
        await inline_query.answer([], cache_time=1)
        return
        
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = (u_lang == "en")
    
    query = inline_query.query.strip().lower()
    
    results = []
    
    for printer in app.printers.values():
        if query and query not in printer.name.lower():
            continue
            
        status_card = build_printer_status_card(printer, is_en=is_en, hide_sensitive=True)
        
        state_label = getattr(printer, "mapped_state", "UNKNOWN")
        try:
            pct = int(getattr(printer, "mc_percent", 0))
        except (TypeError, ValueError):
            pct = 0
            
        desc = f"State: {state_label} | Progress: {pct}%"
        
        try:
            f_type = getattr(printer, "filament_type", "")
            if f_type and f_type not in ["Empty", "None", "", "Невідомо", "Пусто"]:
                desc += f" | Filament: {f_type}"
        except Exception:
            pass
            
        results.append(
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title=printer.name,
                description=desc,
                input_message_content=InputTextMessageContent(
                    message_text=status_card,
                    parse_mode="HTML"
                )
            )
        )
        
    await inline_query.answer(results, cache_time=1, is_personal=True)
