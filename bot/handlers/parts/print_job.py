"""
Send part to print job handlers.
"""

from typing import Any
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from bot.states import PartEditingStates

router = Router()


@router.message(
    PartEditingStates.in_parts_list,
    F.text.lower().in_(["друк", "🚀 друк", "print", "🚀 кинути на друк", "кинути на друк", "🚀 send to print", "send to print"])
)
@router.message(
    PartEditingStates.in_part_info,
    F.text.lower().in_(["друк", "🚀 друк", "print", "🚀 кинути на друк", "кинути на друк", "🚀 send to print", "send to print"])
)
@router.message(
    F.text.lower().in_(["🚀 кинути на друк", "кинути на друк", "🚀 send to print", "send to print"])
)
async def handle_print_part_start(message: Message, state: FSMContext, app: Any) -> None:
    data = await state.get_data()
    part_id = data.get("selected_part_id")
    parts = await app.storage.load_parts()
    if not parts:
        await message.answer("⚠️ На Складі немає деталей для друку.")
        return

    if part_id and part_id in parts:
        from bot.keyboards import get_printer_select_inline_keyboard
        part = parts[part_id]
        ikb = get_printer_select_inline_keyboard(part_id, app.printers, part=part)
        await message.answer(f"🖨️ <b>Оберіть принтер для друку деталі «{part.get('name', 'Деталь')}»:</b>", parse_mode="HTML", reply_markup=ikb)
    else:
        from bot.keyboards import get_parts_inline_keyboard
        await state.set_state(PartEditingStates.select_part_for_print)
        await message.answer("Оберіть деталь для відправки на друк:", reply_markup=get_parts_inline_keyboard(parts))

