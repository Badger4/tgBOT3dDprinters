import re
with open('bot/handlers/commercial.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("callback: aiogram.types.CallbackQuery", "callback: CallbackQuery")

with open('bot/handlers/commercial.py', 'w', encoding='utf-8') as f:
    f.write(content)
