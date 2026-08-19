"""
Farm dashboard and printing history handlers.
"""

import html
import time

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import Message

router = Router()


@router.message(F.text.lower().in_(["📊 стан ферми", "стан ферми", "ферма", "📊 farm status", "farm status"]))
async def handle_dashboard(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    if not app.printers:
        await message.answer(
            "⚠️ No printers added yet!" if is_en else "⚠️ У базі немає доданих принтерів."
        )
        return

    if is_en:
        dash_txt = "<b>🏭 3D Farm Dashboard</b>\n\n"
        dash_txt += f"<b>Total Printers: {len(app.printers)}</b>\n\n"
    else:
        dash_txt = "<b>🏭 Дашборд 3D Ферми</b>\n\n"
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
            sub_task = html.escape(p.subtask_name or ("Model" if is_en else "Модель"))
            min_lbl = "min" if is_en else "хв"
            dash_txt += f"   📄 <i>{sub_task}</i> ({p.mc_percent}%) | ~{p.mc_remaining_time} {min_lbl}\n"
            dash_txt += f"   🔥 {p.nozzle_temper}°C | 🛏️ {p.bed_temper}°C | 🧵 {p.filament_grams}g\n"
        else:
            rem_lbl = "Remaining:" if is_en else "Залишок:"
            dash_txt += f"   📦 {rem_lbl} {p.filament_grams}g | 🧵 {html.escape(p.filament_type)}\n"
        dash_txt += "\n"

    await message.answer(dash_txt, parse_mode=ParseMode.HTML)


@router.message(F.text.lower().in_(["📜 історія друку", "історія друку", "історія", "📜 print history", "print history", "history"]))
async def handle_history(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    history = await app.storage.load_history()
    if not history:
        await message.answer(
            "📜 <b>Print history log is empty!</b>" if is_en else "📜 <b>Журнал друку порожній!</b>",
            parse_mode=ParseMode.HTML,
        )
        return

    total_prints = len(history)
    total_g = round(sum(item.get("weight_g", 0.0) for item in history), 1)

    if is_en:
        hist_txt = (
            f"<b>📜 Farm Print History & Statistics</b>\n\n"
            f"📊 Total prints completed: <b>{total_prints} items</b>\n"
            f"🧵 Total filament used: <b>{total_g}g</b>\n"
            f"-----------------------------------\n"
            f"<b>Recent completed jobs:</b>\n\n"
        )
    else:
        hist_txt = (
            f"<b>📜 Журнал & Статистика Ферми</b>\n\n"
            f"📊 Загалом надруковано: <b>{total_prints} деталей</b>\n"
            f"🧵 Витрачено пластику: <b>{total_g}g</b>\n"
            f"-----------------------------------\n"
            f"<b>Останні виконані завдання:</b>\n\n"
        )

    recent = history[-10:]
    recent.reverse()
    for idx, item in enumerate(recent, 1):
        dt_str = time.strftime("%d.%m %H:%M", time.localtime(item.get("timestamp", time.time())))
        p_name = html.escape(item.get("printer_name", "Printer" if is_en else "Принтер"))
        sub = html.escape(item.get("subtask_name", "Model" if is_en else "Модель"))
        w = item.get("weight_g", 0.0)
        hist_txt += f"<b>{idx}. {p_name}</b> ({dt_str})\n   📄 <i>{sub}</i> | ⚖️ {w}g\n"

    from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

    csv_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📥 Download CSV Report" if is_en else "📥 Завантажити CSV звіт")],
            [KeyboardButton(text="⬅️ Back" if is_en else "⬅️ Назад")]
        ],
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
            "📥 download csv report",
            "download csv report",
            "export csv"
        ]
    )
)
async def handle_export_csv(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    history = await app.storage.load_history()
    if not history:
        await message.answer(
            "⚠️ Print log is empty, nothing to export." if is_en else "⚠️ Журнал друку порожній, немає даних для експорту."
        )
        return

    from aiogram.types import BufferedInputFile

    from services.report_generator import generate_csv_report

    csv_bytes = generate_csv_report(history)
    date_str = time.strftime("%Y%m%d_%H%M")
    doc_file = BufferedInputFile(csv_bytes, filename=f"farm_print_history_{date_str}.csv")
    await message.answer_document(
        document=doc_file,
        caption="📊 *Full 3D Farm Print History CSV Report*" if is_en else "📊 *Повний CSV звіт історії друку 3D Ферми*",
        parse_mode=ParseMode.MARKDOWN,
    )
