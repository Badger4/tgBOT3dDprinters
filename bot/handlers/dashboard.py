"""
Farm dashboard and printing history handlers.
"""

import html
import time

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import Message

router = Router()


@router.message(F.text.lower().in_(["📊 стан ферми", "стан ферми", "ферма"]))
async def handle_dashboard(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    if not app.printers:
        await message.answer("⚠️ У базі немає доданих принтерів. Додай вже щось, Бака! 😤")
        return

    dash_txt = "<b>🏭 Дашборд 3D Ферми</b>\nХ-хмпф! Ось загальний стан ферми... Тільки не думай, що я цілий день за ними стежу заради тебе! 😤💅\n"
    dash_txt += f"<b>Всього принтерів: {len(app.printers)}</b>\n\n"

    for pid, p in app.printers.items():
        p_name = html.escape(p.name)
        st_emoji = (
            "🖨️"
            if p.gcode_state == "RUNNING"
            else ("⏸️" if p.gcode_state == "PAUSE" else ("🎉" if p.gcode_state == "FINISH" else "💤"))
        )
        spd_str = f" ({p.spd_mag}%)" if getattr(p, "spd_mag", 100) and getattr(p, "spd_mag", 100) != 100 else ""

        dash_txt += f"{st_emoji} <b>{p_name}</b>: <code>{p.gcode_state}</code>{spd_str}\n"

        if p.gcode_state in ["RUNNING", "PAUSE"]:
            sub_task = html.escape(p.subtask_name or "Модель")
            dash_txt += f"   📄 <i>{sub_task}</i> ({p.mc_percent}%) | ~{p.mc_remaining_time} хв\n"
            dash_txt += f"   🔥 {p.nozzle_temper}°C | 🛏️ {p.bed_temper}°C | 🧵 {p.filament_grams}g\n"
        else:
            dash_txt += f"   📦 Залишок: {p.filament_grams}g | 🧵 {html.escape(p.filament_type)}\n"
        dash_txt += "\n"

    await message.answer(dash_txt, parse_mode=ParseMode.HTML)


@router.message(F.text.lower().in_(["📜 історія друку", "історія друку", "історія"]))
async def handle_history(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    history = await app.storage.load_history()
    if not history:
        await message.answer(
            "📜 <b>Журнал друку порожній, Бака!</b>\nПоки що нічого не надруковано. Іди працюй! 😤",
            parse_mode=ParseMode.HTML,
        )
        return

    total_prints = len(history)
    total_g = round(sum(item.get("weight_g", 0.0) for item in history), 1)

    hist_txt = (
        f"<b>📜 Журнал & Статистика Ферми</b>\n"
        f"Х-хмпф! Дивись, скільки всього ми вже надрукували! Але не пишайся занадто, Бака! 😤💅\n\n"
        f"📊 Загалом надруковано: <b>{total_prints} деталей</b>\n"
        f"🧵 Витрачено пластику: <b>{total_g}g</b>\n"
        f"-----------------------------------\n"
        f"<b>Останні виконані завдання:</b>\n\n"
    )

    recent = history[-10:]
    recent.reverse()
    for idx, item in enumerate(recent, 1):
        dt_str = time.strftime("%d.%m %H:%M", time.localtime(item.get("timestamp", time.time())))
        p_name = html.escape(item.get("printer_name", "Принтер"))
        sub = html.escape(item.get("subtask_name", "Модель"))
        w = item.get("weight_g", 0.0)
        hist_txt += f"<b>{idx}. {p_name}</b> ({dt_str})\n   📄 <i>{sub}</i> | ⚖️ {w}g\n"

    from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

    csv_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📥 Завантажити CSV звіт")], [KeyboardButton(text="⬅️ Назад")]],
        resize_keyboard=True,
    )
    await message.answer(hist_txt, parse_mode=ParseMode.HTML, reply_markup=csv_kb)


@router.message(
    F.text.lower().in_(
        [
            "📥 завантажити csv звіт",
            "завантажити csv звіт",
            "експорт csv",
            "csv",
            "/export_history",
            "/export",
        ]
    )
)
async def handle_export_csv(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    history = await app.storage.load_history()
    if not history:
        await message.answer("⚠️ Журнал друку порожній, немає даних для експорту.")
        return

    from aiogram.types import BufferedInputFile

    from services.report_generator import generate_csv_report

    csv_bytes = generate_csv_report(history)
    date_str = time.strftime("%Y%m%d_%H%M")
    doc_file = BufferedInputFile(csv_bytes, filename=f"farm_print_history_{date_str}.csv")
    await message.answer_document(
        document=doc_file,
        caption="📊 *Повний CSV звіт історії друку 3D Ферми*\nТримай файл для Excel, Бака! 📑✨",
        parse_mode=ParseMode.MARKDOWN,
    )
