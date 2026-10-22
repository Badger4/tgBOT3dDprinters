"""
Delete spool handlers.
"""

import html
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from bot.keyboards import (
    get_confirm_delete_spool_keyboard,
    get_filament_menu_keyboard,
    get_spools_keyboard,
)
from utils.filament_utils import get_color_emoji

router = Router()

DELETE_STATES = {
    "select_spool_to_delete",
    "confirm_delete_spool",
}


@router.message(F.text.lower().in_(["🗑️ видалити котушку", "видалити котушку", "🗑️ видалити", "видалити", "🗑️ delete spool", "delete spool", "🗑️ delete", "delete"]))
async def handle_delete_spool_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    spools = await app.storage.load_spools()
    warehouse_spools = {s_id: s for s_id, s in spools.items() if not s.get("assigned_printer_id")}
    if not warehouse_spools:
        await message.answer(
            "⚠️ На Складі немає вільних котушок для видалення (усі встановлені на принтери або склад порожній)."
            if u_lang != "en"
            else "⚠️ No free spools available to delete in warehouse (all mounted or stock is empty)."
        )
        return

    user["state"] = "select_spool_to_delete"
    await app.storage.save_user(user)
    await message.answer(
        "🗑️ <b>Оберіть котушку для видалення:</b>" if u_lang != "en" else "🗑️ <b>Select spool to delete:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_spools_keyboard(warehouse_spools, lang=u_lang),
    )


async def handle_delete_states(message: Message, app, user: dict, state: str, text: str) -> bool:
    chat_id = str(message.chat.id)
    u_lang = user.get("language", "uk")
    ctx_data = user.get("context_data", {})

    if state == "select_spool_to_delete":
        spools = await app.storage.load_spools()
        candidate_spools = [s for s in spools.values() if not s.get("assigned_printer_id")]
        selected = None
        for s in candidate_spools:
            s_name = s.get("name", "Spool")
            s_grams = s.get("remaining_grams", 1000.0)
            s_type = s.get("type", "")
            qty = max(1, int(s.get("quantity", 1) or 1))
            color_emoji = get_color_emoji(s.get("color_name") or s.get("color", ""))
            c_prefix = f"{color_emoji} " if color_emoji else ""
            type_str = f"{s_type}, " if (s_type and s_type.lower() not in s_name.lower()) else ""
            qty_unit = "pcs" if u_lang == "en" else "шт"
            qty_str = f" [📦 {qty} {qty_unit}]" if qty > 1 else ""
            qty_str_alt = f" [📦 {qty} {'шт' if qty_unit == 'pcs' else 'pcs'}]" if qty > 1 else ""
            exact_title = f"🧵 {c_prefix}{s_name} ({type_str}{s_grams}g){qty_str}"
            exact_title_alt = f"🧵 {c_prefix}{s_name} ({type_str}{s_grams}g){qty_str_alt}"

            if text in [exact_title, exact_title_alt, s_name, s.get("id")] or text.strip() == s_name.strip():
                selected = s
                break
        if not selected:
            for s in candidate_spools:
                s_name = s.get("name", "")
                if s_name and (s_name.lower() in text.lower() or text.lower() in s_name.lower() or s.get("id") == text.strip()):
                    selected = s
                    break

        if selected:
            user["context_data"]["delete_spool_id"] = selected["id"]
            user["state"] = "confirm_delete_spool"
            await app.storage.save_user(user)

            await message.answer(
                f"⚠️ <b>Ви впевнені, що хочете видалити котушку «{html.escape(selected.get('name', ''))}» ({selected.get('remaining_grams', 1000.0)}g)?</b>"
                if u_lang != "en" else
                f"⚠️ <b>Are you sure you want to delete spool «{html.escape(selected.get('name', ''))}» ({selected.get('remaining_grams', 1000.0)}g)?</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_confirm_delete_spool_keyboard(lang=u_lang),
            )
        else:
            await message.answer(
                "⚠️ Оберіть котушку зі списку на клавіатурі."
                if u_lang != "en" else
                "⚠️ Please select a spool from the keyboard list."
            )
        return True

    if state == "confirm_delete_spool":
        spool_id = ctx_data.get("delete_spool_id")
        spools = await app.storage.load_spools()
        low = text.lower()
        if any(k in low for k in ["так", "yes", "delete", "видалити"]):
            sp = spools.pop(spool_id, None) if spool_id else None
            if sp:
                p_id = sp.get("assigned_printer_id")
                slot_k = sp.get("assigned_slot_key")
                if p_id and p_id in app.printers and slot_k:
                    app.printers[p_id].set_slot_grams(0.0, slot_id=str(slot_k))
                    await app.save_printers_config()
                await app.storage.save_spools(spools)

                prev_w = float(sp.get("remaining_grams", 0.0))
                await app.storage.record_spool_movement(
                    spool_id=spool_id,
                    spool_name=sp.get("name", "Котушка"),
                    action="write_off",
                    weight_change_g=-prev_w,
                    prev_weight_g=prev_w,
                    new_weight_g=0.0,
                    reason="Списання / Видалення котушки зі складу (Telegram)",
                    user=user.get("username") or user.get("first_name") or f"TG:{chat_id}",
                )

                user["state"] = "idle"
                user.get("context_data", {}).pop("delete_spool_id", None)
                await app.storage.save_user(user)

                await message.answer(
                    f"✅ <b>Котушку «{html.escape(sp.get('name', ''))}» успішно видалено!</b>"
                    if u_lang != "en" else
                    f"✅ <b>Spool «{html.escape(sp.get('name', ''))}» successfully deleted!</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_filament_menu_keyboard(lang=u_lang),
                )
            else:
                user["state"] = "idle"
                user.get("context_data", {}).pop("delete_spool_id", None)
                await app.storage.save_user(user)
                await message.answer("⚠️ Котушку не знайдено.", reply_markup=get_filament_menu_keyboard(lang=u_lang))
        else:
            user["state"] = "idle"
            user.get("context_data", {}).pop("delete_spool_id", None)
            await app.storage.save_user(user)
            await message.answer(
                "❌ Видалення котушки скасовано."
                if u_lang != "en" else
                "❌ Spool deletion cancelled.",
                reply_markup=get_filament_menu_keyboard(lang=u_lang),
            )
        return True

    return False

