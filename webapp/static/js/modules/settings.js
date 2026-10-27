/**
 * 3D Farm Manager - Settings, User Access, Fleet Health & Internationalization (i18n)
 */

import { escapeHtml, triggerHaptic } from "./utils.js";
import { showToast } from "./modals.js";
import { state } from "./state.js";
import {
    fetchUserSettingsApi,
    saveUserSettingsApi,
    fetchPrinterSettingsApi,
    savePrinterSettingsApi,
    fetchUsersApi,
    saveUserAccessApi,
    deleteUserApi,
    fetchPrintersApi,
    fetchHealthApi,
    saveGlobalSettingsApi
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
        lang_select_label: "Мова інтерфейсу / Language",
        save_settings_btn: "Зберегти налаштування",
        save_success: "✅ Налаштування успішно збережено!",
        user_access_control_title: "Управління доступом користувачів (Адмінка)",
        th_user: "Користувач",
        th_role: "Роль",
        th_access_status: "Статус доступу",
        th_actions: "Дії",
        server_farm_status_title: "Стан сервера та ферми",
        sys_uptime_label: "Час безвідмовної роботи:",
        connected_printers_label: "Підключені принтери:",
        rest_api_status_label: "REST API Статус:",
        status_active: "Активний",
        loading_users: "Завантаження користувачів..."
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
        lang_select_label: "Language / Мова інтерфейсу",
        save_settings_btn: "Save Settings",
        save_success: "✅ Settings successfully saved!",
        user_access_control_title: "User Access Control (Admin)",
        th_user: "User",
        th_role: "Role",
        th_access_status: "Access Status",
        th_actions: "Actions",
        server_farm_status_title: "Server & Farm Status",
        sys_uptime_label: "Uptime:",
        connected_printers_label: "Connected Printers:",
        rest_api_status_label: "REST API Status:",
        status_active: "Active",
        loading_users: "Loading users..."
    }
};

/**
 * Formats uptime seconds into human-readable duration
 */
export function formatUptime(seconds, lang = "uk") {
    const sec = Math.max(0, parseInt(seconds, 10) || 0);
    const isEn = lang === "en";
    const d = Math.floor(sec / 86400);
    const h = Math.floor((sec % 86400) / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;

    if (d > 0) {
        return isEn ? `${d}d ${h}h ${m}m` : `${d} д ${h} год ${m} хв`;
    }
    if (h > 0) {
        return isEn ? `${h}h ${m}m ${s}s` : `${h} год ${m} хв ${s} сек`;
    }
    if (m > 0) {
        return isEn ? `${m}m ${s}s` : `${m} хв ${s} сек`;
    }
    return isEn ? `${s}s` : `${s} сек`;
}

/**
 * Switch active application language and translate UI elements
 */
export function setAppLanguage(lang) {
    if (!lang || !["uk", "en"].includes(lang.toLowerCase())) lang = "uk";
    lang = lang.toLowerCase();
    state.currentLanguage = lang;
    localStorage.setItem("app_lang", lang);

    const langSelect = document.getElementById("setting-app-language");
    if (langSelect && langSelect.value !== lang) {
        langSelect.value = lang;
    }

    const currentDict = i18nDict[lang] || i18nDict.uk;
    document.querySelectorAll("[data-i18n]").forEach(el => {
        const key = el.getAttribute("data-i18n");
        if (currentDict[key]) {
            el.textContent = currentDict[key];
        }
    });
}

/**
 * Load global user settings, notification rules, language and system status
 */
export async function loadSettings() {
    try {
        const [settingsRes, _] = await Promise.allSettled([
            fetchUserSettingsApi(),
            updateServerHealthAndStats()
        ]);

        const settings = settingsRes.status === "fulfilled" ? settingsRes.value : null;

        if (settings) {
            const notif = settings.notify || settings.notifications || {};
            const setChk = (id1, id2, val) => {
                const el1 = document.getElementById(id1);
                if (el1) el1.checked = Boolean(val);
                const el2 = document.getElementById(id2);
                if (el2) el2.checked = Boolean(val);
            };
            const setVal = (id1, id2, val) => {
                const el1 = document.getElementById(id1);
                if (el1) el1.value = val !== undefined && val !== null ? val : 0;
                const el2 = document.getElementById(id2);
                if (el2) el2.value = val !== undefined && val !== null ? val : 0;
            };

            setChk("global-notify-start", "setting-notify-start", notif.start ?? true);
            setChk("global-notify-finish", "setting-notify-finish", notif.finish ?? true);
            setChk("global-notify-pause", "setting-notify-pause", notif.pause ?? true);
            setChk("global-notify-hms", "setting-notify-hms", notif.hms ?? true);
            setChk("global-notify-remind-clear", "setting-notify-remind-clear", notif.remind_clear ?? true);
            setVal("global-notify-min-time", "setting-notify-min-time", notif.min_time_to_end ?? 0);
            setVal("global-notify-min-filament", "setting-notify-min-filament", notif.min_filament ?? 0);

            const savedLang = settings.language || localStorage.getItem("app_lang") || "uk";
            setAppLanguage(savedLang);

            // Admin User Access Control Card
            const isAdmin = Boolean(settings.user?.is_admin || settings.user?.role === "ADMIN");
            const adminCard = document.getElementById("admin-users-card");
            if (adminCard) {
                if (isAdmin) {
                    adminCard.style.display = "block";
                    await loadUsersTable();
                } else {
                    adminCard.style.display = "none";
                }
            }
        }

        // Populate per-printer select in Tab 5
        await populatePrinterSettingsSelect();
    } catch (e) {
        console.error("Failed loading settings:", e);
    }
}

/**
 * Save global settings and apply them to user profile and all printers
 */
export async function saveSettings() {
    const applyBtn = document.getElementById("apply-global-settings-btn") || document.getElementById("save-settings-btn");
    if (applyBtn?.getAttribute("data-busy") === "true") return;

    const originalHtml = applyBtn ? applyBtn.innerHTML : "";
    if (applyBtn) {
        applyBtn.setAttribute("data-busy", "true");
        applyBtn.disabled = true;
        applyBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Збереження...`;
    }

    const getChk = (id1, id2) => {
        const el = document.getElementById(id1) || document.getElementById(id2);
        return el ? el.checked : true;
    };
    const getVal = (id1, id2, def) => {
        const el = document.getElementById(id1) || document.getElementById(id2);
        return el ? parseInt(el.value, 10) : def;
    };

    const notifyObj = {
        start: getChk("global-notify-start", "setting-notify-start"),
        finish: getChk("global-notify-finish", "setting-notify-finish"),
        pause: getChk("global-notify-pause", "setting-notify-pause"),
        hms: getChk("global-notify-hms", "setting-notify-hms"),
        remind_clear: getChk("global-notify-remind-clear", "setting-notify-remind-clear"),
        min_time_to_end: getVal("global-notify-min-time", "setting-notify-min-time", 0),
        min_filament: getVal("global-notify-min-filament", "setting-notify-min-filament", 0)
    };

    const langEl = document.getElementById("setting-app-language");
    const lang = langEl ? langEl.value : (state.currentLanguage || "uk");

    try {
        // 1. Save user specific settings
        const userRes = await saveUserSettingsApi({ notify: notifyObj, notifications: notifyObj, language: lang });
        if (userRes && userRes.error) throw new Error(userRes.error);

        // 2. Propagate notification settings to all known printers in the fleet
        if (Array.isArray(state.printers) && state.printers.length > 0) {
            await Promise.allSettled(
                state.printers.map(p => savePrinterSettingsApi(p.id, { notify: notifyObj }))
            );
        }

        // 3. Save global backend configuration
        try {
            await saveGlobalSettingsApi({ notify: notifyObj, language: lang });
        } catch (_) {}

        triggerHaptic("success");
        setAppLanguage(lang);
        showToast(i18nDict[lang]?.save_success || "✅ Налаштування успішно збережено!", "success");
    } catch (e) {
        triggerHaptic("error");
        console.error("Save settings error:", e);
        showToast("⚠️ Помилка збереження налаштувань: " + (e.message || e), "error");
    } finally {
        if (applyBtn) {
            applyBtn.removeAttribute("data-busy");
            applyBtn.disabled = false;
            applyBtn.innerHTML = originalHtml;
        }
    }
}

/**
 * Builds HTML table row for a registered Telegram user with 5 aligned columns
 */
export function buildUserRowHtml(u) {
    const uId = u.user_id || u.id || "";
    const isApproved = u.approved === true || u.is_approved === true || u.status === "approved";
    const statusBadge = isApproved
        ? `<span class="badge badge-success">Дозволено</span>`
        : `<span class="badge badge-warning">Очікує</span>`;

    const displayName = u.name || (u.first_name ? `${u.first_name} ${u.last_name || ""}`.trim() : "") || (u.username ? "@" + u.username : "") || String(uId);
    const role = (u.role || "USER").toUpperCase();
    const roleBadge = `<span class="badge ${role === "ADMIN" ? "badge-primary" : "badge-secondary"}">${escapeHtml(role)}</span>`;

    return `
        <tr>
            <td><strong>${escapeHtml(displayName)}</strong></td>
            <td><code>${escapeHtml(String(uId))}</code></td>
            <td>${roleBadge}</td>
            <td>${statusBadge}</td>
            <td>
                <div class="d-flex gap-1">
                    ${!isApproved ? `
                    <button type="button" class="btn btn-xs btn-success btn-approve-user" data-id="${escapeHtml(String(uId))}" title="Дозволити доступ">
                        <i class="fa-solid fa-check"></i>
                    </button>` : `
                    <button type="button" class="btn btn-xs btn-outline-warning btn-revoke-user" data-id="${escapeHtml(String(uId))}" title="Заблокувати доступ">
                        <i class="fa-solid fa-ban"></i>
                    </button>`}
                    <button type="button" class="btn btn-xs btn-outline-danger btn-delete-user" data-id="${escapeHtml(String(uId))}" title="Видалити користувача">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            </td>
        </tr>
    `;
}

/**
 * Load and render Admin Users Table
 */
export async function loadUsersTable() {
    const tbody = document.getElementById("users-table-body");
    if (!tbody) return;

    try {
        const rawUsers = await fetchUsersApi();
        const users = Array.isArray(rawUsers) ? rawUsers : (rawUsers?.users || []);

        if (!users || users.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted p-3">Користувачів не знайдено</td></tr>`;
            return;
        }

        tbody.innerHTML = users.map(u => buildUserRowHtml(u)).join("");

        tbody.querySelectorAll(".btn-approve-user").forEach(b => {
            b.addEventListener("click", async () => {
                const id = b.getAttribute("data-id");
                b.disabled = true;
                try {
                    const res = await saveUserAccessApi({ user_id: id, approved: true, status: "approved" });
                    if (res && res.error) {
                        showToast("⚠️ Помилка зміни доступу: " + res.error, "error");
                        b.disabled = false;
                        return;
                    }
                    triggerHaptic("success");
                    showToast("✅ Доступ надано", "success");
                    await loadUsersTable();
                } catch (err) {
                    b.disabled = false;
                    showToast("⚠️ Помилка зміни доступу: " + (err.message || err), "error");
                }
            });
        });

        tbody.querySelectorAll(".btn-revoke-user").forEach(b => {
            b.addEventListener("click", async () => {
                const id = b.getAttribute("data-id");
                b.disabled = true;
                try {
                    const res = await saveUserAccessApi({ user_id: id, approved: false, status: "pending" });
                    if (res && res.error) {
                        showToast("⚠️ Помилка зміни доступу: " + res.error, "error");
                        b.disabled = false;
                        return;
                    }
                    triggerHaptic("warning");
                    showToast("Доступ заблоковано", "info");
                    await loadUsersTable();
                } catch (err) {
                    b.disabled = false;
                    showToast("⚠️ Помилка зміни доступу: " + (err.message || err), "error");
                }
            });
        });

        tbody.querySelectorAll(".btn-delete-user").forEach(b => {
            b.addEventListener("click", async () => {
                const id = b.getAttribute("data-id");
                if (confirm(`Видалити користувача ${id}?`)) {
                    b.disabled = true;
                    try {
                        const res = await deleteUserApi(id);
                        if (res && res.error) {
                            showToast("⚠️ Помилка видалення: " + res.error, "error");
                            b.disabled = false;
                            return;
                        }
                        triggerHaptic("medium");
                        showToast("Користувача видалено", "info");
                        await loadUsersTable();
                    } catch (err) {
                        b.disabled = false;
                        showToast("⚠️ Помилка видалення: " + (err.message || err), "error");
                    }
                }
            });
        });
    } catch (e) {
        console.error("Failed loading users table:", e);
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger p-3">Помилка завантаження користувачів: ${escapeHtml(e.message || String(e))}</td></tr>`;
    }
}

/**
 * Fetch server health & telemetry (/health) and update status indicators
 */
export async function updateServerHealthAndStats() {
    const elUptime = document.getElementById("sys-uptime");
    const elPrinters = document.getElementById("sys-printers-count");
    const elCpu = document.getElementById("sys-cpu-temp");
    const elRam = document.getElementById("sys-ram-usage");
    const elDisk = document.getElementById("sys-disk-free");

    try {
        const data = await fetchHealthApi();
        if (!data) return;

        const lang = state.currentLanguage || "uk";

        if (elUptime && data.uptime_seconds !== undefined) {
            elUptime.textContent = formatUptime(data.uptime_seconds, lang);
        }

        if (elPrinters) {
            const active = data.active_printers ?? 0;
            const total = data.total_printers ?? (state.printers?.length ?? 0);
            elPrinters.textContent = lang === "en" ? `${active} active / ${total} total` : `${active} активних / ${total} всього`;
        }

        const sys = data.system || {};
        if (elCpu) {
            if (sys.cpu_temp_c !== null && sys.cpu_temp_c !== undefined) {
                elCpu.textContent = `${sys.cpu_temp_c}°C`;
            } else {
                elCpu.textContent = "-";
            }
        }

        if (elRam) {
            if (sys.ram_pct !== null && sys.ram_pct !== undefined) {
                const used = sys.ram_used_mb || 0;
                const total = sys.ram_total_mb || 0;
                elRam.textContent = `${sys.ram_pct}% (${used} / ${total} MB)`;
            } else {
                elRam.textContent = "-";
            }
        }

        if (elDisk) {
            if (sys.disk_free_gb !== null && sys.disk_free_gb !== undefined) {
                const free = sys.disk_free_gb;
                const total = sys.disk_total_gb || 0;
                const pct = sys.disk_pct !== undefined ? `${sys.disk_pct}%` : "";
                elDisk.textContent = `${free} GB ${pct ? `(${pct})` : ""} / ${total} GB`;
            } else {
                elDisk.textContent = "-";
            }
        }
    } catch (e) {
        console.error("Failed updating server health telemetry:", e);
    }
}

/**
 * Populate printer dropdown in the Tab 5 settings card
 */
export async function populatePrinterSettingsSelect() {
    const select = document.getElementById("printer-settings-select");
    if (!select) return;

    // If the user is currently interacting with the dropdown, don't wipe it
    if (document.activeElement === select) return;

    let printers = state.printers;
    if (!printers || !Array.isArray(printers) || printers.length === 0) {
        try {
            printers = await fetchPrintersApi();
            state.printers = printers;
        } catch (_) {
            printers = [];
        }
    }

    // Compare list signature to prevent flickering/re-rendering when printers list did not change
    const signature = (printers || []).map(p => `${p.id}:${p.name}:${p.model || p.printer_model || ""}`).join("|");
    if (select.dataset.sig === signature && select.children.length > 1) {
        return;
    }
    select.dataset.sig = signature;

    const currentVal = select.value;
    select.innerHTML = `<option value="">-- Оберіть принтер --</option>`;

    if (Array.isArray(printers)) {
        printers.forEach(p => {
            const opt = document.createElement("option");
            opt.value = p.id;
            opt.textContent = `${p.name || p.id} (${p.model || p.printer_model || "Bambu Lab"})`;
            select.appendChild(opt);
        });
    }

    if (currentVal && printers.some(p => String(p.id) === String(currentVal))) {
        select.value = currentVal;
    } else {
        const formContainer = document.getElementById("printer-settings-form-container");
        if (formContainer && !select.value) {
            formContainer.style.display = "none";
        }
    }
}

/**
 * Load individual printer settings into the Tab 5 form
 */
export async function loadPrinterSettings(printerId) {
    const formContainer = document.getElementById("printer-settings-form-container");
    if (!printerId) {
        if (formContainer) formContainer.style.display = "none";
        return;
    }

    try {
        const s = await fetchPrinterSettingsApi(printerId);
        if (!s) return;

        if (formContainer) formContainer.style.display = "block";

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

        const counterEl = document.getElementById("p-setting-maint-counter-val");
        if (counterEl) {
            counterEl.textContent = `${s.maintenance_hours_counter ?? 0.0} год`;
        }

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

/**
 * Save per-printer settings edited inside Tab 5
 */
export async function savePrinterSettingsFromTab() {
    const sel = document.getElementById("printer-settings-select");
    const pId = sel?.value;
    if (!pId) {
        alert("Будь ласка, оберіть принтер зі списку.");
        return;
    }

    const saveBtn = document.getElementById("save-printer-settings-btn");
    if (saveBtn?.getAttribute("data-busy") === "true") return;

    const originalBtnHtml = saveBtn ? saveBtn.innerHTML : "";
    if (saveBtn) {
        saveBtn.setAttribute("data-busy", "true");
        saveBtn.disabled = true;
        saveBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Збереження...`;
    }

    const notifyObj = {
        start: document.getElementById("p-setting-notify-start")?.checked ?? true,
        finish: document.getElementById("p-setting-notify-finish")?.checked ?? true,
        pause: document.getElementById("p-setting-notify-pause")?.checked ?? true,
        hms: document.getElementById("p-setting-notify-hms")?.checked ?? true,
        remind_clear: document.getElementById("p-setting-notify-remind-clear")?.checked ?? true,
        min_time_to_end: parseInt(document.getElementById("p-setting-notify-min-time")?.value || 0, 10),
        min_filament: parseInt(document.getElementById("p-setting-notify-min-filament")?.value || 0, 10),
    };

    const payload = {
        name: document.getElementById("p-setting-name")?.value || "",
        ip: document.getElementById("p-setting-ip")?.value || "",
        accessCode: document.getElementById("p-setting-access-code")?.value || "",
        serialNumber: document.getElementById("p-setting-sn")?.value || "",
        printer_model: document.getElementById("p-setting-model")?.value || "A1",
        nozzle_diameter: document.getElementById("p-setting-nozzle-diameter")?.value || "0.4",
        ams_enabled: document.getElementById("p-setting-ams")?.value === "true" ? true : (document.getElementById("p-setting-ams")?.value === "false" ? false : "auto"),
        maintenance_interval_hours: parseInt(document.getElementById("p-setting-maint-interval")?.value || 100, 10),
        notify: notifyObj,
    };

    if (payload.accessCode?.includes("•")) {
        delete payload.accessCode;
    }

    try {
        const res = await savePrinterSettingsApi(pId, payload);
        if (res && res.error) throw new Error(res.error);
        triggerHaptic("success");
        showToast("✅ Налаштування принтера успішно збережено!", "success");

        if (typeof window.fetchPrinters === "function") {
            await window.fetchPrinters();
        } else {
            const printers = await fetchPrintersApi();
            state.printers = printers;
        }
        await populatePrinterSettingsSelect();
    } catch (e) {
        triggerHaptic("error");
        console.error("Failed saving printer settings via tab:", e);
        showToast("⚠️ Помилка збереження налаштувань: " + (e.message || e), "error");
    } finally {
        if (saveBtn) {
            saveBtn.removeAttribute("data-busy");
            saveBtn.disabled = false;
            saveBtn.innerHTML = originalBtnHtml;
        }
    }
}

/**
 * Reset printer maintenance hours counter
 */
export async function resetPrinterMaintenance() {
    const sel = document.getElementById("printer-settings-select");
    const pId = sel?.value;
    if (!pId) {
        showToast("Оберіть принтер зі списку!", "warning");
        return;
    }

    if (!confirm("Ви впевнені, що хочете скинути лічильник напрацювання годин ТО для цього принтера?")) {
        return;
    }

    const resetBtn = document.getElementById("p-setting-reset-maint-btn");
    const originalHtml = resetBtn ? resetBtn.innerHTML : "";
    if (resetBtn) {
        resetBtn.disabled = true;
        resetBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Скидання...`;
    }

    try {
        const res = await savePrinterSettingsApi(pId, { reset_maintenance: true });
        if (res && res.error) throw new Error(res.error);
        triggerHaptic("success");
        const counterEl = document.getElementById("p-setting-maint-counter-val");
        if (counterEl) {
            const newCount = res?.settings?.maintenance_hours_counter ?? 0.0;
            counterEl.textContent = `${newCount} год`;
        }
        showToast("✅ Лічильник годин технічного обслуговування скинуто на 0.0 год!", "success");
    } catch (e) {
        triggerHaptic("error");
        console.error("Failed resetting maintenance:", e);
        showToast("⚠️ Помилка при скиданні лічильника ТО: " + (e.message || e), "error");
    } finally {
        if (resetBtn) {
            resetBtn.disabled = false;
            resetBtn.innerHTML = originalHtml;
        }
    }
}

/**
 * Open modal for quick printer settings from farm card
 */
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

/**
 * Save settings from quick modal
 */
export async function savePrinterSettingsModal() {
    const pId = document.getElementById("ps-modal-printer-id")?.value;
    if (!pId) return;

    const notifyObj = {
        start: document.getElementById("ps-modal-notify-start")?.checked ?? true,
        finish: document.getElementById("ps-modal-notify-finish")?.checked ?? true,
        pause: document.getElementById("ps-modal-notify-pause")?.checked ?? true,
        hms: document.getElementById("ps-modal-notify-hms")?.checked ?? true,
        remind_clear: document.getElementById("ps-modal-notify-remind-clear")?.checked ?? true,
        min_time_to_end: parseInt(document.getElementById("ps-modal-notify-min-time")?.value || 0, 10),
        min_filament: parseInt(document.getElementById("ps-modal-notify-min-filament")?.value || 0, 10),
    };

    const payload = {
        name: document.getElementById("ps-modal-name")?.value || "",
        ip: document.getElementById("ps-modal-ip")?.value || "",
        accessCode: document.getElementById("ps-modal-access-code")?.value || "",
        serialNumber: document.getElementById("ps-modal-sn")?.value || "",
        printer_model: document.getElementById("ps-modal-model")?.value || "A1",
        nozzle_diameter: document.getElementById("ps-modal-nozzle-diameter")?.value || "0.4",
        ams_enabled: document.getElementById("ps-modal-ams")?.value === "true" ? true : (document.getElementById("ps-modal-ams")?.value === "false" ? false : "auto"),
        maintenance_interval_hours: parseInt(document.getElementById("ps-modal-maint-interval")?.value || 100, 10),
        notify: notifyObj,
    };

    if (payload.accessCode?.includes("•")) {
        delete payload.accessCode;
    }

    try {
        const res = await savePrinterSettingsApi(pId, payload);
        if (res && res.error) throw new Error(res.error);
        showToast("✅ Налаштування принтера успішно збережено!", "success");
        document.getElementById("printer-settings-modal")?.classList.remove("active");
        if (typeof window.fetchPrinters === "function") {
            await window.fetchPrinters();
        } else {
            const printers = await fetchPrintersApi();
            state.printers = printers;
        }
        await populatePrinterSettingsSelect();
    } catch (e) {
        console.error("Failed saving printer settings via modal:", e);
        showToast("⚠️ Помилка зв'язку із сервером: " + (e.message || e), "error");
    }
}

/**
 * Wire all event listeners for Settings tab & related modals
 */
export function initSettingsEventListeners() {
    if (state.settingsModuleBound) return;
    state.settingsModuleBound = true;

    // Global settings button (both IDs supported)
    document.getElementById("apply-global-settings-btn")?.addEventListener("click", saveSettings);
    document.getElementById("save-settings-btn")?.addEventListener("click", saveSettings);

    // Language switcher
    document.getElementById("setting-app-language")?.addEventListener("change", (e) => {
        setAppLanguage(e.target.value);
    });

    // Per-printer dropdown selection in Tab 5
    document.getElementById("printer-settings-select")?.addEventListener("change", (e) => {
        const pId = e.target.value;
        loadPrinterSettings(pId);
    });

    // Per-printer save button in Tab 5
    document.getElementById("save-printer-settings-btn")?.addEventListener("click", savePrinterSettingsFromTab);

    // Per-printer maintenance reset button in Tab 5
    document.getElementById("p-setting-reset-maint-btn")?.addEventListener("click", resetPrinterMaintenance);

    // Modal printer settings
    document.getElementById("close-printer-settings-modal")?.addEventListener("click", () => {
        document.getElementById("printer-settings-modal")?.classList.remove("active");
    });
    document.getElementById("save-printer-settings-modal-btn")?.addEventListener("click", savePrinterSettingsModal);

    const psModal = document.getElementById("printer-settings-modal");
    if (psModal) {
        psModal.addEventListener("click", (e) => {
            if (e.target === psModal) {
                psModal.classList.remove("active");
            }
        });
    }
}

export const initSettingsModule = initSettingsEventListeners;
export const applyLanguageDictionary = setAppLanguage;
