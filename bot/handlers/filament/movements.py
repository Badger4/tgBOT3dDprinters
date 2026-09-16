"""
Spool warehouse movements audit log and PDF export handlers.
"""

import html
import math
import time
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.keyboards import (
    get_filament_menu_keyboard,
    get_spool_filter_keyboard,
    get_spool_movements_keyboard,
    get_warehouse_pdf_keyboard,
)

router = Router()

ITEMS_PER_PAGE = 5

ACTION_MAP_UK = {
    "initial_stock": "📦 Внесення на склад",
    "refill": "➕ Поповнення",
    "manual_edit": "✏️ Ручне коригування",
    "write_off": "🗑️ Списання / Видалення",
    "print": "🖨️ Списання друком",
}

ACTION_MAP_EN = {
    "initial_stock": "📦 Initial Stock",
    "refill": "➕ Refill",
    "manual_edit": "✏️ Manual Edit",
    "write_off": "🗑️ Write-off",
    "print": "🖨️ Print Deduction",
}


def format_movement_entry(m: dict, is_en: bool = False) -> str:
    dt = m.get("datetime") or time.strftime("%Y-%m-%d %H:%M", time.localtime(m.get("timestamp", 0)))
    spool_name = html.escape(str(m.get("spool_name") or "Котушка"))
    action_code = m.get("action", "")
    action_map = ACTION_MAP_EN if is_en else ACTION_MAP_UK
    action_label = action_map.get(action_code, f"⚡ {action_code}")
    ch_g = float(m.get("weight_change_g", 0.0))
    ch_sign = f"+{ch_g:.1f}" if ch_g > 0 else f"{ch_g:.1f}"
    prev_g = float(m.get("prev_weight_g", 0.0))
    new_g = float(m.get("new_weight_g", 0.0))
    reason = html.escape(str(m.get("reason") or ""))
    user = html.escape(str(m.get("user") or "System"))

    txt = f"• 📅 <b>{dt}</b> — 🧵 <b>{spool_name}</b>\n"
    txt += f"   {action_label} | <b>{ch_sign}g</b> ({prev_g:.0f}g ➔ <b>{new_g:.0f}g</b>)\n"
    if reason:
        txt += f"   📝 <i>{reason}</i> (👤 {user})\n"
    return txt


def build_movements_page_text(
    movements: list[dict],
    page: int,
    spool_filter: str = "all",
    spool_name_filter: str = "",
    is_en: bool = False,
) -> tuple[str, int]:
    total_count = len(movements)
    if total_count == 0:
        if spool_filter != "all":
            msg = (
                f"🔍 <b>Movement Audit:</b>\nNo recorded movements for spool <b>{html.escape(spool_name_filter)}</b>."
                if is_en
                else f"🔍 <b>Аудит руху:</b>\nНемає записів для котушки <b>{html.escape(spool_name_filter)}</b>."
            )
        else:
            msg = (
                "📜 <b>Spool Movements Audit Log</b>\n\n"
                "ℹ️ <i>Audit log is currently empty. Any warehouse operations (adding, refilling, printing, write-offs) will be recorded here automatically.</i>"
                if is_en
                else "📜 <b>Журнал аудиту руху матеріалів складу</b>\n\n"
                "ℹ️ <i>Журнал аудиту наразі порожній. Будь-які операції (додавання, поповнення, друк, списання) фіксуватимуться тут автоматично.</i>"
            )
        return msg, 1

    total_pages = max(1, math.ceil(total_count / ITEMS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))

    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_items = movements[start_idx:end_idx]

    filter_info = ""
    if spool_filter != "all" and spool_name_filter:
        filter_info = f"\n🔍 Фільтр: <b>{html.escape(spool_name_filter)}</b>" if not is_en else f"\n🔍 Filter: <b>{html.escape(spool_name_filter)}</b>"

    header = (
        f"📜 <b>Журнал аудиту руху матеріалів складу</b>{filter_info}\n"
        f"📊 Загалом записів: <b>{total_count}</b> | Стор. <b>{page + 1}/{total_pages}</b>\n\n"
        if not is_en
        else f"📜 <b>Warehouse Movements Audit Log</b>{filter_info}\n"
        f"📊 Total records: <b>{total_count}</b> | Page <b>{page + 1}/{total_pages}</b>\n\n"
    )

    body = "\n".join(format_movement_entry(m, is_en=is_en) for m in page_items)
    return f"{header}{body}", total_pages


@router.message(
    F.text.lower().in_(
        [
            "📜 аудит руху",
            "аудит руху",
            "📜 аудит",
            "аудит",
            "📜 movement audit",
            "movement audit",
            "movement log",
            "audit log",
            "audit",
        ]
    )
)
async def handle_spool_movements_view(message: Message, app, state: FSMContext | None = None):
    if state:
        await state.clear()
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    movements = await app.storage.load_spool_movements()
    movements = sorted(movements, key=lambda x: x.get("timestamp", 0), reverse=True)

    text, total_pages = build_movements_page_text(movements, page=0, spool_filter="all", is_en=is_en)
    kb = get_spool_movements_keyboard(page=0, total_pages=total_pages, spool_filter="all", lang=u_lang)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)


@router.callback_query(F.data.startswith("mov_page:"))
async def handle_movements_page_callback(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    parts = callback.data.split(":")
    page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    spool_filter = parts[2] if len(parts) > 2 else "all"

    movements = await app.storage.load_spool_movements()
    spool_name_filter = ""
    if spool_filter != "all":
        spools = await app.storage.load_spools()
        spool_name_filter = spools.get(spool_filter, {}).get("name", spool_filter)
        movements = [m for m in movements if m.get("spool_id") == spool_filter]

    movements = sorted(movements, key=lambda x: x.get("timestamp", 0), reverse=True)
    text, total_pages = build_movements_page_text(
        movements, page=page, spool_filter=spool_filter, spool_name_filter=spool_name_filter, is_en=is_en
    )
    kb = get_spool_movements_keyboard(page=page, total_pages=total_pages, spool_filter=spool_filter, lang=u_lang)

    try:
        if callback.message:
            await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "mov_filter_menu")
async def handle_movements_filter_menu_callback(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    spools = await app.storage.load_spools()
    kb = get_spool_filter_keyboard(spools, current_filter="all", lang=u_lang)
    msg_text = (
        "🔍 <b>Оберіть котушку для фільтрації журналу аудиту:</b>"
        if not is_en
        else "🔍 <b>Select spool to filter audit movements:</b>"
    )
    try:
        if callback.message:
            await callback.message.edit_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("mov_filter:"))
async def handle_movements_filter_select_callback(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    spool_filter = callback.data.split(":", 1)[1]
    movements = await app.storage.load_spool_movements()
    spool_name_filter = ""
    if spool_filter != "all":
        spools = await app.storage.load_spools()
        spool_name_filter = spools.get(spool_filter, {}).get("name", spool_filter)
        movements = [m for m in movements if m.get("spool_id") == spool_filter]

    movements = sorted(movements, key=lambda x: x.get("timestamp", 0), reverse=True)
    text, total_pages = build_movements_page_text(
        movements, page=0, spool_filter=spool_filter, spool_name_filter=spool_name_filter, is_en=is_en
    )
    kb = get_spool_movements_keyboard(page=0, total_pages=total_pages, spool_filter=spool_filter, lang=u_lang)

    try:
        if callback.message:
            await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "mov_filter_clear")
async def handle_movements_filter_clear(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    movements = await app.storage.load_spool_movements()
    movements = sorted(movements, key=lambda x: x.get("timestamp", 0), reverse=True)
    text, total_pages = build_movements_page_text(movements, page=0, spool_filter="all", is_en=is_en)
    kb = get_spool_movements_keyboard(page=0, total_pages=total_pages, spool_filter="all", lang=u_lang)

    try:
        if callback.message:
            await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception:
        pass
    await callback.answer("✅ Фільтр скинуто" if not is_en else "✅ Filter cleared")


@router.message(
    F.text.lower().in_(
        [
            "📄 експорт pdf",
            "експорт pdf",
            "📄 pdf",
            "📄 export pdf",
            "export pdf",
        ]
    )
)
async def handle_export_warehouse_pdf_menu(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    kb = get_warehouse_pdf_keyboard(lang=u_lang)
    msg_txt = (
        "📄 <b>Експорт звітів складу в PDF</b>\n\n"
        "Оберіть необхідний тип документа для завантаження:"
        if not is_en
        else "📄 <b>Warehouse PDF Export</b>\n\n"
        "Select the report type you wish to download:"
    )
    await message.answer(msg_txt, parse_mode=ParseMode.HTML, reply_markup=kb)


@router.callback_query(F.data.in_(["mov_export_pdf", "pdf_export_movements"]))
async def handle_export_movements_pdf_callback(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    await callback.answer("⏳ Формування PDF звіту..." if not is_en else "⏳ Generating PDF report...")
    try:
        movements = await app.storage.load_spool_movements()
        from services.report_generator import generate_movements_pdf_report
        pdf_bytes = generate_movements_pdf_report(movements)

        filename = f"spool_movements_audit_{int(time.time())}.pdf"
        doc = BufferedInputFile(pdf_bytes, filename=filename)
        cap = (
            "📜 <b>Журнал аудиту руху матеріалів складу (PDF)</b>"
            if not is_en
            else "📜 <b>Warehouse Movements Audit Log (PDF)</b>"
        )
        if callback.message:
            await callback.message.answer_document(doc, caption=cap, parse_mode=ParseMode.HTML)
        elif callback.bot:
            await callback.bot.send_document(chat_id=callback.from_user.id, document=doc, caption=cap, parse_mode=ParseMode.HTML)
    except Exception as e:
        if callback.message:
            await callback.message.answer(f"⚠️ Помилка формування PDF: {e}")


@router.callback_query(F.data == "pdf_export_spools")
async def handle_export_spools_pdf_callback(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    await callback.answer("⏳ Формування PDF звіту..." if not is_en else "⏳ Generating PDF report...")
    try:
        spools = await app.storage.load_spools()
        from services.report_generator import generate_spools_pdf_report
        pdf_bytes = generate_spools_pdf_report(spools)

        filename = f"spools_inventory_{int(time.time())}.pdf"
        doc = BufferedInputFile(pdf_bytes, filename=filename)
        cap = (
            "📦 <b>Звіт залишків котушок на складі (PDF)</b>"
            if not is_en
            else "📦 <b>Spool Stock Inventory Report (PDF)</b>"
        )
        if callback.message:
            await callback.message.answer_document(doc, caption=cap, parse_mode=ParseMode.HTML)
        elif callback.bot:
            await callback.bot.send_document(chat_id=callback.from_user.id, document=doc, caption=cap, parse_mode=ParseMode.HTML)
    except Exception as e:
        if callback.message:
            await callback.message.answer(f"⚠️ Помилка формування PDF: {e}")


@router.callback_query(F.data == "pdf_export_both")
async def handle_export_both_pdfs_callback(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    await callback.answer("⏳ Формування PDF звітів..." if not is_en else "⏳ Generating PDF reports...")
    try:
        spools = await app.storage.load_spools()
        movements = await app.storage.load_spool_movements()
        from services.report_generator import generate_movements_pdf_report, generate_spools_pdf_report

        doc_spools = BufferedInputFile(generate_spools_pdf_report(spools), filename=f"spools_inventory_{int(time.time())}.pdf")
        doc_movements = BufferedInputFile(generate_movements_pdf_report(movements), filename=f"spool_movements_audit_{int(time.time())}.pdf")

        if callback.message:
            await callback.message.answer_document(
                doc_spools,
                caption="📦 <b>Звіт залишків котушок на складі (PDF)</b>" if not is_en else "📦 <b>Spool Stock Inventory Report (PDF)</b>",
                parse_mode=ParseMode.HTML,
            )
            await callback.message.answer_document(
                doc_movements,
                caption="📜 <b>Журнал аудиту руху матеріалів складу (PDF)</b>" if not is_en else "📜 <b>Warehouse Movements Audit Log (PDF)</b>",
                parse_mode=ParseMode.HTML,
            )
    except Exception as e:
        if callback.message:
            await callback.message.answer(f"⚠️ Помилка формування PDF: {e}")


@router.callback_query(F.data == "mov_noop")
async def handle_mov_noop(callback: CallbackQuery):
    await callback.answer()
