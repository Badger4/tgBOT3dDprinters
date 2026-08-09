/**
 * 3D Farm Telegram WebApp Application Logic
 */

// Automatically bypass localtunnel reminder page for all API requests
const originalFetch = window.fetch;
window.fetch = function(url, options = {}) {
    options = options || {};
    let h = options.headers;
    if (!h) {
        h = new Headers();
    } else if (!(h instanceof Headers)) {
        h = new Headers(h);
    }
    h.set("Bypass-Tunnel-Reminder", "true");
    options.headers = h;
    return originalFetch(url, options);
};

document.addEventListener("DOMContentLoaded", () => {
    // 1. Initialize Telegram WebApp SDK
    const tg = window.Telegram?.WebApp;
    if (tg) {
        tg.ready();
        tg.expand();
        tg.enableClosingConfirmation();
    }

    function triggerHaptic(type = "medium") {
        if (tg?.HapticFeedback) {
            tg.HapticFeedback.impactOccurred(type);
        }
    }

    function escapeHtml(str) {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // State Variables
    let printersData = [];
    let selectedPrinterId = null;
    let pollInterval = null;

    // DOM Elements
    const navButtons = document.querySelectorAll(".nav-btn");
    const tabPages = document.querySelectorAll(".tab-page");
    const printersGrid = document.getElementById("printers-grid");
    const activeCountEl = document.getElementById("active-count");
    const refreshBtn = document.getElementById("refresh-btn");

    // Modal Elements
    const printerModal = document.getElementById("printer-modal");
    const closeModalBtn = document.getElementById("close-modal-btn");
    const modalNameEl = document.getElementById("modal-printer-name");
    const modalStatusEl = document.getElementById("modal-printer-status");
    const cameraImg = document.getElementById("camera-snapshot-img");
    const refreshCamBtn = document.getElementById("refresh-cam-btn");

    const modalNozzleTemp = document.getElementById("modal-nozzle-temp");
    const modalBedTemp = document.getElementById("modal-bed-temp");
    const modalLayer = document.getElementById("modal-layer");
    const modalTime = document.getElementById("modal-time");

    const btnPause = document.getElementById("btn-action-pause");
    const btnResume = document.getElementById("btn-action-resume");
    const btnStop = document.getElementById("btn-action-stop");
    const btnLight = document.getElementById("btn-action-light");
    const btnResetMaint = document.getElementById("btn-reset-maint");
    const modalMaintHours = document.getElementById("modal-maint-hours");
    const modalMaintBar = document.getElementById("modal-maint-bar");
    const speedBtns = document.querySelectorAll(".speed-btn");

    // Spool Modal Elements
    const spoolModal = document.getElementById("spool-modal");
    const addSpoolBtn = document.getElementById("add-spool-btn");
    const closeSpoolModalBtn = document.getElementById("close-spool-modal");
    const saveSpoolSubmitBtn = document.getElementById("save-spool-submit");

    // 2. Navigation & Tabs
    navButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            triggerHaptic("light");
            const targetTab = btn.getAttribute("data-tab");

            navButtons.forEach(b => b.classList.remove("active"));
            tabPages.forEach(p => p.classList.remove("active"));

            btn.classList.add("active");
            document.getElementById(targetTab).classList.add("active");

            if (targetTab === "tab-materials") loadMaterials();
            if (targetTab === "tab-history") loadHistory();
            if (targetTab === "tab-settings") loadSettings();
        });
    });

    // 3. Fetch & Render Printers Telemetry
    async function fetchPrinters() {
        try {
            const res = await fetch("/api/printers");
            if (!res.ok) throw new Error("Failed fetching printers");
            printersData = await res.json();
            renderPrinters(printersData);

            if (selectedPrinterId && printerModal.classList.contains("active")) {
                const currentP = printersData.find(p => p.id === selectedPrinterId);
                if (currentP) updatePrinterModalContent(currentP);
            }
        } catch (err) {
            console.error("Error fetching printers:", err);
        }
    }

    function renderPrinters(printers) {
        if (!printers || printers.length === 0) {
            printersGrid.innerHTML = `
                <div class="glass-card text-center p-4">
                    <i class="fa-solid fa-triangle-exclamation color-orange fa-2x mb-2"></i>
                    <p>Не знайдено жодного підключеного принтера Bambu Lab.</p>
                </div>`;
            activeCountEl.textContent = "0/0";
            return;
        }

        const activeCount = printers.filter(p => p.state === "RUNNING").length;
        activeCountEl.textContent = `${activeCount}/${printers.length}`;

        printersGrid.innerHTML = printers.map(p => {
            const isPrinting = p.state === "RUNNING";
            const progress = p.progress_pct || 0;
            const modelName = p.subtask_name || (isPrinting ? "Друк..." : "Вільний");
            const usedWeight = p.job_weight_g > 0 ? `${p.job_weight_g}g` : "-";

            return `
                <div class="printer-card" data-id="${p.id}">
                    <div class="printer-card-header">
                        <div class="printer-name-group">
                            <h3>${p.name}</h3>
                            <div class="printer-model-sub"><i class="fa-solid fa-file-code"></i> ${modelName}</div>
                        </div>
                        <span class="status-pill status-${p.state}">${p.state}</span>
                    </div>

                    <div class="progress-container">
                        <div class="progress-header">
                            <span>Прогрес: ${progress}%</span>
                            <span>${p.remaining_mins > 0 ? p.remaining_mins + ' хв' : ''}</span>
                        </div>
                        <div class="progress-bar-wrap">
                            <div class="progress-bar ${p.state === 'PAUSE' ? 'amber' : ''}" style="width: ${progress}%;"></div>
                        </div>
                    </div>

                    <div class="printer-stats-row">
                        <span><i class="fa-solid fa-temperature-high color-red"></i> ${p.nozzle_temp}°C</span>
                        <span><i class="fa-solid fa-hot-tub-person color-orange"></i> ${p.bed_temp}°C</span>
                        <span><i class="fa-solid fa-layer-group color-blue"></i> ${p.current_layer}/${p.total_layers}</span>
                        <span><i class="fa-solid fa-spool color-purple"></i> ${p.filament_type} (${p.filament_grams_left}g)</span>
                    </div>
                </div>`;
        }).join("");

        // Attach click listeners to cards
        document.querySelectorAll(".printer-card").forEach(card => {
            card.addEventListener("click", () => {
                const pId = card.getAttribute("data-id");
                openPrinterModal(pId);
            });
        });
    }

    // 4. Printer Details Modal
    function openPrinterModal(pId) {
        triggerHaptic("medium");
        selectedPrinterId = pId;
        const p = printersData.find(x => x.id === pId);
        if (!p) return;

        updatePrinterModalContent(p);
        loadCameraSnapshot(pId);
        printerModal.classList.add("active");
    }

    function updatePrinterModalContent(p) {
        modalNameEl.textContent = p.name;
        modalStatusEl.textContent = p.state;
        modalStatusEl.className = `status-pill status-${p.state}`;

        modalNozzleTemp.textContent = `${p.nozzle_temp}°C`;
        modalBedTemp.textContent = `${p.bed_temp}°C`;
        modalLayer.textContent = `${p.current_layer} / ${p.total_layers}`;
        modalTime.textContent = p.remaining_mins > 0 ? `${p.remaining_mins} хв` : "0 хв";

        // Speed buttons
        speedBtns.forEach(btn => {
            const lvl = parseInt(btn.getAttribute("data-level"));
            btn.classList.toggle("active", lvl === p.spd_lvl);
        });

        // Action buttons state
        if (p.state === "PAUSE") {
            btnPause.style.display = "none";
            btnResume.style.display = "inline-flex";
        } else {
            btnPause.style.display = "inline-flex";
            btnResume.style.display = "none";
        }

        // Maintenance
        const maintCounter = p.maintenance_hours_counter || 0.0;
        const maintInterval = p.maintenance_interval_hours || 100;
        const maintPct = Math.min(100, (maintCounter / maintInterval) * 100);
        modalMaintHours.textContent = `${maintCounter.toFixed(1)} / ${maintInterval} год`;
        modalMaintBar.style.width = `${maintPct}%`;
    }

    function loadCameraSnapshot(pId) {
        cameraImg.style.display = "block";
        cameraImg.nextElementSibling.style.display = "none";
        cameraImg.src = `/api/printers/${pId}/snapshot?t=${Date.now()}`;
    }

    closeModalBtn.addEventListener("click", () => {
        triggerHaptic("light");
        printerModal.classList.remove("active");
        selectedPrinterId = null;
    });

    refreshCamBtn.addEventListener("click", () => {
        triggerHaptic("light");
        if (selectedPrinterId) loadCameraSnapshot(selectedPrinterId);
    });

    // 5. Remote Printer Controls (Pause, Resume, Stop, Speed, Light, Reset Maintenance)
    async function sendPrinterAction(actionPayload) {
        if (!selectedPrinterId) return;
        triggerHaptic("medium");
        try {
            const res = await fetch(`/api/printers/${selectedPrinterId}/control`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(actionPayload)
            });
            const data = await res.json();
            if (data.status === "ok") {
                fetchPrinters();
            } else {
                alert("Помилка при виконанні дії: " + (data.error || "Невідомо"));
            }
        } catch (e) {
            console.error("Action error:", e);
        }
    }

    btnPause.addEventListener("click", () => sendPrinterAction({ action: "pause" }));
    btnResume.addEventListener("click", () => sendPrinterAction({ action: "resume" }));
    btnStop.addEventListener("click", () => {
        if (confirm("Ви дійсно хочете ЗУПИНИТИ друк?")) {
            sendPrinterAction({ action: "stop" });
        }
    });
    btnLight.addEventListener("click", () => sendPrinterAction({ action: "light_toggle" }));
    btnResetMaint.addEventListener("click", () => {
        if (confirm("Скинути лічильник ТО (100 годин)?")) {
            sendPrinterAction({ action: "reset_maint" });
        }
    });

    speedBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            const level = parseInt(btn.getAttribute("data-level"));
            sendPrinterAction({ action: "set_speed", level: level });
        });
    });

    // 6. Tab 2: Materials & AMS
    async function loadMaterials() {
        const container = document.getElementById("ams-printers-container");
        container.innerHTML = `<div class="loading-spinner"><i class="fa-solid fa-circle-notch fa-spin"></i> Завантаження...</div>`;

        try {
            const [printersRes, spoolsRes] = await Promise.all([
                fetch("/api/printers"),
                fetch("/api/spools")
            ]);
            const printers = await printersRes.json();
            const spools = await spoolsRes.json();

            // Render AMS for printers
            if (!printers || printers.length === 0) {
                container.innerHTML = `<p class="text-muted">Немає активних принтерів</p>`;
            } else {
                container.innerHTML = printers.map(p => {
                    const activeKey = String(p.active_slot_key || "255");
                    const slots = p.ams_slots || {};
                    const slotKeys = ["0", "1", "2", "3", "255"];
                    const slotLabels = { "0": "A1", "1": "A2", "2": "A3", "3": "A4", "255": "VT" };

                    return `
                        <div class="ams-printer-block">
                            <div class="ams-printer-title"><i class="fa-solid fa-print"></i> ${p.name}</div>
                            <div class="ams-slots-grid">
                                ${slotKeys.map(k => {
                                    const grams = slots[k] !== undefined ? slots[k] : 1000;
                                    const isActive = (k === activeKey);
                                    return `
                                        <div class="ams-slot-card ${isActive ? 'active-slot' : ''}">
                                            <div class="slot-tag">${slotLabels[k]} ${isActive ? '⚡' : ''}</div>
                                            <div class="slot-spool-icon"><i class="fa-solid fa-spool"></i></div>
                                            <div class="slot-weight">${grams}g</div>
                                        </div>`;
                                }).join("")}
                            </div>
                        </div>`;
                }).join("");
            }

            // Render Spool Inventory
            const spoolsList = document.getElementById("spools-list");
            const spoolsArray = Object.values(spools || {});
            if (spoolsArray.length === 0) {
                spoolsList.innerHTML = `<p class="text-muted text-center p-3">Склад порожній. Натисніть "+ Нова котушка", щоб додати.</p>`;
            } else {
                spoolsList.innerHTML = spoolsArray.map(s => `
                    <div class="spool-item">
                        <div class="spool-left">
                            <div class="spool-color-circle" style="background-color: ${s.color || '#6366f1'};"></div>
                            <div class="spool-details">
                                <h4>${s.name}</h4>
                                <p>${s.type || 'PLA'} • ${s.price_per_kg || 650} ₴/кг</p>
                            </div>
                        </div>
                        <div class="spool-right text-right">
                            <strong>${s.remaining_grams || 1000}g</strong>
                            <button class="icon-btn text-danger btn-delete-spool" data-id="${s.id}" style="margin-left: 10px;">
                                <i class="fa-solid fa-trash"></i>
                            </button>
                        </div>
                    </div>`).join("");

                document.querySelectorAll(".btn-delete-spool").forEach(b => {
                    b.addEventListener("click", async () => {
                        const id = b.getAttribute("data-id");
                        if (confirm("Видалити цю котушку зі складу?")) {
                            await fetch(`/api/spools/${id}`, { method: "DELETE" });
                            loadMaterials();
                        }
                    });
                });
            }

        } catch (e) {
            console.error("Error loading materials:", e);
        }
    }

    // Add Spool Form Modal
    addSpoolBtn.addEventListener("click", () => {
        triggerHaptic("medium");
        spoolModal.classList.add("active");
    });

    closeSpoolModalBtn.addEventListener("click", () => {
        spoolModal.classList.remove("active");
    });

    saveSpoolSubmitBtn.addEventListener("click", async () => {
        const name = document.getElementById("spool-name").value.trim();
        const type = document.getElementById("spool-type").value;
        const grams = parseFloat(document.getElementById("spool-grams").value) || 1000;
        const price = parseFloat(document.getElementById("spool-price").value) || 650;

        if (!name) { alert("Введіть назву котушки!"); return; }

        try {
            await fetch("/api/spools", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name, type, remaining_grams: grams, price_per_kg: price })
            });
            spoolModal.classList.remove("active");
            loadMaterials();
        } catch (e) {
            console.error("Failed saving spool:", e);
        }
    });

    // 8. Tab 3: History
    async function loadHistory() {
        try {
            const res = await fetch("/api/history");
            const data = await res.json();

            document.getElementById("stat-total-jobs").textContent = data.total_jobs || 0;
            document.getElementById("stat-total-weight").textContent = `${data.total_weight_kg || 0} kg`;
            document.getElementById("stat-total-cost").textContent = `${data.total_cost_uah || 0} ₴`;

            const tbody = document.getElementById("history-table-body");
            const history = data.history || [];
            if (history.length === 0) {
                tbody.innerHTML = `<tr><td colspan="5" class="text-center">Журнал історії порожній</td></tr>`;
            } else {
                tbody.innerHTML = history.slice(-20).reverse().map(item => `
                    <tr>
                        <td>${item.timestamp || '-'}</td>
                        <td>${item.printer || '-'}</td>
                        <td><code>${item.task || '-'}</code></td>
                        <td>${item.weight_g || 0}g</td>
                        <td><strong>${item.cost_uah || 0} ₴</strong></td>
                    </tr>`).join("");
            }
        } catch (e) {
            console.error("Failed loading history:", e);
        }
    }

    // 9. Tab 2: Commercial Calculator & Presets
    let currentPresets = {};
    let editingPresetId = null;

    async function loadCommercialPresets() {
        try {
            const res = await fetch("/api/commercial/presets");
            currentPresets = await res.json();

            const selectEl = document.getElementById("calc-preset-select");
            const listEl = document.getElementById("presets-list");

            selectEl.innerHTML = Object.values(currentPresets).map(p => 
                `<option value="${p.id}">${escapeHtml(p.name)}</option>`
            ).join("");

            if (Object.keys(currentPresets).length > 0) {
                if (!selectEl.value) selectEl.value = Object.keys(currentPresets)[0];
            }

            listEl.innerHTML = Object.values(currentPresets).map(p => `
                <div class="spool-item">
                    <div class="spool-left">
                        <i class="fa-solid fa-calculator color-orange" style="font-size:20px;"></i>
                        <div class="spool-details">
                            <h4>${escapeHtml(p.name)}</h4>
                            <p>Пластик: ${p.price_per_g} грн/г | Потужність: ${p.power_watts} Вт | Маржа: ${p.profit_val}</p>
                        </div>
                    </div>
                    <div class="preset-actions-wrap" style="display:flex; gap:6px;">
                        <button class="btn btn-xs btn-outline-warning btn-edit-preset" data-id="${p.id}" title="Редагувати">
                            <i class="fa-solid fa-pen-to-square"></i>
                        </button>
                        <button class="btn btn-xs btn-outline-danger btn-delete-preset" data-id="${p.id}" title="Видалити">
                            <i class="fa-solid fa-trash"></i>
                        </button>
                    </div>
                </div>
            `).join("");

            document.querySelectorAll(".btn-edit-preset").forEach(btn => {
                btn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    const pId = btn.getAttribute("data-id");
                    const p = currentPresets[pId];
                    if (!p) return;

                    editingPresetId = pId;
                    const titleEl = document.getElementById("preset-modal-title");
                    if (titleEl) titleEl.textContent = "✏️ Редагувати пресет";

                    document.getElementById("preset-name").value = p.name || "";
                    document.getElementById("preset-price-g").value = p.price_per_g !== undefined ? p.price_per_g : 0.85;
                    document.getElementById("preset-power").value = p.power_watts !== undefined ? p.power_watts : 120;
                    document.getElementById("preset-depreciation").value = p.depreciation_val || "10";
                    document.getElementById("preset-consumables").value = p.consumables_val || "5";
                    document.getElementById("preset-profit").value = p.profit_val || "100%";

                    triggerHaptic("light");
                    presetModal.classList.add("active");
                });
            });

            document.querySelectorAll(".btn-delete-preset").forEach(btn => {
                btn.addEventListener("click", async (e) => {
                    e.stopPropagation();
                    const pId = btn.getAttribute("data-id");
                    if (confirm("Видалити цей пресет?")) {
                        await fetch(`/api/commercial/presets/${pId}`, { method: "DELETE" });
                        loadCommercialPresets();
                    }
                });
            });

            recalculateCommercial();
        } catch (e) {
            console.error("Failed loading commercial presets:", e);
        }
    }

    async function recalculateCommercial() {
        const weight_g = parseFloat(document.getElementById("calc-weight-g").value) || 100;
        const time_mins = parseInt(document.getElementById("calc-time-mins").value) || 60;
        const preset_id = document.getElementById("calc-preset-select").value;

        try {
            const res = await fetch("/api/commercial/calculate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ weight_g, time_mins, preset_id })
            });
            const data = await res.json();
            if (data.status === "ok" && data.calculation) {
                const c = data.calculation;
                document.getElementById("res-total-price").textContent = `${c.total_price.toFixed(2)} ₴`;
                document.getElementById("res-filament-cost").textContent = `${c.filament_cost.toFixed(2)} ₴`;
                document.getElementById("res-elec-cost").textContent = `${c.electricity_cost.toFixed(2)} ₴`;
                document.getElementById("res-depr-cost").textContent = `${c.depreciation_cost.toFixed(2)} ₴ (${c.depreciation_str})`;
                document.getElementById("res-cons-cost").textContent = `${c.consumables_cost.toFixed(2)} ₴ (${c.consumables_str})`;
                document.getElementById("res-direct-cost").textContent = `${c.direct_cost.toFixed(2)} ₴`;
                document.getElementById("res-profit-cost").textContent = `${c.profit_cost.toFixed(2)} ₴ (${c.profit_str})`;
            }
        } catch (e) {
            console.error("Failed calculating commercial price:", e);
        }
    }

    document.getElementById("calc-preset-select").addEventListener("change", recalculateCommercial);
    document.getElementById("calc-weight-g").addEventListener("input", recalculateCommercial);
    document.getElementById("calc-time-mins").addEventListener("input", recalculateCommercial);

    // Preset Modal handlers
    const presetModal = document.getElementById("preset-modal");
    document.getElementById("add-preset-btn").addEventListener("click", () => {
        editingPresetId = null;
        const titleEl = document.getElementById("preset-modal-title");
        if (titleEl) titleEl.textContent = "➕ Створити пресет ціноутворення";

        document.getElementById("preset-name").value = "";
        document.getElementById("preset-price-g").value = "0.85";
        document.getElementById("preset-power").value = "120";
        document.getElementById("preset-depreciation").value = "10";
        document.getElementById("preset-consumables").value = "5";
        document.getElementById("preset-profit").value = "100%";

        triggerHaptic("light");
        presetModal.classList.add("active");
    });
    document.getElementById("close-preset-modal").addEventListener("click", () => {
        presetModal.classList.remove("active");
    });
    document.getElementById("save-preset-submit").addEventListener("click", async () => {
        triggerHaptic("medium");
        const name = document.getElementById("preset-name").value.trim();
        const raw_price = document.getElementById("preset-price-g").value;
        const price_per_g = (raw_price && !isNaN(parseFloat(raw_price))) ? parseFloat(raw_price) : 0.85;
        const raw_power = document.getElementById("preset-power").value;
        const power_watts = (raw_power && !isNaN(parseFloat(raw_power))) ? parseFloat(raw_power) : 120.0;
        const depreciation_val = document.getElementById("preset-depreciation").value.trim() || "10";
        const consumables_val = document.getElementById("preset-consumables").value.trim() || "5";
        const profit_val = document.getElementById("preset-profit").value.trim() || "100%";

        if (!name) return alert("⚠️ Введіть назву пресета");

        const payload = {
            name, price_per_g, power_watts, depreciation_val, consumables_val, profit_val
        };
        if (editingPresetId) {
            payload.id = editingPresetId;
        }

        try {
            const res = await fetch("/api/commercial/presets", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.status === "ok") {
                presetModal.classList.remove("active");
                editingPresetId = null;
                await loadCommercialPresets();
            } else {
                alert(`⚠️ Помилка збереження: ${data.error || "Невідома"}`);
            }
        } catch (e) {
            console.error("Failed saving preset:", e);
            alert(`⚠️ Не вдалося зберегти пресет: ${e.message || e}`);
        }
    });

    // Update Tab Listener
    document.querySelectorAll(".nav-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            triggerHaptic("light");
            const tabId = btn.getAttribute("data-tab");
            
            document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
            document.querySelectorAll(".tab-page").forEach(p => p.classList.remove("active"));
            
            btn.classList.add("active");
            document.getElementById(tabId).classList.add("active");

            if (tabId === "tab-commercial") loadCommercialPresets();
            if (tabId === "tab-materials") loadMaterials();
            if (tabId === "tab-history") loadHistory();
            if (tabId === "tab-settings") loadSettings();
        });
    });

    // 10. Tab 5: Settings
    async function loadSettings() {
        try {
            const [settingsRes, healthRes] = await Promise.all([
                fetch("/api/settings"),
                fetch("/health")
            ]);
            const settings = await settingsRes.json();
            const health = await healthRes.json();

            document.getElementById("setting-notify-start").checked = settings.notify_start !== false;
            document.getElementById("setting-notify-finish").checked = settings.notify_finish !== false;
            document.getElementById("setting-notify-pause").checked = settings.notify_pause !== false;

            const uptimeMins = Math.floor((health.uptime_seconds || 0) / 60);
            document.getElementById("sys-uptime").textContent = `${uptimeMins} хв`;
            document.getElementById("sys-printers-count").textContent = health.total_printers || 0;
        } catch (e) {
            console.error("Failed loading settings:", e);
        }
    }

    document.getElementById("save-settings-btn").addEventListener("click", async () => {
        triggerHaptic("medium");
        const notify_start = document.getElementById("setting-notify-start").checked;
        const notify_finish = document.getElementById("setting-notify-finish").checked;
        const notify_pause = document.getElementById("setting-notify-pause").checked;

        try {
            await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ notify_start, notify_finish, notify_pause })
            });
            alert("Налаштування успішно збережено!");
        } catch (e) {
            console.error("Failed saving settings:", e);
        }
    });

    // File Upload & Choice Modal Logic
    const uploadBtn = document.getElementById("upload-file-btn");
    const fileInput = document.getElementById("file-upload-input");
    const fileActionModal = document.getElementById("file-action-modal");
    const closeFileModalBtn = document.getElementById("close-file-action-modal");
    const btnChoiceCalc = document.getElementById("btn-choice-calc");
    const btnChoicePrint = document.getElementById("btn-choice-print");
    const filePrintPanel = document.getElementById("file-print-panel");
    const filePrintersList = document.getElementById("file-printers-list");

    let uploadedFileData = null;

    if (uploadBtn && fileInput) {
        uploadBtn.addEventListener("click", () => {
            triggerHaptic("light");
            fileInput.click();
        });

        fileInput.addEventListener("change", async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            if (!file.name.toLowerCase().endsWith(".3mf")) {
                alert("⚠️ Дозволено завантажувати тільки файли з розширенням .3mf від Bambu Studio або OrcaSlicer!");
                fileInput.value = "";
                return;
            }

            const formData = new FormData();
            formData.append("file", file);

            triggerHaptic("medium");
            uploadBtn.disabled = true;
            uploadBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Аналіз...`;

            try {
                const res = await fetch("/api/files/upload", {
                    method: "POST",
                    body: formData
                });
                const data = await res.json();

                uploadBtn.disabled = false;
                uploadBtn.innerHTML = `<i class="fa-solid fa-file-arrow-up"></i> 📥 Файл`;
                fileInput.value = "";

                if (data.status === "ok") {
                    uploadedFileData = data;
                    const elFilename = document.getElementById("file-modal-filename");
                    const elModel = document.getElementById("file-modal-model");
                    const elType = document.getElementById("file-modal-type") || document.getElementById("file-modal-filament");
                    const elWeight = document.getElementById("file-modal-weight");
                    const elTime = document.getElementById("file-modal-time");

                    if (elFilename) elFilename.textContent = data.filename || "";
                    if (elModel) elModel.textContent = data.printer_model || "Невизначено";
                    if (elType) elType.textContent = data.filament_type || "PLA";
                    if (elWeight) elWeight.textContent = `${data.weight_g} г`;
                    if (elTime) elTime.textContent = `${data.time_mins} хв`;

                    filePrintPanel.style.display = "none";
                    fileActionModal.classList.add("active");
                } else {
                    alert(`Помилка аналізу файлу: ${data.error || "Невідома"}`);
                }
            } catch (err) {
                uploadBtn.disabled = false;
                uploadBtn.innerHTML = `<i class="fa-solid fa-file-arrow-up"></i> 📥 Файл`;
                console.error("File upload error:", err);
                alert(`Не вдалося завантажити файл: ${err.message || err}`);
            }
        });
    }

    if (closeFileModalBtn) {
        closeFileModalBtn.addEventListener("click", () => {
            fileActionModal.classList.remove("active");
        });
    }

    // Choice 1: Calculate Commercial Cost
    if (btnChoiceCalc) {
        btnChoiceCalc.addEventListener("click", async () => {
            triggerHaptic("medium");
            if (!uploadedFileData) return;

            fileActionModal.classList.remove("active");

            // Switch to Commercial Tab
            document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
            document.querySelectorAll(".tab-page").forEach(p => p.classList.remove("active"));

            const commNavBtn = document.querySelector('.nav-btn[data-tab="tab-commercial"]');
            if (commNavBtn) commNavBtn.classList.add("active");
            document.getElementById("tab-commercial").classList.add("active");

            // Pre-fill weight and time from 3MF metadata
            document.getElementById("calc-weight-g").value = uploadedFileData.weight_g || 100;
            document.getElementById("calc-time-mins").value = uploadedFileData.time_mins || 60;

            await loadCommercialPresets();
            await recalculateCommercial();
        });
    }

    // Choice 2: Send to Print
    if (btnChoicePrint) {
        btnChoicePrint.addEventListener("click", () => {
            triggerHaptic("medium");
            if (!uploadedFileData) return;

            filePrintPanel.style.display = "block";

            const printers = uploadedFileData.printers || [];
            filePrintersList.innerHTML = printers.map(p => `
                <div class="spool-item mb-2">
                    <div class="spool-left">
                        <i class="fa-solid fa-print ${p.state === 'RUNNING' ? 'color-green' : 'color-purple'}" style="font-size:20px;"></i>
                        <div class="spool-details">
                            <h4>${escapeHtml(p.name)}</h4>
                            <p>Статус: <strong>${p.state}</strong> | ${p.compatible ? '✅ Сумісний' : '🛑 Несумісна модель'}</p>
                        </div>
                    </div>
                    <button class="btn btn-sm ${p.compatible ? 'btn-success' : 'btn-outline-danger'} btn-start-print-job" data-id="${p.id}" ${p.state === 'RUNNING' ? 'disabled' : ''}>
                        ${p.state === 'RUNNING' ? 'Зайнятий' : '🚀 Друк'}
                    </button>
                </div>
            `).join("");

            document.querySelectorAll(".btn-start-print-job").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const printerId = btn.getAttribute("data-id");
                    triggerHaptic("heavy");
                    btn.disabled = true;
                    btn.textContent = "⏳ Відправка...";

                    try {
                        const res = await fetch(`/api/printers/${printerId}/print_file`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                file_token: uploadedFileData.file_token,
                                filename: uploadedFileData.filename
                            })
                        });
                        const result = await res.json();
                        if (result.status === "ok") {
                            alert(`Успіх! ${result.message || "Файл відправлено на друк!"}`);
                            fileActionModal.classList.remove("active");
                            fetchPrinters();
                        } else {
                            alert(`Помилка запуску: ${result.error}`);
                            btn.disabled = false;
                            btn.textContent = "🚀 Друк";
                        }
                    } catch (err) {
                        console.error("Print job send error:", err);
                        alert("Помилка відправки команди друку.");
                        btn.disabled = false;
                        btn.textContent = "🚀 Друк";
                    }
                });
            });
        });
    }

    refreshBtn.addEventListener("click", () => {
        triggerHaptic("light");
        fetchPrinters();
    });

    // Initial Load & Polling Loop
    fetchPrinters();
    pollInterval = setInterval(fetchPrinters, 3000);
});


