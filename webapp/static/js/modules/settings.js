/**
 * 3D Farm Manager - Settings, User Access & Internationalization (i18n)
 */

import { escapeHtml, triggerHaptic } from "./utils.js";
import { state } from "./state.js";
import {
    fetchUserSettingsApi,
    saveUserSettingsApi,
    fetchPrinterSettingsApi,
    savePrinterSettingsApi,
    fetchUsersApi,
    saveUserAccessApi,
    deleteUserApi,
    deletePrinterApi,
    fetchPrintersApi
} from "./api.js";

export const i18nDict = {
    uk: {
        nav_printers: "Ферма",
        nav_materials: "Філамент",
        nav_parts: "Деталі",
        nav_commercial: "Комерція",
        nav_history: "Історія",
        nav_settings: "Опції",
        farm_status_title: "Стан ферми",
        add_printer_btn: "Додати принтер",
        active_label: "активні",
        filter_all: "Всі",
        filter_running: "Друкує 🟢",
        filter_pause: "Пауза ⏸️",
        filter_idle: "Вільні ⚪",
        filter_offline: "Офлайн 🔴",
        fleet_lights_on: "💡 Світло Увімк",
        fleet_lights_off: "🌑 Світло Вимк",
        fleet_calibrate_all: "🎯 Калібрувати",
        loading_printers: "Завантаження принтерів...",
        commercial_title: "Комерція & Калькулятор",
        new_preset_btn: "Новий пресет",
        calc_cost_title: "Розрахунок вартості друку",
        pricing_preset_label: "Пресет ціноутворення",
        loading_presets: "Завантаження пресетів...",
        filament_weight_g_label: "Вага нитки (г)",
        print_time_mins_label: "Час друку (хв)",
        total_commercial_price_label: "Підсумкова комерційна ціна:",
        item_filament: "Пластик",
        item_electricity: "Електроенергія",
        item_depreciation: "Амортизація",
        item_consumables: "Витратні матеріали",
        item_prime_cost: "Собівартість",
        item_margin: "Прибуток (Маржа)",
        existing_presets_title: "Наявні пресети ціноутворення",
        materials_stock_title: "Склад пластику",
        new_spool_btn: "Нова котушка",
        spools_warehouse_title: "Склад котушок",
        history_title: "Аналітика & Історія",
        refresh_btn: "Оновити",
        clear_btn: "Очистити",
        export_pdf_btn: "Звіт (PDF)",
        total_jobs_label: "Всього друків",
        total_filament_label: "Витрачено нитки",
        completed_jobs_log: "Журнал виконаних робіт",
        th_date: "Дата",
        th_printer: "Принтер",
        th_model: "Модель",
        th_weight_g: "Вага (г)",
        no_history_records: "Немає записів історії",
        settings_title: "Налаштування та сповіщення",
        notification_settings_card: "Повноцінні налаштування сповіщень",
        notify_start_label: "Сповіщення про початок друку",
        notify_finish_label: "Сповіщення про завершення друку",
        notify_pause_label: "Сповіщення про паузу друку",
        notify_hms_label: "HMS Помилки та тривоги",
        notify_remind_clear_label: "Нагадування зняти деталь з підкладки",
        notify_before_end_label: "Сповіщення за N хв до кінця",
        opt_timer_off: "❌ Вимкнути таймер",
        opt_timer_5: "⏳ 5 хвилин до кінця",
        opt_timer_10: "⏳ 10 хвилин до кінця",
        opt_timer_15: "⏳ 15 хвилин до кінця",
        notify_filament_threshold: "Поріг залишку нитки",
        opt_limit_off: "❌ Вимкнути ліміт",
        opt_limit_50: "📦 Менше 50г",
        opt_limit_100: "📦 Менше 100г",
        opt_limit_200: "📦 Менше 200г",
        lang_select_label: "Мова / Language",
        save_settings_btn: "Зберегти налаштування",
        save_success: "✅ Налаштування успішно збережено!",
        user_access_control_title: "Управління доступом користувачів (Адмінка)",
        th_user: "Користувач",
        th_role: "Роль",
        th_access_status: "Статус доступу",
        th_actions: "Дії"
    },
    en: {
        nav_printers: "Farm",
        nav_materials: "Filament",
        nav_parts: "Parts",
        nav_commercial: "Commerce",
        nav_history: "History",
        nav_settings: "Options",
        farm_status_title: "Farm Status",
        add_printer_btn: "Add Printer",
        active_label: "active",
        filter_all: "All",
        filter_running: "Printing 🟢",
        filter_pause: "Pause ⏸️",
        filter_idle: "Idle ⚪",
        filter_offline: "Offline 🔴",
        fleet_lights_on: "💡 Lights On",
        fleet_lights_off: "🌑 Lights Off",
        fleet_calibrate_all: "🎯 Calibrate",
        loading_printers: "Loading printers...",
        commercial_title: "Commercial & Calculator",
        new_preset_btn: "New Preset",
        calc_cost_title: "Print Cost Estimation",
        pricing_preset_label: "Pricing Preset",
        loading_presets: "Loading presets...",
        filament_weight_g_label: "Filament Weight (g)",
        print_time_mins_label: "Print Time (min)",
        total_commercial_price_label: "Total Commercial Price:",
        item_filament: "Filament",
        item_electricity: "Electricity",
        item_depreciation: "Depreciation",
        item_consumables: "Consumables",
        item_prime_cost: "Prime Cost",
        item_margin: "Profit (Margin)",
        existing_presets_title: "Existing Pricing Presets",
        materials_stock_title: "Filament Stock",
        new_spool_btn: "New Spool",
        spools_warehouse_title: "Spool Warehouse",
        history_title: "Analytics & History",
        refresh_btn: "Refresh",
        clear_btn: "Clear",
        export_pdf_btn: "Report (PDF)",
        total_jobs_label: "Total Prints",
        total_filament_label: "Used Filament",
        completed_jobs_log: "Completed Jobs Log",
        th_date: "Date",
        th_printer: "Printer",
        th_model: "Model",
        th_weight_g: "Weight (g)",
        no_history_records: "No history records found",
        settings_title: "Settings & Notifications",
        notification_settings_card: "Comprehensive Notification Settings",
        notify_start_label: "Print Started notification",
        notify_finish_label: "Print Finished notification",
        notify_pause_label: "Print Paused notification",
        notify_hms_label: "HMS Errors and alerts",
        notify_remind_clear_label: "Reminder to remove printed part",
        notify_before_end_label: "Notify N mins before completion",
        opt_timer_off: "❌ Disable timer",
        opt_timer_5: "⏳ 5 mins remaining",
        opt_timer_10: "⏳ 10 mins remaining",
        opt_timer_15: "⏳ 15 mins remaining",
        notify_filament_threshold: "Remaining Filament Threshold",
        opt_limit_off: "❌ Disable limit",
        opt_limit_50: "📦 Under 50g",
        opt_limit_100: "📦 Under 100g",
        opt_limit_200: "📦 Under 200g",
        lang_select_label: "Language / Мова",
        save_settings_btn: "Save Settings",
        save_success: "✅ Settings successfully saved!",
        user_access_control_title: "User Access Control (Admin)",
        th_user: "User",
        th_role: "Role",
        th_access_status: "Access Status",
        th_actions: "Actions"
    }
};

export function setAppLanguage(lang) {
    if (!lang || !["uk", "en"].includes(lang.toLowerCase())) lang = "uk";
    lang = lang.toLowerCase();
    state.currentLanguage = lang;
    localStorage.setItem("app_lang", lang);

    const langSelect = document.getElementById("setting-app-language");
    if (langSelect) langSelect.value = lang;

    const currentDict = i18nDict[lang] || i18nDict.uk;
    document.querySelectorAll("[data-i18n]").forEach(el => {
        const key = el.getAttribute("data-i18n");
        if (currentDict[key]) {
            el.textContent = currentDict[key];
        }
    });
}

export async function loadSettings() {
    try {
        const settings = await fetchUserSettingsApi();
        if (!settings) return;

        const notif = settings.notifications || {};
        if (document.getElementById("setting-notify-start")) document.getElementById("setting-notify-start").checked = notif.start ?? true;
        if (document.getElementById("setting-notify-finish")) document.getElementById("setting-notify-finish").checked = notif.finish ?? true;
        if (document.getElementById("setting-notify-pause")) document.getElementById("setting-notify-pause").checked = notif.pause ?? true;
        if (document.getElementById("setting-notify-hms")) document.getElementById("setting-notify-hms").checked = notif.hms ?? true;
        if (document.getElementById("setting-notify-remind-clear")) document.getElementById("setting-notify-remind-clear").checked = notif.remind_clear ?? true;
        if (document.getElementById("setting-notify-min-time")) document.getElementById("setting-notify-min-time").value = notif.min_time_to_end ?? 0;
        if (document.getElementById("setting-notify-min-filament")) document.getElementById("setting-notify-min-filament").value = notif.min_filament ?? 0;

        const savedLang = settings.language || localStorage.getItem("app_lang") || "uk";
        setAppLanguage(savedLang);

        await loadUsersTable();
    } catch (e) {
        console.error("Failed loading settings:", e);
    }
}

export async function saveSettings() {
    const notifyObj = {
        start: document.getElementById("setting-notify-start")?.checked ?? true,
        finish: document.getElementById("setting-notify-finish")?.checked ?? true,
        pause: document.getElementById("setting-notify-pause")?.checked ?? true,
        hms: document.getElementById("setting-notify-hms")?.checked ?? true,
        remind_clear: document.getElementById("setting-notify-remind-clear")?.checked ?? true,
        min_time_to_end: parseInt(document.getElementById("setting-notify-min-time")?.value || 0),
        min_filament: parseInt(document.getElementById("setting-notify-min-filament")?.value || 0)
    };
    const lang = document.getElementById("setting-app-language")?.value || "uk";

    try {
        await saveUserSettingsApi({ notifications: notifyObj, language: lang });
        triggerHaptic("success");
        setAppLanguage(lang);
        alert(i18nDict[lang]?.save_success || "✅ Налаштування успішно збережено!");
    } catch (e) {
        triggerHaptic("error");
        console.error("Save settings error:", e);
        alert("⚠️ Помилка збереження налаштувань.");
    }
}

export async function loadUsersTable() {
    const tbody = document.getElementById("users-table-body");
    if (!tbody) return;

    try {
        const users = await fetchUsersApi();
        if (!users || users.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted p-3">Користувачів не знайдено</td></tr>`;
            return;
        }

        tbody.innerHTML = users.map(u => {
            const isApproved = u.status === "approved" || u.is_approved;
            const statusBadge = isApproved
                ? `<span class="badge badge-success">Дозволено</span>`
                : `<span class="badge badge-warning">Очікує</span>`;

            return `
                <tr>
                    <td><strong>${escapeHtml(u.username || u.name || String(u.user_id))}</strong></td>
                    <td>${escapeHtml(u.role || "user")}</td>
                    <td>${statusBadge}</td>
                    <td>
                        <div class="d-flex gap-1">
                            ${!isApproved ? `
                            <button class="btn btn-xs btn-success btn-approve-user" data-id="${u.user_id}">
                                <i class="fa-solid fa-check"></i>
                            </button>` : `
                            <button class="btn btn-xs btn-outline-warning btn-revoke-user" data-id="${u.user_id}">
                                <i class="fa-solid fa-ban"></i>
                            </button>`}
                            <button class="btn btn-xs btn-outline-danger btn-delete-user" data-id="${u.user_id}">
                                <i class="fa-solid fa-trash"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join("");

        tbody.querySelectorAll(".btn-approve-user").forEach(b => {
            b.addEventListener("click", async () => {
                const id = b.getAttribute("data-id");
                await saveUserAccessApi({ user_id: id, status: "approved" });
                loadUsersTable();
            });
        });
        tbody.querySelectorAll(".btn-revoke-user").forEach(b => {
            b.addEventListener("click", async () => {
                const id = b.getAttribute("data-id");
                await saveUserAccessApi({ user_id: id, status: "pending" });
                loadUsersTable();
            });
        });
        tbody.querySelectorAll(".btn-delete-user").forEach(b => {
            b.addEventListener("click", async () => {
                const id = b.getAttribute("data-id");
                if (confirm("Видалити цього користувача?")) {
                    await deleteUserApi(id);
                    loadUsersTable();
                }
            });
        });
    } catch (e) {
        console.error("Failed loading users table:", e);
    }
}

export async function loadPrinterSettings(printerId) {
    if (!printerId) return;
    try {
        const s = await fetchPrinterSettingsApi(printerId);
        if (!s) return;

        const sel = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.value = val !== undefined && val !== null ? val : "";
        };
        const chk = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.checked = Boolean(val);
        };

        sel("p-setting-name", s.name);
        sel("p-setting-ip", s.ip);
        sel("p-setting-access-code", s.accessCode);
        sel("p-setting-sn", s.serialNumber);
        sel("p-setting-model", s.printer_model || "A1");
        sel("p-setting-nozzle-diameter", s.nozzle_diameter || "0.4");
        sel("p-setting-ams", s.ams_enabled === true ? "true" : (s.ams_enabled === false ? "false" : "auto"));
        sel("p-setting-maint-interval", s.maintenance_interval_hours || 100);

        const n = s.notify || {};
        chk("p-setting-notify-start", n.start ?? true);
        chk("p-setting-notify-finish", n.finish ?? true);
        chk("p-setting-notify-pause", n.pause ?? true);
        chk("p-setting-notify-hms", n.hms ?? true);
        chk("p-setting-notify-remind-clear", n.remind_clear ?? true);
        sel("p-setting-notify-min-time", n.min_time_to_end ?? 0);
        sel("p-setting-notify-min-filament", n.min_filament ?? 0);
    } catch (e) {
        console.error("Failed loading printer settings:", e);
    }
}

export async function openPrinterSettingsModal(printerId) {
    if (!printerId) return;
    state.selectedPrinterId = printerId;

    const modal = document.getElementById("printer-settings-modal");
    if (!modal) return;

    try {
        const s = await fetchPrinterSettingsApi(printerId);
        if (!s) return;

        const sel = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.value = val !== undefined && val !== null ? val : "";
        };
        const chk = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.checked = Boolean(val);
        };

        sel("ps-modal-printer-id", printerId);
        sel("ps-modal-name", s.name);
        sel("ps-modal-ip", s.ip);
        sel("ps-modal-access-code", s.accessCode);
        sel("ps-modal-sn", s.serialNumber);
        sel("ps-modal-model", s.printer_model || "A1");
        sel("ps-modal-nozzle-diameter", s.nozzle_diameter || "0.4");
        sel("ps-modal-ams", s.ams_enabled === true ? "true" : (s.ams_enabled === false ? "false" : "auto"));
        sel("ps-modal-maint-interval", s.maintenance_interval_hours || 100);

        const n = s.notify || {};
        chk("ps-modal-notify-start", n.start ?? true);
        chk("ps-modal-notify-finish", n.finish ?? true);
        chk("ps-modal-notify-pause", n.pause ?? true);
        chk("ps-modal-notify-hms", n.hms ?? true);
        chk("ps-modal-notify-remind-clear", n.remind_clear ?? true);
        sel("ps-modal-notify-min-time", n.min_time_to_end ?? 0);
        sel("ps-modal-notify-min-filament", n.min_filament ?? 0);

        triggerHaptic("light");
        modal.classList.add("active");
    } catch (e) {
        console.error("Failed opening printer settings modal:", e);
    }
}

export async function savePrinterSettingsModal() {
    const pId = document.getElementById("ps-modal-printer-id")?.value;
    if (!pId) return;

    const notifyObj = {
        start: document.getElementById("ps-modal-notify-start")?.checked ?? true,
        finish: document.getElementById("ps-modal-notify-finish")?.checked ?? true,
        pause: document.getElementById("ps-modal-notify-pause")?.checked ?? true,
        hms: document.getElementById("ps-modal-notify-hms")?.checked ?? true,
        remind_clear: document.getElementById("ps-modal-notify-remind-clear")?.checked ?? true,
        min_time_to_end: parseInt(document.getElementById("ps-modal-notify-min-time")?.value || 0),
        min_filament: parseInt(document.getElementById("ps-modal-notify-min-filament")?.value || 0),
    };

    const payload = {
        name: document.getElementById("ps-modal-name")?.value || "",
        ip: document.getElementById("ps-modal-ip")?.value || "",
        accessCode: document.getElementById("ps-modal-access-code")?.value || "",
        serialNumber: document.getElementById("ps-modal-sn")?.value || "",
        printer_model: document.getElementById("ps-modal-model")?.value || "A1",
        nozzle_diameter: document.getElementById("ps-modal-nozzle-diameter")?.value || "0.4",
        ams_enabled: document.getElementById("ps-modal-ams")?.value === "true" ? true : (document.getElementById("ps-modal-ams")?.value === "false" ? false : "auto"),
        maintenance_interval_hours: parseInt(document.getElementById("ps-modal-maint-interval")?.value || 100),
        notify: notifyObj,
    };

    try {
        await savePrinterSettingsApi(pId, payload);
        alert("✅ Налаштування принтера успішно збережено!");
        document.getElementById("printer-settings-modal")?.classList.remove("active");
        const printers = await fetchPrintersApi();
        state.printers = printers;
    } catch (e) {
        console.error("Failed saving printer settings via modal:", e);
        alert("⚠️ Помилка зв'язку із сервером: " + e);
    }
}

export function initSettingsEventListeners() {
    document.getElementById("save-settings-btn")?.addEventListener("click", saveSettings);
    document.getElementById("setting-app-language")?.addEventListener("change", (e) => {
        setAppLanguage(e.target.value);
    });
    document.getElementById("close-printer-settings-modal")?.addEventListener("click", () => {
        document.getElementById("printer-settings-modal")?.classList.remove("active");
    });
    document.getElementById("save-printer-settings-modal-btn")?.addEventListener("click", savePrinterSettingsModal);

    // Delete printer button inside settings modal
    document.getElementById("btn-action-delete")?.addEventListener("click", async () => {
        const pId = document.getElementById("ps-modal-printer-id")?.value || state.selectedPrinterId;
        if (!pId) return;
        const p = state.printers.find(x => x.id === pId);
        const name = p ? p.name : pId;
        if (confirm(`Ви дійсно бажаєте ВИДАЛИТИ принтер "${name}" з системи?`)) {
            try {
                await deletePrinterApi(pId);
                document.getElementById("printer-settings-modal")?.classList.remove("active");
                document.getElementById("printer-modal")?.classList.remove("active");
                const printers = await fetchPrintersApi();
                state.printers = printers;
            } catch (e) {
                console.error("Delete printer error:", e);
            }
        }
    });
}

export const initSettingsModule = initSettingsEventListeners;
export const applyLanguageDictionary = setAppLanguage;
