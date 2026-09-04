"""
Printers view & status card handlers.
"""

import html
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import Message
from bot.keyboards import get_printers_keyboard
from models.printer import BambuPrinter

router = Router()


@router.message(F.text.lower().in_(["🖨️ принтери", "принтери", "🖨️ назад до принтерів", "назад до принтерів", "🖨️ printers", "printers", "🖨️ back to printers", "back to printers"]))
async def handle_list_printers(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    user["state"] = "idle"
    user["context_data"] = {}
    await app.storage.save_user(user)
    u_lang = user.get("language", "uk")
    await message.answer(
        "🖨️ <b>Ось твої принтери, Бака!</b>\nОбирай якийсь один і не дратуй мене даремно! 😤💅" if u_lang != "en" else "🖨️ <b>Here are your printers!</b>\nSelect one to view controls and status! 🚀",
        parse_mode=ParseMode.HTML,
        reply_markup=get_printers_keyboard(app.printers, lang=u_lang),
    )


def build_printer_status_card(target_printer: BambuPrinter, is_en: bool = False) -> str:
    is_online = getattr(target_printer, "is_online", True)
    st_code = getattr(target_printer, "gcode_state", "IDLE")

    if not is_online or st_code in ["OFFLINE", "DISCONNECTED", "UNKNOWN"]:
        state_emoji = "🔴"
        state_label = "🔴 Офлайн (Вимкнений)" if not is_en else "🔴 Offline (Powered off)"
    elif st_code in ["RUNNING", "PREPARING", "PREPARATION", "BUILDING", "PRINTING"]:
        state_emoji = "🟢"
        state_label = "🟢 Друкує" if not is_en else "🟢 Printing"
    elif st_code in ["PAUSE", "PAUSED"]:
        state_emoji = "⏸️"
        state_label = "⏸️ Пауза" if not is_en else "⏸️ Paused"
    elif st_code == "FINISH":
        state_emoji = "🎉"
        state_label = "🎉 Друк завершено" if not is_en else "🎉 Finished"
    elif st_code in ["FAILED", "CANCEL"]:
        state_emoji = "⚠️"
        state_label = "⚠️ Помилка/Скасовано" if not is_en else "⚠️ Failed/Cancelled"
    else:
        state_emoji = "⚪"
        state_label = "⚪ Готовий до друку" if not is_en else "⚪ Ready"

    nozzle_target = getattr(target_printer, "nozzle_target_temper", 0)
    bed_target = getattr(target_printer, "bed_target_temper", 0)
    chamber_t = getattr(target_printer, "chamber_temper", 0)
    wifi_sig = getattr(target_printer, "wifi_signal", "")

    nozzle_target_str = (
        f" / {nozzle_target}°C" if isinstance(nozzle_target, (int, float)) and nozzle_target > 0 else ""
    )
    bed_target_str = f" / {bed_target}°C" if isinstance(bed_target, (int, float)) and bed_target > 0 else ""

    chamber_label = "Chamber" if is_en else "Камера"
    chamber_str = f" | 🌡️ <b>{chamber_label}:</b> <code>{chamber_t}°C</code>" if isinstance(chamber_t, (int, float)) and chamber_t > 0 else ""
    wifi_str = f" | 📶 <b>Wi-Fi:</b> <code>{wifi_sig}</code>" if isinstance(wifi_sig, str) and wifi_sig else ""

    hours = getattr(target_printer, "print_hours", 0.0)
    try:
        hours_val = float(hours)
    except (TypeError, ValueError):
        hours_val = 0.0
    hours_str = f"⏱️ <b>Напрацювання:</b> <code>{hours_val:.1f} год</code>\n" if not is_en else f"⏱️ <b>Print Hours:</b> <code>{hours_val:.1f} hrs</code>\n"

    if is_en:
        status_txt = (
            f"<b>📊 Printer Status: {target_printer.name}</b>\n\n"
            f"{state_emoji} <b>State:</b> <code>{state_label}</code>{wifi_str}\n"
            f"🔥 <b>Nozzle:</b> <code>{target_printer.nozzle_temper}°C{nozzle_target_str}</code> | 🛏️ <b>Bed:</b> <code>{target_printer.bed_temper}°C{bed_target_str}</code>{chamber_str}\n"
            f"🧵 <b>Filament Type:</b> <b>{target_printer.filament_type}</b>\n"
            f"📦 <b>Spool Remaining:</b> <b>{target_printer.filament_grams}g</b>\n"
            f"{hours_str}"
        )
    else:
        status_txt = (
            f"<b>📊 Стан принтера: {target_printer.name}</b>\n\n"
            f"{state_emoji} <b>Стан:</b> <code>{state_label}</code>{wifi_str}\n"
            f"🔥 <b>Сопло:</b> <code>{target_printer.nozzle_temper}°C{nozzle_target_str}</code> | 🛏️ <b>Стіл:</b> <code>{target_printer.bed_temper}°C{bed_target_str}</code>{chamber_str}\n"
            f"🧵 <b>Тип пластику:</b> <b>{target_printer.filament_type}</b>\n"
            f"📦 <b>Залишок на бабіні:</b> <b>{target_printer.filament_grams}g</b>\n"
            f"{hours_str}"
        )

    return status_txt


@router.message(F.text.lower().in_(["📊 статус", "статус", "📊 status", "status"]))
async def handle_printer_status(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        await message.answer("⚠️ Спочатку оберіть принтер у меню «🖨️ Принтери».")
        return

    card = build_printer_status_card(target_printer, is_en=(u_lang == "en"))
    await message.answer(card, parse_mode=ParseMode.HTML)


@router.message(F.text.startswith("🖨️ "))
async def handle_select_printer(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    p_name = message.text.replace("🖨️ ", "").strip()
    target_printer = next((p for p in app.printers.values() if p.name == p_name or p_name in p.name), None)

    if target_printer:
        user = await app.storage.load_user(chat_id)
        user["state"] = "printer_menu"
        user.setdefault("context_data", {})["selected_printer_id"] = target_printer.id
        await app.storage.save_user(user)

        from bot.keyboards import get_printer_menu_keyboard
        u_lang = user.get("language", "uk")
        card = build_printer_status_card(target_printer, is_en=(u_lang == "en"))
        await message.answer(card, parse_mode=ParseMode.HTML, reply_markup=get_printer_menu_keyboard(target_printer, lang=u_lang))

