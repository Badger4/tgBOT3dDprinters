"""
Printers view & status card handlers.
"""

import html
import time
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from bot.keyboards import get_printers_keyboard
from models.printer import BambuPrinter

router = Router()


@router.message(F.text.lower().in_(["🖨️ принтери", "принтери", "🖨️ назад до принтерів", "назад до принтерів", "🖨️ printers", "printers", "🖨️ back to printers", "back to printers"]))
async def handle_list_printers(message: Message, app, state: FSMContext | None = None):
    if state:
        await state.clear()
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


def format_remaining_time(minutes: int, is_en: bool = False) -> str:
    try:
        minutes = int(minutes)
    except (ValueError, TypeError):
        return ""
    if minutes <= 0:
        return ""
    hours = minutes // 60
    mins = minutes % 60
    if hours > 0 and mins > 0:
        return f"{hours} год {mins} хв" if not is_en else f"{hours}h {mins}m"
    elif hours > 0:
        return f"{hours} год" if not is_en else f"{hours}h"
    else:
        return f"{mins} хв" if not is_en else f"{mins} min"


def get_finish_time_str(minutes: int, is_en: bool = False) -> str:
    try:
        minutes = int(minutes)
    except (ValueError, TypeError):
        return ""
    if minutes <= 0:
        return ""
    finish_ts = time.time() + minutes * 60
    finish_loc = time.localtime(finish_ts)
    now_loc = time.localtime()

    time_part = time.strftime("%H:%M", finish_loc)

    if finish_loc.tm_year == now_loc.tm_year and finish_loc.tm_yday == now_loc.tm_yday:
        return f"завершиться о {time_part}" if not is_en else f"finishes at {time_part}"
    elif (finish_loc.tm_yday - now_loc.tm_yday) in [1, -364, -365]:
        return f"завершиться завтра о {time_part}" if not is_en else f"finishes tomorrow at {time_part}"
    else:
        date_part = time.strftime("%d.%m", finish_loc)
        return f"завершиться {date_part} о {time_part}" if not is_en else f"finishes {date_part} at {time_part}"


def build_printer_status_card(target_printer: BambuPrinter, is_en: bool = False) -> str:
    is_online = getattr(target_printer, "is_online", True)
    mapped_st = getattr(target_printer, "mapped_state", "ONLINE")

    try:
        rem_m = int(getattr(target_printer, "mc_remaining_time", 0))
    except (TypeError, ValueError):
        rem_m = 0
    try:
        pct = int(getattr(target_printer, "mc_percent", 0))
    except (TypeError, ValueError):
        pct = 0
    rem_str = format_remaining_time(rem_m, is_en)
    finish_str = get_finish_time_str(rem_m, is_en)

    if not is_online or mapped_st == "OFFLINE":
        state_emoji = "🔴"
        state_label = "Офлайн" if not is_en else "Offline"
    elif mapped_st == "RUNNING":
        state_emoji = "🟢"
        finish_note = f", {finish_str}" if finish_str else ""
        if rem_str:
            state_label = f"Друкує (~{rem_str}{finish_note})" if not is_en else f"Printing (~{rem_str}{finish_note})"
        else:
            state_label = f"Друкує ({pct}%)" if not is_en else f"Printing ({pct}%)"
    elif mapped_st == "PAUSE":
        state_emoji = "⏸️"
        state_label = f"Пауза ({pct}%)" if not is_en else f"Paused ({pct}%)"
    else:
        state_emoji = "⚪"
        state_label = "Онлайн" if not is_en else "Online"

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

    active_k = target_printer.get_active_slot_key() if hasattr(target_printer, "get_active_slot_key") else "254"
    if callable(active_k):
        try:
            active_k = active_k()
        except Exception:
            active_k = "254"
    if not isinstance(active_k, (str, int)):
        active_k = "254"

    raw_grams = target_printer.get_slot_grams(active_k) if hasattr(target_printer, "get_slot_grams") else getattr(target_printer, "filament_grams", 0.0)
    if callable(raw_grams):
        try:
            raw_grams = raw_grams(active_k)
        except Exception:
            raw_grams = 0.0
    try:
        active_grams_val = float(raw_grams)
    except (TypeError, ValueError):
        active_grams_val = 0.0

    trays = getattr(target_printer, "ams_trays_info", {})
    if not isinstance(trays, dict):
        trays = {}
    t_info = trays.get(str(active_k), {})
    if not isinstance(t_info, dict):
        t_info = {}
    has_tray = bool(t_info.get("type") and not t_info.get("empty", False))
    f_type = getattr(target_printer, "filament_type", "")
    f_type_str = str(f_type) if isinstance(f_type, str) else ""

    has_spool = (active_grams_val > 0.0) and (has_tray or (f_type_str and f_type_str not in ["Невизначено", "None", "", "Порожньо", "Empty"]))

    spool_str = f"<b>{active_grams_val}g</b>" if has_spool else ("<i>Empty</i>" if is_en else "<i>Порожньо</i>")
    type_str = f"<b>{f_type_str}</b>" if (has_spool and f_type_str and f_type_str not in ["Невизначено", "None", "", "Порожньо", "Empty"]) else "<i>—</i>"

    print_info_str = ""
    if mapped_st in ["RUNNING", "PAUSE"]:
        subtask = getattr(target_printer, "subtask_name", "")
        if not isinstance(subtask, str):
            subtask = ""
        try:
            layer = int(getattr(target_printer, "layer_num", 0))
        except (TypeError, ValueError):
            layer = 0
        try:
            total_layer = int(getattr(target_printer, "total_layer_num", 0))
        except (TypeError, ValueError):
            total_layer = 0
        lines = []
        if subtask:
            lines.append(f"📄 <b>{'Завдання' if not is_en else 'Job'}:</b> <code>{html.escape(subtask)}</code>")
        lines.append(f"⏳ <b>{'Прогрес' if not is_en else 'Progress'}:</b> <code>{pct}%</code>")
        if rem_m > 0:
            finish_note = f" ({finish_str})" if finish_str else ""
            lines.append(f"⏱️ <b>{'Залишилось друкувати' if not is_en else 'Time Remaining'}:</b> <code>~{rem_str}</code>{finish_note}")
        if total_layer > 0:
            lines.append(f"🥞 <b>{'Шар' if not is_en else 'Layer'}:</b> <code>{layer} / {total_layer}</code>")
        if lines:
            print_info_str = "\n".join(lines) + "\n"

    if is_en:
        status_txt = (
            f"<b>📊 Printer Status: {target_printer.name}</b>\n\n"
            f"{state_emoji} <b>State:</b> <code>{state_label}</code>{wifi_str}\n"
            f"{print_info_str}"
            f"🌐 <b>IP:</b> <tg-spoiler>{target_printer.ip}</tg-spoiler>\n"
            f"🔑 <b>Access Code:</b> <tg-spoiler>{target_printer.access_code}</tg-spoiler>\n"
            f"🔢 <b>SN:</b> <tg-spoiler>{target_printer.serial_number}</tg-spoiler>\n"
            f"🔥 <b>Nozzle:</b> <code>{target_printer.nozzle_temper}°C{nozzle_target_str}</code> | 🛏️ <b>Bed:</b> <code>{target_printer.bed_temper}°C{bed_target_str}</code>{chamber_str}\n"
            f"🧵 <b>Filament Type:</b> {type_str}\n"
            f"📦 <b>Spool Remaining:</b> {spool_str}\n"
            f"{hours_str}"
        )
    else:
        status_txt = (
            f"<b>📊 Стан принтера: {target_printer.name}</b>\n\n"
            f"{state_emoji} <b>Стан:</b> <code>{state_label}</code>{wifi_str}\n"
            f"{print_info_str}"
            f"🌐 <b>IP:</b> <tg-spoiler>{target_printer.ip}</tg-spoiler>\n"
            f"🔑 <b>Access Code:</b> <tg-spoiler>{target_printer.access_code}</tg-spoiler>\n"
            f"🔢 <b>SN:</b> <tg-spoiler>{target_printer.serial_number}</tg-spoiler>\n"
            f"🔥 <b>Сопло:</b> <code>{target_printer.nozzle_temper}°C{nozzle_target_str}</code> | 🛏️ <b>Стіл:</b> <code>{target_printer.bed_temper}°C{bed_target_str}</code>{chamber_str}\n"
            f"🧵 <b>Тип пластику:</b> {type_str}\n"
            f"📦 <b>Залишок на бабіні:</b> {spool_str}\n"
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


async def printer_view_state_filter(message: Message, app) -> bool:
    if not message.text or not message.text.startswith("🖨️ "):
        return False
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    return user.get("state") in [None, "", "idle", "printer_menu", "printers_list", "main_menu"]


@router.message(printer_view_state_filter)
async def handle_select_printer(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    p_name = message.text.replace("🖨️ ", "").strip()
    # 1. Prioritize exact name match first
    target_printer = next((p for p in app.printers.values() if p.name.strip().lower() == p_name.lower()), None)
    # 2. Fallback to substring only if exact match is not found
    if not target_printer:
        target_printer = next((p for p in app.printers.values() if p_name.lower() in p.name.lower()), None)

    if target_printer:
        user = await app.storage.load_user(chat_id)
        user["state"] = "printer_menu"
        user.setdefault("context_data", {})["selected_printer_id"] = target_printer.id
        await app.storage.save_user(user)

        from bot.keyboards import get_printer_menu_keyboard
        u_lang = user.get("language", "uk")
        card = build_printer_status_card(target_printer, is_en=(u_lang == "en"))
        await message.answer(card, parse_mode=ParseMode.HTML, reply_markup=get_printer_menu_keyboard(target_printer, lang=u_lang))


@router.message(F.text.lower().in_(["📷 камера", "📷 реальне фото (камера)", "фото", "камера", "📷 camera", "camera"]))
async def handle_printer_camera(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        await message.answer(
            "⚠️ Спочатку оберіть принтер у меню «🖨️ Принтери»."
            if u_lang != "en"
            else "⚠️ Please select a printer first in «🖨️ Printers»."
        )
        return

    from aiogram.types import BufferedInputFile
    from services.camera_stream import capture_real_camera_photo

    wait_txt = "📷 ⏳ Отримую кадр з камери... Зачекайте хвилинку!" if u_lang != "en" else "📷 ⏳ Fetching camera frame... Please wait!"
    msg_wait = await message.answer(wait_txt)
    photo_bytes = await capture_real_camera_photo(target_printer.ip, target_printer.access_code)
    if photo_bytes:
        photo_file = BufferedInputFile(photo_bytes, filename="real_camera.jpg")
        try:
            rem_m = int(getattr(target_printer, "mc_remaining_time", 0))
        except (TypeError, ValueError):
            rem_m = 0
        rem_fmt = format_remaining_time(rem_m, u_lang == "en")
        finish_str = get_finish_time_str(rem_m, u_lang == "en")
        finish_note = f" ({finish_str})" if finish_str else ""
        rem_str = f" | ⏱️ ~{rem_fmt}{finish_note}" if rem_fmt else ""
        try:
            pct_cam = int(getattr(target_printer, "mc_percent", 0))
        except (TypeError, ValueError):
            pct_cam = 0
        cap = (
            f"📷 <b>Жива камера: {html.escape(target_printer.name)}</b>\n"
            f"📊 Стан: <code>{target_printer.mapped_state}</code> | ⏳ <code>{pct_cam}%</code>{rem_str}"
        )
        await message.answer_photo(photo=photo_file, caption=cap, parse_mode=ParseMode.HTML)
        try:
            await msg_wait.delete()
        except Exception:
            pass
    else:
        err_msg = (
            f"⚠️ <b>Порт камери недоступний для {html.escape(target_printer.name)}</b> ({target_printer.ip}:6000)\n"
            f"Перевірте Access Code або закрийте Bambu Handy на телефоні."
            if u_lang != "en"
            else f"⚠️ <b>Camera port unreachable for {html.escape(target_printer.name)}</b> ({target_printer.ip}:6000)\nCheck Access Code or close Bambu Handy."
        )
        await message.answer(err_msg, parse_mode=ParseMode.HTML)
        try:
            await msg_wait.delete()
        except Exception:
            pass


