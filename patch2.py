import re
with open('bot/handlers/commercial.py', 'r', encoding='utf-8') as f:
    content = f.read()

handler = '''
@router.callback_query(F.data == "edit_p_done")
async def handle_edit_preset_done(callback: aiogram.types.CallbackQuery, app):
    chat_id = str(callback.message.chat.id)
    user = await app.storage.load_user(chat_id)
    user["state"] = "idle"
    user["context_data"] = {}
    await app.storage.save_user(user)
    await callback.message.answer("? ??? ????? ?????????!")
    from bot.handlers.commercial import handle_commercial_menu
    await handle_commercial_menu(callback.message, app)
    await callback.answer()
'''

content += "\n" + handler + "\n"

# ensure aiogram is imported if needed, but F is already imported.
with open('bot/handlers/commercial.py', 'w', encoding='utf-8') as f:
    f.write(content)
