"""
Commercial Pricing Calculator and Preset Management Handlers.
"""

import html
import uuid

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import (
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


def get_commercial_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧮 Швидкий розрахунок ціни")],
            [KeyboardButton(text="➕ Створити пресет"), KeyboardButton(text="📋 Копіювати пресет")],
            [KeyboardButton(text="✏️ Редагувати пресет"), KeyboardButton(text="🗑️ Видалити пресет")],
            [KeyboardButton(text="⬅️ Головне меню")],
        ],
        resize_keyboard=True,
    )


@router.message(F.text.lower().in_(["💰 комерція", "комерція", "калькулятор ціни", "пресети"]))
async def handle_commercial_menu(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    user["state"] = "idle"
    await app.storage.save_user(user)

    presets = await get_user_presets(app)

    txt = (
        "<b>💰 Комерційний калькулятор ціни</b>\n"
        "<i>Налаштування себевартості та маржі для комерційного друку</i> 💼✨\n\n"
        "<b>📋 Наявні пресети:</b>\n"
    )
    for p in presets.values():
        txt += (
            f"• <b>{html.escape(p['name'])}</b>\n"
            f"  <i>Пластик: {p['price_per_g']}грн/г | Світло: {p['electricity_rate_uah']}грн | Аморт: {p['depreciation_val']} | Витрат: {p['consumables_val']} | Маржа: {p['profit_val']}</i>\n"
        )

    await message.answer(txt, parse_mode=ParseMode.HTML, reply_markup=get_commercial_menu_keyboard())


@router.message(F.text.lower().in_(["➕ створити пресет", "створити пресет"]))
async def start_add_preset(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    user["state"] = "add_preset_name"
    user["context_data"]["new_preset"] = {}
    await app.storage.save_user(user)

    await message.answer(
        "➕ <b>Створення нового пресету</b>\nStep 1/6: Введіть назву пресету (наприклад: <i>PLA Sunlu Black</i>):",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True),
    )


@router.message(F.text.lower().in_(["📋 копіювати пресет", "копіювати пресет"]))
async def start_copy_preset(message: Message, app):
    chat_id = str(message.chat.id)
    presets = await get_user_presets(app)
    if not presets:
        await message.answer("⚠️ Немає наявних пресетів для копіювання.")
        return

    user = await app.storage.load_user(chat_id)
    user["state"] = "select_preset_to_copy"
    await app.storage.save_user(user)

    kb = [[KeyboardButton(text=p["name"])] for p in presets.values()]
    kb.append([KeyboardButton(text="⬅️ Назад")])
    await message.answer(
        "📋 <b>Оберіть пресет, який хочете скопіювати:</b>\n"
        "<i>Ви зможете дати нову назву і змінити тільки потрібні параметри (наприклад, ціну нитки)!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True),
    )


@router.message(F.text.lower().in_(["✏️ редагувати пресет", "редагувати пресет"]))
async def start_edit_preset(message: Message, app):
    chat_id = str(message.chat.id)
    presets = await get_user_presets(app)
    if not presets:
        await message.answer("⚠️ Немає наявних пресетів для редагування.")
        return

    user = await app.storage.load_user(chat_id)
    user["state"] = "select_preset_to_edit"
    await app.storage.save_user(user)

    kb = [[KeyboardButton(text=p["name"])] for p in presets.values()]
    kb.append([KeyboardButton(text="⬅️ Назад")])
    await message.answer(
        "✏️ <b>Оберіть пресет для редагування:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True),
    )


@router.message(F.text.lower().in_(["🗑️ видалити пресет", "видалити пресет"]))
async def start_delete_preset(message: Message, app):
    chat_id = str(message.chat.id)
    presets = await get_user_presets(app)
    if not presets:
        await message.answer("⚠️ Немає наявних пресетів для видалення.")
        return

    user = await app.storage.load_user(chat_id)
    user["state"] = "select_preset_to_delete"
    await app.storage.save_user(user)

    kb = [[KeyboardButton(text=p["name"])] for p in presets.values()]
    kb.append([KeyboardButton(text="⬅️ Назад")])
    await message.answer(
        "🗑️ <b>Оберіть пресет для видалення:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True),
    )


@router.message(F.text.lower().in_(["🧮 швидкий розрахунок ціни", "розрахунок ціни", "розрахувати"]))
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

        inline_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"🧵 Ціна пластику ({target['price_per_g']}грн/г)",
                        callback_data=f"edit_p_field_price_{target['id']}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=f"⚡ Світло ({target['electricity_rate_uah']}грн)",
                        callback_data=f"edit_p_field_elec_{target['id']}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=f"🔧 Амортизація ({target['depreciation_val']})",
                        callback_data=f"edit_p_field_depr_{target['id']}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=f"🧼 Витратники ({target['consumables_val']})",
                        callback_data=f"edit_p_field_cons_{target['id']}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=f"💼 Прибуток ({target['profit_val']})",
                        callback_data=f"edit_p_field_profit_{target['id']}",
                    )
                ],
            ]
        )
        await message.answer(
            f"✏️ <b>Редагування пресету: {html.escape(target['name'])}</b>\nОберіть параметр для зміни:",
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
        await message.answer(calc_txt, parse_mode=ParseMode.HTML, reply_markup=get_commercial_menu_keyboard())
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

        if field == "price_per_g":
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
        pid = parts[4]

        field_map = {
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
