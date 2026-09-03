"""
Commercial Pricing Calculator and Preset Management Handlers.
"""

import html
import uuid

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from config import STORAGE_DIR
from models.commercial import calculate_commercial_price

PRESETS_PATH = STORAGE_DIR / "commercial_presets.json"

router = Router()

DEFAULT_PRESETS = {
    "default_pla": {
        "id": "default_pla",
        "name": "Стандарт PLA (850 грн/кг, +100%)",
        "price_per_g": 0.85,
        "electricity_rate_uah": 4.32,
        "power_watts": 120.0,
        "depreciation_val": "10",
        "consumables_val": "5",
        "profit_val": "100%",
    },
    "default_petg": {
        "id": "default_petg",
        "name": "PETG / Engineering (950 грн/кг, +100%)",
        "price_per_g": 0.95,
        "electricity_rate_uah": 4.32,
        "power_watts": 150.0,
        "depreciation_val": "15",
        "consumables_val": "8",
        "profit_val": "100%",
    },
}


def sanitize_commercial_presets(presets: dict) -> dict:
    if not isinstance(presets, dict):
        return {}
    clean = {}
    test_keywords = {"test", "тест", "тестовий", "sample", "demo"}
    for pid, p in presets.items():
        if not isinstance(p, dict):
            continue
        p_id_str = str(p.get("id") or pid).lower()
        p_name_str = str(p.get("name") or "").lower()
        if any(kw in p_id_str or kw in p_name_str for kw in test_keywords):
            continue
        clean[pid] = p
    return clean


async def get_user_presets(app) -> dict:
    presets = await app.storage.load_json(PRESETS_PATH, None)
    if presets is None:
        presets = DEFAULT_PRESETS.copy()
        await app.storage.save_json(PRESETS_PATH, presets)

    sanitized = sanitize_commercial_presets(presets)
    if len(sanitized) != len(presets):
        presets = sanitized
        await app.storage.save_json(PRESETS_PATH, presets)
    else:
        presets = sanitized
    return presets


def get_commercial_menu_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    is_en = lang == "en"
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🧮 Quick Price Calculation" if is_en else "🧮 Швидкий розрахунок ціни"),
                KeyboardButton(text="📊 Commercial Report (PDF)" if is_en else "📊 Комерційний звіт (PDF)"),
            ],
            [
                KeyboardButton(text="➕ Create Preset" if is_en else "➕ Створити пресет"),
                KeyboardButton(text="📋 Copy Preset" if is_en else "📋 Копіювати пресет"),
            ],
            [
                KeyboardButton(text="✏️ Edit Preset" if is_en else "✏️ Редагувати пресет"),
                KeyboardButton(text="🗑️ Delete Preset" if is_en else "🗑️ Видалити пресет"),
            ],
            [KeyboardButton(text="⬅️ Main Menu" if is_en else "⬅️ Головне меню")],
        ],
        resize_keyboard=True,
    )


@router.message(
    F.text.lower().in_(
        [
            "📊 комерційний звіт (pdf)",
            "комерційний звіт (pdf)",
            "📊 commercial report (pdf)",
            "commercial report (pdf)",
            "📊 звіт pdf",
            "звіт pdf",
            "комерційний звіт",
            "commercial report",
        ]
    )
)
async def handle_commercial_pdf_report(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    presets = await get_user_presets(app)

    import time
    from services.report_generator import generate_commercial_pdf_report

    pdf_bytes = generate_commercial_pdf_report(presets, lang=u_lang)
    now_f = time.strftime("%Y%m%d_%H%M%S")
    filename = f"commercial_report_{now_f}.pdf"
    doc_file = BufferedInputFile(pdf_bytes, filename=filename)
    cap = (
        "📊 <b>Комерційний PDF-звіт пресетів та розрахунку</b>"
        if u_lang != "en"
        else "📊 <b>Commercial PDF Presets & Calculation Report</b>"
    )
    await message.answer_document(doc_file, caption=cap, parse_mode=ParseMode.HTML)


@router.message(F.text.lower().in_(["💰 комерція", "комерція", "калькулятор ціни", "пресети", "💰 commercial", "commercial"]))
async def handle_commercial_menu(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    user["state"] = "idle"
    await app.storage.save_user(user)

    presets = await get_user_presets(app)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    if is_en:
        txt = (
            "<b>💰 Commercial Price Calculator</b>\n"
            "<i>Cost price & profit margin configuration for commercial 3D printing</i> 💼✨\n\n"
            "<b>📋 Available Presets:</b>\n"
        )
        for p in presets.values():
            p_name = html.escape(str(p.get("name", "Preset")))
            p_pr = p.get("price_per_g", 0.85)
            p_el = p.get("electricity_rate_uah", 4.32)
            p_depr = p.get("depreciation_val", "10")
            p_cons = p.get("consumables_val", "5")
            p_prof = p.get("profit_val", "100%")
            txt += (
                f"• <b>{p_name}</b>\n"
                f"  <i>Filament: {p_pr}UAH/g | Power: {p_el}UAH | Depr: {p_depr} | Consumables: {p_cons} | Margin: {p_prof}</i>\n"
            )
    else:
        txt = (
            "<b>💰 Комерційний калькулятор ціни</b>\n"
            "<i>Налаштування себевартості та маржі для комерційного друку</i> 💼✨\n\n"
            "<b>📋 Наявні пресети:</b>\n"
        )
        for p in presets.values():
            p_name = html.escape(str(p.get("name", "Пресет")))
            p_pr = p.get("price_per_g", 0.85)
            p_el = p.get("electricity_rate_uah", 4.32)
            p_depr = p.get("depreciation_val", "10")
            p_cons = p.get("consumables_val", "5")
            p_prof = p.get("profit_val", "100%")
            txt += (
                f"• <b>{p_name}</b>\n"
                f"  <i>Пластик: {p_pr}грн/г | Світло: {p_el}грн | Аморт: {p_depr} | Витрат: {p_cons} | Маржа: {p_prof}</i>\n"
            )

    await message.answer(txt, parse_mode=ParseMode.HTML, reply_markup=get_commercial_menu_keyboard(lang=u_lang))


@router.message(F.text.lower().in_(["➕ створити пресет", "створити пресет", "➕ create preset", "create preset"]))
async def start_add_preset(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    user["state"] = "add_preset_name"
    user["context_data"]["new_preset"] = {}
    await app.storage.save_user(user)

    u_lang = user.get("language", "uk")
    await message.answer(
        "➕ <b>Створення нового пресету</b>\nStep 1/6: Введіть назву пресету (наприклад: <i>PLA Sunlu Black</i>):" if u_lang != "en" else "➕ <b>Create New Preset</b>\nStep 1/6: Enter preset name (e.g. <i>PLA Sunlu Black</i>):",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад" if u_lang != "en" else "⬅️ Back")]], resize_keyboard=True),
    )


@router.message(F.text.lower().in_(["📋 копіювати пресет", "копіювати пресет", "📋 copy preset", "copy preset"]))
async def start_copy_preset(message: Message, app):
    chat_id = str(message.chat.id)
    presets = await get_user_presets(app)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    if not presets:
        await message.answer("⚠️ Немає наявних пресетів для копіювання." if u_lang != "en" else "⚠️ No presets available to copy.")
        return

    user["state"] = "select_preset_to_copy"
    await app.storage.save_user(user)

    kb = [[KeyboardButton(text=p["name"])] for p in presets.values()]
    kb.append([KeyboardButton(text="⬅️ Назад" if u_lang != "en" else "⬅️ Back")])
    await message.answer(
        "📋 <b>Оберіть пресет, який хочете скопіювати:</b>\n"
        "<i>Ви зможете дати нову назву і змінити тільки потрібні параметри!</i>" if u_lang != "en" else "📋 <b>Select preset to copy:</b>\n<i>You will be able to set a new name and update parameters!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True),
    )


@router.message(F.text.lower().in_(["✏️ редагувати пресет", "редагувати пресет", "✏️ edit preset", "edit preset"]))
async def start_edit_preset(message: Message, app):
    chat_id = str(message.chat.id)
    presets = await get_user_presets(app)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    if not presets:
        await message.answer("⚠️ Немає наявних пресетів для редагування." if u_lang != "en" else "⚠️ No presets available to edit.")
        return

    user["state"] = "select_preset_to_edit"
    await app.storage.save_user(user)

    kb = [[KeyboardButton(text=p["name"])] for p in presets.values()]
    kb.append([KeyboardButton(text="⬅️ Назад" if u_lang != "en" else "⬅️ Back")])
    await message.answer(
        "✏️ <b>Оберіть пресет для редагування:</b>" if u_lang != "en" else "✏️ <b>Select preset to edit:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True),
    )


@router.message(F.text.lower().in_(["🗑️ видалити пресет", "видалити пресет", "🗑️ delete preset", "delete preset"]))
async def start_delete_preset(message: Message, app):
    chat_id = str(message.chat.id)
    presets = await get_user_presets(app)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    if not presets:
        await message.answer("⚠️ Немає наявних пресетів для видалення." if u_lang != "en" else "⚠️ No presets available to delete.")
        return

    user["state"] = "select_preset_to_delete"
    await app.storage.save_user(user)

    kb = [[KeyboardButton(text=p["name"])] for p in presets.values()]
    kb.append([KeyboardButton(text="⬅️ Назад" if u_lang != "en" else "⬅️ Back")])
    await message.answer(
        "🗑️ <b>Оберіть пресет для видалення:</b>" if u_lang != "en" else "🗑️ <b>Select preset to delete:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True),
    )


@router.message(F.text.lower().in_(["🧮 швидкий розрахунок ціни", "розрахунок ціни", "розрахувати", "🧮 quick price calculation", "quick price calculation", "quick calc"]))
async def start_quick_calc(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    user["state"] = "calc_enter_weight"
    await app.storage.save_user(user)

    await message.answer(
        "🧮 <b>Швидкий розрахунок ціни друку</b>\nВведіть масу деталі у грамах (наприклад: <code>150</code>):",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True),
    )


COMMERCIAL_STATES = {
    "add_preset_name",
    "add_preset_price",
    "add_preset_elec",
    "add_preset_depr",
    "add_preset_cons",
    "add_preset_profit",
    "select_preset_to_copy",
    "copy_preset_new_name",
    "select_preset_to_edit",
    "edit_preset_field",
    "select_preset_to_delete",
    "calc_enter_weight",
    "calc_enter_time",
    "calc_select_preset",
    "edit_preset_field_value",
}


async def is_commercial_wizard_state(message: Message, app) -> bool:
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    return user.get("state", "") in COMMERCIAL_STATES


@router.message(is_commercial_wizard_state)
async def handle_commercial_wizard(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    st = user.get("state", "")

    text = message.text.strip()
    if text.lower() in ["⬅️ назад", "назад", "скасувати"]:
        user["state"] = "idle"
        await app.storage.save_user(user)
        await handle_commercial_menu(message, app)
        return

    presets = await get_user_presets(app)
    c_data = user.get("context_data", {})

    # 1. ADD PRESET WIZARD
    if st == "add_preset_name":
        c_data["new_preset"] = {"id": str(uuid.uuid4()), "name": text}
        user["state"] = "add_preset_price"
        await app.storage.save_user(user)
        await message.answer(
            "Step 2/6: Введіть ціну нитки за 1 грам або за 1 кг (наприклад: <code>0.85</code> або <code>850</code>):",
            parse_mode=ParseMode.HTML,
        )
        return True

    elif st == "add_preset_price":
        try:
            val = float(text.replace(",", "."))
            price_g = val / 1000.0 if val >= 50 else val
        except ValueError:
            await message.answer("⚠️ Введіть числову ціну (наприклад: 0.85 або 850).")
            return True
        c_data["new_preset"]["price_per_g"] = price_g
        user["state"] = "add_preset_elec"
        await app.storage.save_user(user)
        await message.answer(
            "Step 3/6: Введіть ціну електроенергії грн/кВт·год (наприклад: <code>4.32</code>):",
            parse_mode=ParseMode.HTML,
        )
        return True

    elif st == "add_preset_elec":
        try:
            val = float(text.replace(",", "."))
        except ValueError:
            await message.answer("⚠️ Введіть числову тарифну ставку (наприклад: 4.32).")
            return True
        c_data["new_preset"]["electricity_rate_uah"] = val
        c_data["new_preset"]["power_watts"] = 120.0
        user["state"] = "add_preset_depr"
        await app.storage.save_user(user)
        await message.answer(
            "Step 4/6: Введіть амортизацію принтера.\n<i>Якщо цифри (наприклад <code>10</code>) — це грн/год. Якщо з відсотком (наприклад <code>15%</code>) — це +15% до собівартості:</i>",
            parse_mode=ParseMode.HTML,
        )
        return True

    elif st == "add_preset_depr":
        c_data["new_preset"]["depreciation_val"] = text
        user["state"] = "add_preset_cons"
        await app.storage.save_user(user)
        await message.answer(
            "Step 5/6: Введіть витратники/обслуговування.\n<i>Якщо цифри (наприклад <code>5</code>) — це грн/год. Якщо з відсотком (наприклад <code>10%</code>) — це +10%:</i>",
            parse_mode=ParseMode.HTML,
        )
        return True

    elif st == "add_preset_cons":
        c_data["new_preset"]["consumables_val"] = text
        user["state"] = "add_preset_profit"
        await app.storage.save_user(user)
        await message.answer(
            "Step 6/6: Введіть бажаний прибуток/маржу.\n<i>Якщо цифри (наприклад <code>100</code>) — це фіксовані грн. Якщо з відсотком (наприклад <code>100%</code> або <code>150%</code>) — це націнка +%:</i>",
            parse_mode=ParseMode.HTML,
        )
        return True

    elif st == "add_preset_profit":
        c_data["new_preset"]["profit_val"] = text
        np = c_data["new_preset"]
        presets[np["id"]] = np
        await app.storage.save_json(PRESETS_PATH, presets)
        user["state"] = "idle"
        await app.storage.save_user(user)

        await message.answer(
            f"✅ <b>Пресет «{html.escape(np['name'])}» успішно збережено!</b>", parse_mode=ParseMode.HTML
        )
        await handle_commercial_menu(message, app)
        return True

    # 2. COPY PRESET WIZARD
    elif st == "select_preset_to_copy":
        target = next((p for p in presets.values() if p["name"] == text), None)
        if not target:
            await message.answer("⚠️ Пресет не знайдено, оберіть зі списку.")
            return True
        c_data["copy_source_preset"] = target.copy()
        user["state"] = "copy_preset_new_name"
        await app.storage.save_user(user)
        await message.answer(
            f"📋 Копіюємо <b>«{html.escape(target['name'])}»</b>.\nВведіть нову назву для скопійованого пресету:",
            parse_mode=ParseMode.HTML,
        )
        return True

    elif st == "copy_preset_new_name":
        src = c_data.get("copy_source_preset", {})
        new_preset = src.copy()
        new_preset["id"] = str(uuid.uuid4())
        new_preset["name"] = text
        presets[new_preset["id"]] = new_preset
        await app.storage.save_json(PRESETS_PATH, presets)
        user["state"] = "idle"
        await app.storage.save_user(user)

        await message.answer(
            f"✅ <b>Пресет скопійовано під назвою «{html.escape(text)}»!</b>\n"
            f"<i>Ви можете відредагувати ціну нитки або інші параметри кнопкою «✏️ Редагувати пресет».</i>",
            parse_mode=ParseMode.HTML,
        )
        await handle_commercial_menu(message, app)
        return True

    # 3. EDIT PRESET WIZARD
    elif st == "select_preset_to_edit":
        target = next((p for p in presets.values() if p["name"] == text), None)
        if not target:
            await message.answer("⚠️ Пресет не знайдено, оберіть зі списку.")
            return True
        c_data["edit_preset_id"] = target["id"]
        user["state"] = "edit_preset_field_choice"
        await app.storage.save_user(user)

        p_name = target.get("name", "Пресет")
        p_pr = target.get("price_per_g", 0.85)
        p_el = target.get("electricity_rate_uah", 4.32)
        p_depr = target.get("depreciation_val", "10")
        p_cons = target.get("consumables_val", "5")
        p_prof = target.get("profit_val", "100%")
        p_id = target.get("id", "")
        inline_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"🏷️ Назва ({p_name})",
                        callback_data=f"edit_p_field_name_{p_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=f"🧵 Ціна пластику ({p_pr}грн/г)",
                        callback_data=f"edit_p_field_price_{p_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=f"⚡ Світло ({p_el}грн)",
                        callback_data=f"edit_p_field_elec_{p_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=f"🔧 Амортизація ({p_depr})",
                        callback_data=f"edit_p_field_depr_{p_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=f"🧼 Витратники ({p_cons})",
                        callback_data=f"edit_p_field_cons_{p_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=f"💼 Прибуток ({p_prof})",
                        callback_data=f"edit_p_field_profit_{p_id}",
                    )
                ],
            ]
        )
        await message.answer(
            f"✏️ <b>Редагування пресету: {html.escape(p_name)}</b>\nОберіть параметр для зміни:",
            parse_mode=ParseMode.HTML,
            reply_markup=inline_kb,
        )
        return True

    # 4. DELETE PRESET
    elif st == "select_preset_to_delete":
        target = next((p for p in presets.values() if p["name"] == text), None)
        if not target:
            await message.answer("⚠️ Пресет не знайдено.")
            return True
        presets.pop(target["id"], None)
        await app.storage.save_json(PRESETS_PATH, presets)
        user["state"] = "idle"
        await app.storage.save_user(user)
        await message.answer(
            f"🗑️ Пресет <b>«{html.escape(target['name'])}»</b> успішно видалено!", parse_mode=ParseMode.HTML
        )
        await handle_commercial_menu(message, app)
        return True

    # 5. QUICK CALC WIZARD
    elif st == "calc_enter_weight":
        try:
            w = float(text.replace(",", "."))
        except ValueError:
            await message.answer("⚠️ Введіть вагу в грамах (число, наприклад: 150).")
            return True
        c_data["calc_weight_g"] = w
        user["state"] = "calc_enter_time"
        await app.storage.save_user(user)
        await message.answer(
            "⏱️ Введіть орієнтовний час друку у хвилинах (наприклад: <code>180</code> для 3 годин):",
            parse_mode=ParseMode.HTML,
        )
        return True

    elif st == "calc_enter_time":
        try:
            t_mins = int(text)
        except ValueError:
            await message.answer("⚠️ Введіть час у хвилинах (ціле число, наприклад: 180).")
            return True
        c_data["calc_time_mins"] = t_mins
        user["state"] = "calc_select_preset"
        await app.storage.save_user(user)

        kb = [[KeyboardButton(text=p["name"])] for p in presets.values()]
        kb.append([KeyboardButton(text="⬅️ Назад")])
        await message.answer(
            "📋 <b>Оберіть пресет для розрахунку:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True),
        )
        return True

    elif st == "calc_select_preset":
        target = next((p for p in presets.values() if p["name"] == text), None)
        if not target:
            await message.answer("⚠️ Пресет не знайдено, оберіть зі списку.")
            return True
        w = c_data.get("calc_weight_g", 100.0)
        t_mins = c_data.get("calc_time_mins", 60)

        res = calculate_commercial_price(target, w, t_mins)
        user["state"] = "idle"
        await app.storage.save_user(user)

        calc_txt = (
            f"<b>💰 Комерційний розрахунок для клієнта</b>\n"
            f"📋 Пресет: <b>{html.escape(res['preset_name'])}</b>\n"
            f"⚖️ Вага: <b>{res['weight_g']}g</b> | ⏱️ Час: <b>~{res['time_mins']} хв</b>\n"
            f"-----------------------------------\n"
            f"🧵 Пластик: <b>{res['filament_cost']:.2f} грн</b>\n"
            f"⚡ Електроенергія: <b>{res['electricity_cost']:.2f} грн</b>\n"
            f"🔧 Амортизація: <b>{res['depreciation_cost']:.2f} грн</b> ({res['depreciation_str']})\n"
            f"🧼 Витратники: <b>{res['consumables_cost']:.2f} грн</b> ({res['consumables_str']})\n"
            f"💼 Прибуток: <b>{res['profit_cost']:.2f} грн</b> ({res['profit_str']})\n"
            f"-----------------------------------\n"
            f"🏷️ <b>ПІДСУМКОВА ВАРТІСТЬ ДЛЯ КЛІЄНТА:</b> <code>{res['total_price']:.2f} грн</code>"
        )
        u_lang = user.get("language", "uk")
        inline_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📄 Завантажити розрахунок (PDF)" if u_lang != "en" else "📄 Download Quote (PDF)",
                        callback_data=f"comm_quote_pdf_{target['id']}_{int(w)}_{int(t_mins)}",
                    )
                ]
            ]
        )
        await message.answer(
            calc_txt,
            parse_mode=ParseMode.HTML,
            reply_markup=inline_kb,
        )
        return True

    # 6. INLINE FIELD EDIT VALUE
    elif st == "edit_preset_field_value":
        pid = c_data.get("edit_preset_id")
        field = c_data.get("edit_preset_field")
        p = presets.get(pid)
        if not p or not field:
            user["state"] = "idle"
            await app.storage.save_user(user)
            await handle_commercial_menu(message, app)
            return True

        if field == "name":
            p["name"] = text.strip()
        elif field == "price_per_g":
            try:
                v = float(text.replace(",", "."))
                p["price_per_g"] = v / 1000.0 if v >= 50 else v
            except ValueError:
                await message.answer("⚠️ Некоректне значення.")
                return True
        elif field == "electricity_rate_uah":
            try:
                p["electricity_rate_uah"] = float(text.replace(",", "."))
            except ValueError:
                await message.answer("⚠️ Некоректне значення.")
                return True
        elif field in ["depreciation_val", "consumables_val", "profit_val"]:
            p[field] = text

        presets[pid] = p
        await app.storage.save_json(PRESETS_PATH, presets)
        user["state"] = "idle"
        await app.storage.save_user(user)
        await message.answer(
            f"✅ <b>Параметр успішно оновлено для «{html.escape(p['name'])}»!</b>", parse_mode=ParseMode.HTML
        )
        await handle_commercial_menu(message, app)
        return True

    return False


@router.callback_query(F.data.startswith("edit_p_field_"))
async def handle_edit_preset_field_callback(callback: CallbackQuery, app):
    parts = callback.data.split("_")
    if len(parts) >= 5:
        field_type = parts[3]
        pid = "_".join(parts[4:])

        field_map = {
            "name": ("name", "Введіть нову назву для цього пресету:"),
            "price": ("price_per_g", "Введіть нову ціну нитки (грн/г або грн/кг, наприклад: 0.85 або 850):"),
            "elec": ("electricity_rate_uah", "Введіть новий тариф електроенергії (грн/кВт·год, наприклад: 4.32):"),
            "depr": ("depreciation_val", "Введіть нову амортизацію (наприклад: 10 або 15%):"),
            "cons": ("consumables_val", "Введіть нові витратники (наприклад: 5 або 10%):"),
            "profit": ("profit_val", "Введіть новий прибуток (наприклад: 100 грн або 100%):"),
        }

        if field_type in field_map:
            field_name, prompt_txt = field_map[field_type]
            chat_id = str(callback.message.chat.id)
            user = await app.storage.load_user(chat_id)
            user["state"] = "edit_preset_field_value"
            user["context_data"]["edit_preset_id"] = pid
            user["context_data"]["edit_preset_field"] = field_name
            await app.storage.save_user(user)

            await callback.answer()
            await callback.message.reply(prompt_txt, parse_mode=ParseMode.HTML)


@router.callback_query(F.data.startswith("comm_quote_pdf_"))
async def handle_commercial_quote_pdf_callback(callback: CallbackQuery, app):
    parts = callback.data.split("_")
    if len(parts) >= 6:
        pid = "_".join(parts[3:-2])
        try:
            w = float(parts[-2])
            t_mins = int(parts[-1])
        except ValueError:
            w = 100.0
            t_mins = 60
        presets = await get_user_presets(app)
        target = presets.get(pid)
        if not target:
            await callback.answer("⚠️ Пресет не знайдено!", show_alert=True)
            return
        user = await app.storage.load_user(str(callback.from_user.id))
        u_lang = user.get("language", "uk")
        pending_file = user.get("context_data", {}).get("pending_file", {})
        fname = pending_file.get("filename") if pending_file else None

        import time
        from services.report_generator import generate_commercial_calc_pdf

        pdf_bytes = generate_commercial_calc_pdf(res, filename=fname, lang=u_lang)
        now_f = time.strftime("%Y%m%d_%H%M%S")
        clean_fn = f"_{fname.rsplit('.', 1)[0]}" if fname else ""
        filename = f"commercial_quote{clean_fn}_{now_f}.pdf"
        doc_file = BufferedInputFile(pdf_bytes, filename=filename)
        file_label = f" ({html.escape(fname)})" if fname else ""
        cap = (
            f"💼 <b>Комерційний розрахунок для клієнта: {html.escape(target['name'])}{file_label}</b>"
            if u_lang != "en"
            else f"💼 <b>Commercial Quotation: {html.escape(target['name'])}{file_label}</b>"
        )
        await callback.message.answer_document(doc_file, caption=cap, parse_mode=ParseMode.HTML)
        await callback.answer()
