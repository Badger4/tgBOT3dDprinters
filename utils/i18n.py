"""
Internationalization (i18n) module providing Ukrainian (uk) and English (en) translations.
"""

from typing import Any

TRANSLATIONS: dict[str, dict[str, str]] = {
    # --- Main Menu Buttons ---
    "btn_open_webapp": {
        "uk": "📱 Відкрити WebApp 🚀",
        "en": "📱 Open WebApp 🚀",
    },
    "btn_printers": {
        "uk": "🖨️ Принтери",
        "en": "🖨️ Printers",
    },
    "btn_farm_status": {
        "uk": "📊 Стан ферми",
        "en": "📊 Farm Status",
    },
    "btn_warehouse": {
        "uk": "📦 Склад",
        "en": "📦 Warehouse",
    },
    "btn_commercial": {
        "uk": "💰 Комерція",
        "en": "💰 Commercial",
    },
    "btn_notify_settings": {
        "uk": "🔔 Налаштування сповіщень",
        "en": "🔔 Notification Settings",
    },
    "btn_admin": {
        "uk": "👑 Адмінка",
        "en": "👑 Admin Panel",
    },
    # --- Warehouse Buttons ---
    "btn_rfid_sync": {
        "uk": "🏷️ Зчитати RFID котушки",
        "en": "🏷️ Read RFID Spools",
    },
    "btn_add_spool": {
        "uk": "➕ Нова котушка",
        "en": "➕ New Spool",
    },
    "btn_mount_spool": {
        "uk": "🔗 Встановити на принтер",
        "en": "🔗 Mount to Printer",
    },
    "btn_unmount_spool": {
        "uk": "🔓 Зняти з принтера",
        "en": "🔓 Unmount Spool",
    },
    "btn_edit_spool": {
        "uk": "✏️ Редагувати котушку",
        "en": "✏️ Edit Spool",
    },
    "btn_edit_weight": {
        "uk": "✏️ Ручне введення ваги",
        "en": "✏️ Manual Weight Input",
    },
    "btn_delete_spool": {
        "uk": "🗑️ Видалити котушку",
        "en": "🗑️ Delete Spool",
    },
    "btn_back": {
        "uk": "⬅️ Назад",
        "en": "⬅️ Back",
    },
    # --- Printer Menu Buttons ---
    "btn_status": {
        "uk": "📊 Статус",
        "en": "📊 Status",
    },
    "btn_camera": {
        "uk": "📷 Камера",
        "en": "📷 Camera",
    },
    "btn_control": {
        "uk": "🎛️ Керування принтером",
        "en": "🎛️ Printer Control",
    },
    "btn_filament": {
        "uk": "🧵 Філамент",
        "en": "🧵 Filament",
    },
    "btn_calibrate": {
        "uk": "🎯 Калібрувати",
        "en": "🎯 Calibrate",
    },
    "btn_printer_notify": {
        "uk": "🔔 Сповіщення",
        "en": "🔔 Notifications",
    },
    "btn_reset_maint": {
        "uk": "🧹 Скинути лічильник ТО",
        "en": "🧹 Reset Maintenance",
    },
    "btn_delete_printer": {
        "uk": "🗑️ Видалити принтер",
        "en": "🗑️ Delete Printer",
    },
    "btn_add_printer": {
        "uk": "➕ Додати принтер",
        "en": "➕ Add Printer",
    },
    "btn_main_menu": {
        "uk": "Головне меню",
        "en": "Main Menu",
    },
    "btn_back_to_printers": {
        "uk": "🖨️ Назад до принтерів",
        "en": "🖨️ Back to Printers",
    },
    "btn_speed": {
        "uk": "⚡ Швидкість",
        "en": "⚡ Speed",
    },
    "btn_light": {
        "uk": "💡 Підсвітка",
        "en": "💡 Light",
    },
    "btn_stop_print": {
        "uk": "⏹️ Зупинити друк",
        "en": "⏹️ Stop Print",
    },
    "btn_pause_print": {
        "uk": "⏸️ Пауза",
        "en": "⏸️ Pause",
    },
    "btn_resume_print": {
        "uk": "▶️ Відновити друк",
        "en": "▶️ Resume Print",
    },
    "btn_users": {
        "uk": "👥 Користувачі",
        "en": "👥 Users",
    },
    "btn_new_users": {
        "uk": "🆕 Нові користувачі",
        "en": "🆕 New Users",
    },
    "btn_quick_calc": {
        "uk": "🧮 Швидкий розрахунок ціни",
        "en": "🧮 Quick Price Calculation",
    },
    "btn_create_preset": {
        "uk": "➕ Створити пресет",
        "en": "➕ Create Preset",
    },
    "btn_copy_preset": {
        "uk": "📋 Копіювати пресет",
        "en": "📋 Copy Preset",
    },
    "btn_edit_preset": {
        "uk": "✏️ Редагувати пресет",
        "en": "✏️ Edit Preset",
    },
    "btn_delete_preset": {
        "uk": "🗑️ Видалити пресет",
        "en": "🗑️ Delete Preset",
    },
    "btn_language": {
        "uk": "🌐 Мова / Language",
        "en": "🌐 Language / Мова",
    },
    # --- General Titles ---
    "warehouse_title": {
        "uk": "📦 <b>Склад Матеріалів & AMS 3D Ферми</b>",
        "en": "📦 <b>Materials Stock & AMS Farm</b>",
    },
    "lang_switched": {
        "uk": "🇺🇦 Мову інтерфейсу змінено на <b>Українську</b>!",
        "en": "🇬🇧 Interface language switched to <b>English</b>!",
    },
}


def t(key: str, lang: str = "uk", **kwargs: Any) -> str:
    """Translates a key into the given language ('uk' or 'en')."""
    entry = TRANSLATIONS.get(key, {})
    text = entry.get(lang) or entry.get("uk") or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            pass
    return text


def get_user_lang(user_data: dict[str, Any] | None) -> str:
    """Extracts language preference ('uk' or 'en') from user dictionary."""
    if not user_data or not isinstance(user_data, dict):
        return "uk"
    lang = user_data.get("language", "uk")
    return "en" if str(lang).lower() in ["en", "english"] else "uk"
