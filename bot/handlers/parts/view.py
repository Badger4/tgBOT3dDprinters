"""
Parts warehouse view handlers.
"""

import html
from pathlib import Path
from typing import Any
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, Message, ReplyKeyboardMarkup, FSInputFile
from config import logger
from bot.keyboards import (
    construct_part_info_keyboard,
    get_part_action_reply_keyboard,
    get_parts_inline_keyboard,
    get_parts_reply_keyboard,
)
from bot.states import PartEditingStates
from utils.i18n import get_user_lang

router = Router()


async def open_parts_list(message: Message, state: FSMContext, app: Any, lang: str = "uk") -> None:
    await state.set_state(PartEditingStates.in_parts_list)
    parts: dict[str, dict[str, Any]] = await app.storage.load_parts()

    text_keyboard = get_parts_reply_keyboard(lang)
    inline_keyboard = get_parts_inline_keyboard(parts)

    await message.answer(".", reply_markup=text_keyboard)
    if not parts:
        await message.answer(
            "🧩 <b>Склад деталей порожній!</b>\nНатисніть <b>Добавити</b>, щоб додати першу деталь.",
            parse_mode=ParseMode.HTML,
            reply_markup=inline_keyboard,
        )
    else:
        await message.answer("Список деталей:", reply_markup=inline_keyboard)


@router.message(F.text.in_(["🧩 Склад деталей", "🧩 Parts Stock", "Склад деталей", "3Д"]))
async def handle_parts_warehouse_btn(message: Message, state: FSMContext, app: Any) -> None:
    await state.clear()
    u_data = await app.storage.load_user(message.from_user.id)
    lang = get_user_lang(u_data)
    await open_parts_list(message, state, app, lang)


async def send_part_info(target_message: Message, part: dict[str, Any], text_keyboard: ReplyKeyboardMarkup, inline_keyboard: InlineKeyboardMarkup) -> None:
    await target_message.answer(".", reply_markup=text_keyboard)

    img = str(part.get("image", "") or "").strip()
    name = html.escape(part.get("name", "Деталь"))
    p_model = part.get("printer_model")
    model_para = f"\n🖨️ <b>Принтер:</b> {html.escape(p_model)}" if p_model and p_model != "Unknown" else ""
    cnt = part.get("count", part.get("quantity", 0))
    caption_text = f"🧩 <b>{name}</b>{model_para}\n📦 <b>Кількість:</b> {cnt} шт"

    photo_sent = False
    if img:
        try:
            if img.startswith("http://") or img.startswith("https://") or (len(img) > 15 and "/" not in img and "\\" not in img):
                await target_message.answer_photo(photo=img, caption=caption_text, parse_mode=ParseMode.HTML, reply_markup=inline_keyboard)
                photo_sent = True
            else:
                import config
                img_file_name = Path(img).name
                p = config.STORAGE_DIR / "uploads" / img_file_name
                if not p.exists():
                    p = Path(img)
                if not p.exists():
                    p = config.STORAGE_DIR / img
                if p.exists():
                    await target_message.answer_photo(photo=FSInputFile(p), caption=caption_text, parse_mode=ParseMode.HTML, reply_markup=inline_keyboard)
                    photo_sent = True
        except Exception as e:
            logger.warning(f"Error sending photo [{img}]: {e}")

    if not photo_sent:
        await target_message.answer(caption_text, parse_mode=ParseMode.HTML, reply_markup=inline_keyboard)


@router.message(
    PartEditingStates.in_parts_list,
    F.text.in_(["🔍 Пошук", "🔍 Search", "🔍 Пошук деталі", "Пошук деталі", "Пошук"]),
)
@router.message(F.text.in_(["🔍 Пошук", "🔍 Search", "🔍 Пошук деталі", "🔍 Search Part"]))
async def handle_search_part_btn(message: Message, state: FSMContext) -> None:
    await state.set_state(PartEditingStates.search_query)
    await message.answer("🔍 <b>Введіть назву деталі для пошуку:</b>", parse_mode=ParseMode.HTML)


@router.message(PartEditingStates.search_query)
async def process_search_part_query(message: Message, state: FSMContext, app: Any) -> None:
    query = (message.text or "").strip().lower()
    parts: dict[str, dict[str, Any]] = await app.storage.load_parts()

    filtered = {
        pid: p
        for pid, p in parts.items()
        if query in (p.get("name") or "").lower() or query in (p.get("printer_model") or "").lower()
    }

    if not filtered:
        await message.answer(
            f"🔍 <b>За запитом «{html.escape(query)}» нічого не знайдено!</b>\nВведіть іншу назву або оберіть з меню:",
            parse_mode=ParseMode.HTML,
        )
        return

    kb = get_parts_inline_keyboard(filtered)
    await state.set_state(PartEditingStates.in_parts_list)
    await message.answer(
        f"🔍 <b>Знайдено деталей: {len(filtered)}</b>\nОберіть деталь зі списку:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


@router.message(
    PartEditingStates.in_parts_list,
    F.text.lower().in_(
        [
            "назад", "back", "⬅️ назад", "⬅️ back", "⬅️ до списку деталей",
            "до списку деталей", "⬅️ back to parts", "back to parts", "⬅️ назад до списку", "назад до списку",
        ]
    ),
)
@router.message(
    PartEditingStates.in_part_info,
    F.text.lower().in_(
        [
            "назад", "back", "⬅️ назад", "⬅️ back", "⬅️ до списку деталей",
            "до списку деталей", "⬅️ back to parts", "back to parts", "⬅️ назад до списку", "назад до списку",
        ]
    ),
)
@router.message(
    F.text.lower().in_(
        [
            "⬅️ до списку деталей", "до списку деталей", "⬅️ back to parts", "back to parts", "⬅️ назад до списку деталей",
        ]
    )
)
async def back_to_main_menu_or_list(message: Message, state: FSMContext, app: Any) -> None:
    current_state = await state.get_state()
    u_data = await app.storage.load_user(message.from_user.id)
    lang = get_user_lang(u_data)
    is_admin = await app.is_user_admin(message.from_user.id)

    if current_state in (
        PartEditingStates.in_part_info,
        PartEditingStates.property_edit,
        PartEditingStates.select_part_for_print,
        PartEditingStates.select_part_for_edit,
        PartEditingStates.select_part_for_delete,
    ):
        await open_parts_list(message, state, app, lang)
    else:
        await state.clear()
        kb = get_main_keyboard(is_admin=is_admin, lang=lang)
        from utils.i18n import t
        await message.answer(t("warehouse_title", lang), reply_markup=kb)


@router.message(
    F.text.lower().in_(
        [
            "📊 звіт деталей (pdf)", "звіт деталей (pdf)", "📊 parts report (pdf)", "parts report (pdf)",
            "🧩 звіт pdf деталей", "звіт pdf деталей", "звіт деталей pdf", "📊 звіт pdf деталей",
            "звіт деталей", "звіт по деталях", "/pdf_parts", "pdf parts",
        ]
    )
)
async def handle_parts_pdf_report_bot(message: Message, app: Any):
    import time
    from aiogram.types import BufferedInputFile
    from services.report_generator import generate_parts_pdf_report

    parts = await app.storage.load_parts()
    pdf_bytes = generate_parts_pdf_report(parts)
    date_str = time.strftime("%Y-%m-%d_%H-%M")
    doc_file = BufferedInputFile(pdf_bytes, filename=f"parts_report_{date_str}.pdf")

    await message.answer_document(
        doc_file,
        caption="🧩 <b>PDF Звіт складу готових деталей згенеровано!</b>\n\nФайл містить виключно перелік усіх готових 3D деталей із назвою, моделлю принтера, пластиком, ціною, вагою та кількістю.",
        parse_mode=ParseMode.HTML,
    )


@router.message(
    F.text.lower().in_(
        [
            "🧵 звіт котушок (pdf)", "звіт котушок (pdf)", "🧵 звіт pdf котушок", "звіт pdf котушок",
            "звіт котушок pdf", "звіт котушок", "/pdf_spools", "pdf spools",
        ]
    )
)
async def handle_spools_pdf_report_bot(message: Message, app: Any):
    import time
    from aiogram.types import BufferedInputFile
    from services.report_generator import generate_spools_pdf_report

    spools = await app.storage.load_spools()
    pdf_bytes = generate_spools_pdf_report(spools)
    date_str = time.strftime("%Y-%m-%d_%H-%M")
    doc_file = BufferedInputFile(pdf_bytes, filename=f"spools_report_{date_str}.pdf")

    await message.answer_document(
        doc_file,
        caption="🧵 <b>PDF Звіт складу котушок пластику згенеровано!</b>\n\nФайл містить перелік усіх котушок на складі із залишками, ціною та статусом прив'язки до принтерів.",
        parse_mode=ParseMode.HTML,
    )


@router.message(
    F.text.lower().in_(
        [
            "🏢 загальний звіт складу (pdf)", "загальний звіт складу (pdf)", "🏢 загальний звіт (pdf)",
            "загальний звіт (pdf)", "📊 звіт pdf склада", "звіт pdf склада", "звіт всього складу",
            "звіт всього складу (pdf)", "pdf склад", "📊 pdf warehouse", "pdf warehouse", "/pdf_warehouse",
        ]
    )
)
async def handle_warehouse_pdf_report_bot(message: Message, app: Any):
    import time
    from aiogram.types import BufferedInputFile
    from services.report_generator import generate_warehouse_pdf_report

    spools = await app.storage.load_spools()
    parts = await app.storage.load_parts()
    pdf_bytes = generate_warehouse_pdf_report(spools, parts, report_type="all")
    date_str = time.strftime("%Y-%m-%d_%H-%M")
    doc_file = BufferedInputFile(pdf_bytes, filename=f"warehouse_report_{date_str}.pdf")

    await message.answer_document(
        doc_file,
        caption="📊 <b>Повний PDF звіт складу згенеровано!</b>\n\nФайл містить окремі блоки для <b>Котушок пластику</b> та <b>Готових деталей</b>.",
        parse_mode=ParseMode.HTML,
    )

