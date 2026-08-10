/**
 * 3D Farm Telegram WebApp Application Logic
 */

// Automatically bypass localtunnel & attach Telegram WebApp HMAC initData to all API requests
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
    if (window.Telegram?.WebApp?.initData) {
        h.set("X-Telegram-Init-Data", window.Telegram.WebApp.initData);
    }
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
    const btnActionDelete = document.getElementById("btn-action-delete");
    const modalMaintHours = document.getElementById("modal-maint-hours");
    const modalMaintBar = document.getElementById("modal-maint-bar");
    const speedBtns = document.querySelectorAll(".speed-btn");

    // Add Printer Modal Elements
    const addPrinterBtn = document.getElementById("add-printer-btn");
    const addPrinterModal = document.getElementById("add-printer-modal");
    const closeAddPrinterModalBtn = document.getElementById("close-add-printer-modal");
    const savePrinterSubmitBtn = document.getElementById("save-printer-submit");

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

    // 3. SSE Live Event Stream Listener & Telemetry Fetching
    function initSSEStream() {
        if (!window.EventSource) return;
        try {
            const initDataParam = tg?.initData ? "?initData=" + encodeURIComponent(tg.initData) : "";
            const evtSource = new EventSource("/api/events" + initDataParam);
            evtSource.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    if (Array.isArray(data) && data.length > 0) {
                        printersData = data;
                        renderPrinters(printersData);
                        if (selectedPrinterId && printerModal.classList.contains("active")) {
                            const currentP = printersData.find(p => p.id === selectedPrinterId);
                            if (currentP) updatePrinterModalContent(currentP);
                        }
                    }
                } catch (e) {
                    console.error("SSE parse error:", e);
                }
            };
            evtSource.onerror = function() {
                evtSource.close();
            };
        } catch (e) {
            console.error("SSE initialization failed:", e);
        }
    }

    async function fetchPrinters() {
        try {
            const res = await fetch("/api/printers");
            if (res.status === 401 || res.status === 403) {
                renderAccessDenied();
                return;
            }
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

    function renderAccessDenied() {
        if (pollInterval) clearInterval(pollInterval);
        document.body.innerHTML = `
            <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;background:#0f172a;color:#ef4444;text-align:center;padding:24px;font-family:sans-serif;">
                <div style="font-size:54px;margin-bottom:16px;">⛔</div>
                <h2 style="font-size:24px;font-weight:700;margin-bottom:12px;color:#f87171;">Доступ заблоковано</h2>
                <p style="color:#94a3b8;max-width:360px;line-height:1.5;font-size:15px;">
                    Ваш акаунт не має прав доступу до цієї 3D Ферми або ваш доступ було скасовано адміністратором.
                </p>
            </div>`;
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
    async function openPrinterModal(pId) {
        triggerHaptic("medium");
        selectedPrinterId = pId;
        const p = printersData.find(x => x.id === pId);
        if (!p) return;

        try {
            const sRes = await fetch("/api/spools");
            if (sRes.ok) {
                window.latestSpools = await sRes.json();
            }
        } catch (e) {
            console.error("Error fetching spools for modal:", e);
        }

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

        const modalSubtask = document.getElementById("modal-subtask-name");
        const modalProgText = document.getElementById("modal-progress-text");
        const modalProgBar = document.getElementById("modal-progress-bar");
        if (modalSubtask && modalProgText && modalProgBar) {
            const isPrinting = p.state === "RUNNING";
            const progress = p.progress_pct || 0;
            const modelName = p.subtask_name || (isPrinting ? "Друк..." : "Вільний");
            modalSubtask.innerHTML = `<i class="fa-solid fa-file-code color-blue"></i> ${escapeHtml(modelName)}`;
            modalProgText.textContent = `${progress}%`;
            modalProgBar.style.width = `${progress}%`;
            modalProgBar.className = `progress-bar ${p.state === 'PAUSE' ? 'amber' : ''}`;
        }

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

        // Filament & AMS Slots in Modal
        const amsToggle = document.getElementById("modal-ams-toggle");
        const amsSlotsContainer = document.getElementById("modal-ams-slots-container");
        if (amsToggle && amsSlotsContainer) {
            amsToggle.checked = Boolean(p.has_ams);

            amsToggle.onchange = () => {
                const isChecked = amsToggle.checked;
                sendPrinterAction({ action: "set_ams_enabled", enabled: isChecked });
            };

            const hasAms = Boolean(p.has_ams);
            const activeKey = String(p.active_slot_key || "255");
            const slots = p.ams_slots || {};
            const slotKeys = hasAms ? ["0", "1", "2", "3", "255"] : ["255"];
            const slotLabels = { "0": "A1", "1": "A2", "2": "A3", "3": "A4", "255": hasAms ? "VT (Зовнішній)" : "Зовнішній котушкотримач" };
            const spoolsList = Object.values(window.latestSpools || {});

            amsSlotsContainer.innerHTML = slotKeys.map(k => {
                const grams = slots[k] !== undefined ? slots[k] : 1000;
                const isActive = (k === activeKey);
                const assignedSpool = spoolsList.find(s => s.assigned_printer_id === p.id && String(s.assigned_slot_key) === k);
                const trayInfo = (p.ams_trays_info || {})[k] || {};
                const isTrayEmpty = trayInfo.empty === true;

                let spoolColor = '#64748b';
                let spoolName = 'Порожньо';
                let spoolType = '—';
                let pct = Math.min(100, Math.max(0, Math.round((grams / 1000) * 100)));

                if (assignedSpool) {
                    spoolColor = assignedSpool.color || '#3b82f6';
                    spoolName = escapeHtml(assignedSpool.name);
                    spoolType = escapeHtml(assignedSpool.type);
                } else if (!isTrayEmpty && (trayInfo.type || trayInfo.color)) {
                    spoolColor = trayInfo.color || (isActive ? '#22c55e' : '#3b82f6');
                    spoolType = escapeHtml(trayInfo.type);
                    spoolName = trayInfo.sub_brands ? `${spoolType} ${escapeHtml(trayInfo.sub_brands)}` : `Bambu ${spoolType}`;
                    if (trayInfo.remain !== undefined && trayInfo.remain >= 0) {
                        pct = trayInfo.remain;
                    }
                } else if (isActive && !isTrayEmpty) {
                    spoolColor = '#22c55e';
                    spoolName = 'Активна нитка';
                    spoolType = escapeHtml(p.filament_type || 'PLA');
                } else if (isTrayEmpty) {
                    spoolColor = '#334155';
                    spoolName = 'Порожній слот';
                    spoolType = 'Порожньо';
                    pct = 0;
                }

                return `
                    <div class="ams-slot-card ${isActive ? 'active-slot' : ''} ${isTrayEmpty ? 'empty-slot' : ''}">
                        <div class="slot-tag d-flex justify-content-between align-items-center mb-1">
                            <span><b>${slotLabels[k]}</b> ${isActive ? '⚡' : ''}</span>
                            <div class="d-flex gap-1">
                                <button class="btn btn-xs btn-outline btn-edit-slot-grams" data-printer="${p.id}" data-slot="${k}" title="Встановити залишок (г)">
                                    <i class="fa-solid fa-pencil"></i>
                                </button>
                                ${assignedSpool ? `
                                <button class="btn btn-xs btn-outline-danger btn-unassign-slot-spool" data-printer="${p.id}" data-slot="${k}" title="Зняти котушку">
                                    <i class="fa-solid fa-xmark"></i>
                                </button>` : ''}
                            </div>
                        </div>
                        <div class="d-flex align-items-center gap-2 mb-1" style="min-width:0;">
                            <div class="spool-color-dot" style="background-color:${spoolColor}; width:14px; height:14px; border-radius:50%; border:1px solid rgba(255,255,255,0.4); flex-shrink:0;"></div>
                            <div style="font-size:11px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:1; min-width:0;">
                                <strong>${spoolName}</strong> <small class="text-muted">(${spoolType})</small>
                            </div>
                        </div>
                        <div class="d-flex align-items-center justify-content-between" style="font-size:11px;">
                            <span>${grams}g</span>
                            <span class="text-muted">${pct}%</span>
                        </div>
                        <div class="progress-bar-wrap sm mt-1">
                            <div class="progress-bar ${pct < 15 ? 'red' : 'green'}" style="width: ${pct}%;"></div>
                        </div>
                    </div>`;
            }).join("");

            amsSlotsContainer.querySelectorAll(".btn-edit-slot-grams").forEach(btn => {
                btn.addEventListener("click", () => {
                    const sId = btn.getAttribute("data-slot");
                    const curG = (p.ams_slots || {})[sId] !== undefined ? p.ams_slots[sId] : 1000;
                    const val = prompt(`Введіть новий залишок ваги (в грамах) для слоту ${slotLabels[sId]}:`, curG);
                    if (val !== null && val.trim() !== "") {
                        try {
                            const parsed = evalMathSimple(val.trim());
                            if (!isNaN(parsed) && parsed >= 0) {
                                sendPrinterAction({ action: "set_slot_grams", slot_id: sId, grams: parsed });
                            } else {
                                alert("Некоректне число!");
                            }
                        } catch (e) {
                            alert("Помилка математичного виразу!");
                        }
                    }
                });
            });

            amsSlotsContainer.querySelectorAll(".btn-unassign-slot-spool").forEach(btn => {
                btn.addEventListener("click", () => {
                    const sId = btn.getAttribute("data-slot");
                    if (confirm("Зняти котушку зі слоту?")) {
                        sendPrinterAction({ action: "unassign_spool", slot_id: sId });
                    }
                });
            });
        }

        // Detailed Maintenance Items Grid
        const maintListContainer = document.getElementById("modal-maint-list");
        if (maintListContainer) {
            const maintItems = p.maintenance_items || {
                "rails": { "key": "rails", "name": "Змащення валів & направляючих", "counter_hours": p.maintenance_hours_counter || 0.0, "interval_hours": p.maintenance_interval_hours || 100.0 }
            };

            maintListContainer.innerHTML = Object.values(maintItems).map(item => {
                const cHrs = (item.counter_hours || 0.0).toFixed(1);
                const iHrs = (item.interval_hours || 100.0).toFixed(0);
                const pct = Math.min(100, Math.round(((item.counter_hours || 0.0) / (item.interval_hours || 100.0)) * 100));
                const isOverdue = (item.counter_hours || 0.0) >= (item.interval_hours || 100.0);

                return `
                    <div class="maint-item-card ${isOverdue ? 'overdue' : ''}">
                        <div class="maint-item-header">
                            <span class="maint-item-title">${item.name} ${isOverdue ? '⚠️' : ''}</span>
                            <div class="maint-item-inputs">
                                <small style="font-size:11px; color:#94a3b8;">${cHrs} /</small>
                                <input type="number" class="maint-input-interval" data-key="${item.key}" value="${iHrs}" step="10" min="1" title="Натисніть Enter або клацніть поза полем для збереження годин">
                                <small style="font-size:11px; color:#94a3b8;">год</small>
                                <button class="btn btn-xs btn-outline-warning btn-reset-maint-item" data-key="${item.key}" style="margin-left:4px;" title="Скинути лічильник">
                                    <i class="fa-solid fa-rotate"></i>
                                </button>
                            </div>
                        </div>
                        <div class="progress-bar-wrap sm">
                            <div class="progress-bar ${isOverdue ? 'red' : 'amber'}" style="width: ${pct}%;"></div>
                        </div>
                    </div>`;
            }).join("");

            // Add Event Listeners for Resetting & Interval Input
            maintListContainer.querySelectorAll(".btn-reset-maint-item").forEach(btn => {
                btn.addEventListener("click", () => {
                    const k = btn.getAttribute("data-key");
                    sendPrinterAction({ action: "reset_maint", item_key: k });
                });
            });

            maintListContainer.querySelectorAll(".maint-input-interval").forEach(input => {
                input.addEventListener("change", () => {
                    const k = input.getAttribute("data-key");
                    const val = parseFloat(input.value);
                    if (val > 0) {
                        sendPrinterAction({ action: "set_maint_interval", item_key: k, interval_hours: val });
                    }
                });
            });
        }
    }

    let autoCamInterval = null;
    const autoCamToggle = document.getElementById("auto-cam-toggle");

    function loadCameraSnapshot(pId) {
        cameraImg.style.display = "block";
        cameraImg.nextElementSibling.style.display = "none";
        const initDataParam = tg?.initData ? "&initData=" + encodeURIComponent(tg.initData) : "";
        cameraImg.src = `/api/printers/${pId}/snapshot?t=${Date.now()}${initDataParam}`;
    }

    if (autoCamToggle) {
        autoCamToggle.addEventListener("change", () => {
            if (autoCamToggle.checked) {
                if (selectedPrinterId) loadCameraSnapshot(selectedPrinterId);
                if (autoCamInterval) clearInterval(autoCamInterval);
                autoCamInterval = setInterval(() => {
                    if (selectedPrinterId && printerModal.classList.contains("active") && autoCamToggle.checked) {
                        loadCameraSnapshot(selectedPrinterId);
                    } else {
                        if (autoCamInterval) clearInterval(autoCamInterval);
                        autoCamInterval = null;
                    }
                }, 5000);
            } else {
                if (autoCamInterval) clearInterval(autoCamInterval);
                autoCamInterval = null;
            }
        });
    }

    closeModalBtn.addEventListener("click", () => {
        triggerHaptic("light");
        printerModal.classList.remove("active");
        selectedPrinterId = null;
        if (autoCamInterval) clearInterval(autoCamInterval);
        autoCamInterval = null;
        if (autoCamToggle) autoCamToggle.checked = false;
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

    const btnNotify = document.getElementById("btn-action-notify");
    const btnCalibrate = document.getElementById("btn-action-calibrate");

    if (btnPause) btnPause.addEventListener("click", () => sendPrinterAction({ action: "pause" }));
    if (btnResume) btnResume.addEventListener("click", () => sendPrinterAction({ action: "resume" }));
    if (btnStop) btnStop.addEventListener("click", () => {
        if (confirm("Ви дійсно хочете ЗУПИНИТИ друк?")) {
            sendPrinterAction({ action: "stop" });
        }
    });
    if (btnLight) btnLight.addEventListener("click", () => sendPrinterAction({ action: "light_toggle" }));
    if (btnNotify) btnNotify.addEventListener("click", () => sendPrinterAction({ action: "toggle_notify" }));
    if (btnCalibrate) btnCalibrate.addEventListener("click", () => {
        const p = printersData.find(x => x.id === selectedPrinterId);
        if (p && p.state === "RUNNING") {
            alert("⚠️ Неможливо запустити калібрування під час друку!");
            return;
        }
        if (confirm("Запустити повне автоматичне калібрування принтера (G32 / Vibrations & Bed Leveling)?")) {
            sendPrinterAction({ action: "calibrate" });
        }
    });
    if (btnResetMaint) btnResetMaint.addEventListener("click", () => {
        if (confirm("Скинути лічильник ТО?")) {
            sendPrinterAction({ action: "reset_maint" });
        }
    });

    speedBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            const level = parseInt(btn.getAttribute("data-level"));
            sendPrinterAction({ action: "set_speed", level: level });
        });
    });

    if (addPrinterBtn) {
        addPrinterBtn.addEventListener("click", () => {
            triggerHaptic("medium");
            addPrinterModal.classList.add("active");
        });
    }

    if (closeAddPrinterModalBtn) {
        closeAddPrinterModalBtn.addEventListener("click", () => {
            triggerHaptic("light");
            addPrinterModal.classList.remove("active");
        });
    }

    if (savePrinterSubmitBtn) {
        savePrinterSubmitBtn.addEventListener("click", async () => {
            const name = document.getElementById("new-p-name").value.trim();
            const ip = document.getElementById("new-p-ip").value.trim();
            const accessCode = document.getElementById("new-p-code").value.trim();
            const serialNumber = document.getElementById("new-p-sn").value.trim();

            if (!name || !ip || !accessCode || !serialNumber) {
                alert("Заповніть всі поля!");
                return;
            }

            triggerHaptic("medium");
            savePrinterSubmitBtn.disabled = true;
            savePrinterSubmitBtn.textContent = "Збереження...";

            try {
                const res = await fetch("/api/printers", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ name, ip, accessCode, serialNumber })
                });
                const data = await res.json();
                if (data.status === "ok") {
                    addPrinterModal.classList.remove("active");
                    document.getElementById("add-printer-form").reset();
                    fetchPrinters();
                } else {
                    alert("Помилка додавання принтера: " + (data.error || "Невідомо"));
                }
            } catch (e) {
                console.error("Add printer error:", e);
                alert("Помилка з'єднання при додаванні принтера.");
            } finally {
                savePrinterSubmitBtn.disabled = false;
                savePrinterSubmitBtn.textContent = "Зберегти принтер";
            }
        });
    }

    if (btnActionDelete) {
        btnActionDelete.addEventListener("click", async () => {
            if (!selectedPrinterId) return;
            if (confirm("Ви дійсно хочете ВИДАЛИТИ цей принтер з системи?")) {
                triggerHaptic("medium");
                try {
                    const res = await fetch(`/api/printers/${selectedPrinterId}`, {
                        method: "DELETE"
                    });
                    const data = await res.json();
                    if (data.status === "ok") {
                        printerModal.classList.remove("active");
                        selectedPrinterId = null;
                        fetchPrinters();
                    } else {
                        alert("Помилка видалення принтера: " + (data.error || "Невідомо"));
                    }
                } catch (e) {
                    console.error("Delete printer error:", e);
                    alert("Помилка при видаленні принтера.");
                }
            }
        });
    }

    let editingSpoolId = null;
    let selectedSpoolForAssign = null;

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
                container.innerHTML = `<p class="text-muted text-center p-3">Немає активних принтерів</p>`;
            } else {
                const spoolsList = Object.values(spools || {});

                container.innerHTML = printers.map(p => {
                    const hasAms = Boolean(p.has_ams);
                    const activeKey = String(p.active_slot_key || "255");
                    const slots = p.ams_slots || {};
                    const slotKeys = hasAms ? ["0", "1", "2", "3", "255"] : ["255"];
                    const slotLabels = { "0": "A1", "1": "A2", "2": "A3", "3": "A4", "255": hasAms ? "VT (Зовнішній)" : "Зовнішній котушкотримач" };
                    const amsBadge = hasAms 
                        ? `<span class="badge badge-success" style="font-size:10px; font-weight:500;"><i class="fa-solid fa-layer-group"></i> AMS Підключено</span>`
                        : `<span class="badge badge-secondary" style="font-size:10px; font-weight:500;"><i class="fa-solid fa-spool"></i> Пряма подача (Без AMS)</span>`;

                    return `
                        <div class="ams-printer-block glass-card p-3 mb-3">
                            <div class="ams-printer-title d-flex justify-content-between align-items-center mb-2">
                                <div class="d-flex align-items-center gap-2">
                                    <strong><i class="fa-solid fa-print color-blue"></i> ${escapeHtml(p.name)}</strong>
                                    ${amsBadge}
                                </div>
                                <small class="text-muted">Тип: <b>${escapeHtml(p.filament_type || 'PLA')}</b> • ${p.price_per_kg || 650} ₴/кг</small>
                            </div>
                            <div class="ams-slots-grid">
                                ${slotKeys.map(k => {
                                    const grams = slots[k] !== undefined ? slots[k] : 1000;
                                    const isActive = (k === activeKey);
                                    const assignedSpool = spoolsList.find(s => s.assigned_printer_id === p.id && String(s.assigned_slot_key) === k);
                                    const trayInfo = (p.ams_trays_info || {})[k] || {};
                                    const isTrayEmpty = trayInfo.empty === true;

                                    let spoolColor = '#64748b';
                                    let spoolName = 'Порожньо';
                                    let spoolType = '—';
                                    let pct = Math.min(100, Math.max(0, Math.round((grams / 1000) * 100)));

                                    if (assignedSpool) {
                                        spoolColor = assignedSpool.color || '#3b82f6';
                                        spoolName = escapeHtml(assignedSpool.name);
                                        spoolType = escapeHtml(assignedSpool.type);
                                    } else if (!isTrayEmpty && (trayInfo.type || trayInfo.color)) {
                                        spoolColor = trayInfo.color || (isActive ? '#22c55e' : '#3b82f6');
                                        spoolType = escapeHtml(trayInfo.type);
                                        spoolName = trayInfo.sub_brands ? `${spoolType} ${escapeHtml(trayInfo.sub_brands)}` : `Bambu ${spoolType}`;
                                        if (trayInfo.remain !== undefined && trayInfo.remain >= 0) {
                                            pct = trayInfo.remain;
                                        }
                                    } else if (isActive && !isTrayEmpty) {
                                        spoolColor = '#22c55e';
                                        spoolName = 'Активна нитка';
                                        spoolType = escapeHtml(p.filament_type || 'PLA');
                                    } else if (isTrayEmpty) {
                                        spoolColor = '#334155';
                                        spoolName = 'Порожній слот';
                                        spoolType = 'Порожньо';
                                        pct = 0;
                                    }

                                    return `
                                        <div class="ams-slot-card ${isActive ? 'active-slot' : ''} ${isTrayEmpty ? 'empty-slot' : ''}">
                                            <div class="slot-tag d-flex justify-content-between align-items-center mb-1">
                                                <span><b>${slotLabels[k]}</b> ${isActive ? '⚡' : ''}</span>
                                                <div class="d-flex gap-1">
                                                    <button class="btn btn-xs btn-outline btn-edit-slot-grams" data-printer="${p.id}" data-slot="${k}" title="Встановити залишок (г)">
                                                        <i class="fa-solid fa-pencil"></i>
                                                    </button>
                                                    ${assignedSpool ? `
                                                    <button class="btn btn-xs btn-outline-danger btn-unassign-slot-spool" data-printer="${p.id}" data-slot="${k}" title="Зняти котушку">
                                                        <i class="fa-solid fa-xmark"></i>
                                                     </button>` : ''}
                                                </div>
                                            </div>
                                            <div class="d-flex align-items-center gap-2 mb-1" style="min-width:0;">
                                                <div class="spool-color-dot" style="background-color:${spoolColor}; width:14px; height:14px; border-radius:50%; border:1px solid rgba(255,255,255,0.4); flex-shrink:0;"></div>
                                                <div style="font-size:11px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:1; min-width:0;">
                                                    <strong>${spoolName}</strong> <small class="text-muted">(${spoolType})</small>
                                                </div>
                                            </div>
                                            <div class="d-flex align-items-center justify-content-between" style="font-size:11px;">
                                                <span>${grams}g</span>
                                                <span class="text-muted">${pct}%</span>
                                            </div>
                                            <div class="progress-bar-wrap sm mt-1">
                                                <div class="progress-bar ${pct < 15 ? 'red' : 'green'}" style="width: ${pct}%;"></div>
                                            </div>
                                        </div>`;
                                }).join("")}
                            </div>
                        </div>`;
                }).join("");

                // Edit slot grams
                document.querySelectorAll(".btn-edit-slot-grams").forEach(btn => {
                    btn.addEventListener("click", async (e) => {
                        e.stopPropagation();
                        const pId = btn.getAttribute("data-printer");
                        const slotId = btn.getAttribute("data-slot");
                        const inputVal = prompt("Введіть новий залишок у грамах (наприклад: 850 або 1000 - 150):");
                        if (inputVal !== null && inputVal.trim() !== "") {
                            try {
                                let grams = eval(inputVal.replace(/[^0-9\+\-\*\/\.\(\)]/g, ''));
                                grams = Math.max(0, roundToTwo(parseFloat(grams) || 0));
                                await fetch(`/api/printers/${pId}/control`, {
                                    method: "POST",
                                    headers: { "Content-Type": "application/json" },
                                    body: JSON.stringify({ action: "set_filament", grams, slot_id: slotId })
                                });
                                loadMaterials();
                            } catch (err) {
                                alert("Некоректне значення ваги.");
                            }
                        }
                    });
                });

                // Unassign spool from slot
                document.querySelectorAll(".btn-unassign-slot-spool").forEach(btn => {
                    btn.addEventListener("click", async (e) => {
                        e.stopPropagation();
                        const pId = btn.getAttribute("data-printer");
                        const slotId = btn.getAttribute("data-slot");
                        if (confirm("Зняти котушку з цього слоту?")) {
                            await fetch(`/api/printers/${pId}/control`, {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({ action: "unassign_spool", slot_id: slotId })
                            });
                            loadMaterials();
                        }
                    });
                });
            }

            // Render Spool Inventory
            const spoolsList = document.getElementById("spools-list");
            const spoolsArray = Object.values(spools || {});
            if (spoolsArray.length === 0) {
                spoolsList.innerHTML = `<p class="text-muted text-center p-3">Склад порожній. Натисніть "+ Нова котушка", щоб додати.</p>`;
            } else {
                spoolsList.innerHTML = spoolsArray.map(s => `
                    <div class="spool-item glass-card p-3 mb-2 d-flex justify-content-between align-items-center">
                        <div class="spool-left d-flex align-items-center gap-2">
                            <div class="spool-color-circle" style="background-color: ${s.color || '#3b82f6'}; width: 24px; height: 24px; border-radius: 50%; border: 1px solid rgba(255,255,255,0.3);"></div>
                            <div class="spool-details">
                                <h4 style="margin:0; font-size:14px;">${escapeHtml(s.name)}</h4>
                                <small class="text-muted">${escapeHtml(s.type || 'PLA')} • ${s.price_per_kg || s.price_uah || 650} ₴/кг • ${s.remaining_grams || 1000}g</small>
                            </div>
                        </div>
                        <div class="spool-right d-flex align-items-center gap-2">
                            <button class="btn btn-xs btn-primary btn-assign-spool" data-id="${s.id}" title="Встановити на принтер">
                                <i class="fa-solid fa-truck-ramp-box"></i> На принтер
                            </button>
                            <button class="btn btn-xs btn-outline btn-edit-spool" data-id="${s.id}" title="Редагувати">
                                <i class="fa-solid fa-pen-to-square"></i>
                            </button>
                            <button class="btn btn-xs btn-outline-danger btn-delete-spool" data-id="${s.id}" title="Видалити">
                                <i class="fa-solid fa-trash"></i>
                            </button>
                        </div>
                    </div>`).join("");

                // Assign spool to printer
                document.querySelectorAll(".btn-assign-spool").forEach(b => {
                    b.addEventListener("click", () => {
                        const id = b.getAttribute("data-id");
                        selectedSpoolForAssign = spools[id];
                        openAssignSpoolModal(printers);
                    });
                });

                // Edit spool
                document.querySelectorAll(".btn-edit-spool").forEach(b => {
                    b.addEventListener("click", () => {
                        const id = b.getAttribute("data-id");
                        const s = spools[id];
                        if (s) {
                            editingSpoolId = s.id;
                            const titleEl = document.getElementById("spool-modal-title");
                            if (titleEl) titleEl.textContent = "✏️ Редагувати котушку";
                            document.getElementById("spool-name").value = s.name || "";
                            document.getElementById("spool-type").value = s.type || "PLA";
                            document.getElementById("spool-grams").value = s.remaining_grams || 1000;
                            document.getElementById("spool-price").value = s.price_per_kg || s.price_uah || 650;
                            const colEl = document.getElementById("spool-color");
                            if (colEl) colEl.value = s.color || "#3b82f6";
                            if (spoolModal) spoolModal.classList.add("active");
                        }
                    });
                });

                // Delete spool
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

    function roundToTwo(num) {
        return Math.round((num + Number.EPSILON) * 100) / 100;
    }

    function openAssignSpoolModal(printers) {
        const modal = document.getElementById("assign-spool-modal");
        const selectPrinter = document.getElementById("assign-printer-select");
        if (!modal || !selectPrinter) return;

        selectPrinter.innerHTML = printers.map(p => `<option value="${p.id}">${escapeHtml(p.name)} (${p.ip})</option>`).join("");
        modal.classList.add("active");
    }

    const confirmAssignBtn = document.getElementById("confirm-assign-spool-btn");
    if (confirmAssignBtn) {
        confirmAssignBtn.addEventListener("click", async () => {
            if (!selectedSpoolForAssign) return;
            const printerId = document.getElementById("assign-printer-select").value;
            const slotId = document.getElementById("assign-slot-select").value;

            try {
                const res = await fetch(`/api/printers/${printerId}/control`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        action: "assign_spool",
                        spool_id: selectedSpoolForAssign.id,
                        slot_id: slotId
                    })
                });
                const result = await res.json();
                if (result.status === "ok") {
                    document.getElementById("assign-spool-modal").classList.remove("active");
                    loadMaterials();
                    fetchPrinters();
                } else {
                    alert("Помилка встановлення: " + (result.error || "Невідомо"));
                }
            } catch (err) {
                console.error("Assign spool error:", err);
                alert("Помилка з'єднання при встановленні котушки.");
            }
        });
    }

    // Add / Edit Spool Form Modal
    if (addSpoolBtn) {
        addSpoolBtn.addEventListener("click", () => {
            editingSpoolId = null;
            const titleEl = document.getElementById("spool-modal-title");
            if (titleEl) titleEl.textContent = "➕ Додати котушку";
            document.getElementById("spool-name").value = "";
            document.getElementById("spool-type").value = "PLA";
            document.getElementById("spool-grams").value = "1000";
            document.getElementById("spool-price").value = "650";
            const colEl = document.getElementById("spool-color");
            if (colEl) colEl.value = "#3b82f6";

            triggerHaptic("medium");
            if (spoolModal) spoolModal.classList.add("active");
        });
    }

    if (closeSpoolModalBtn) {
        closeSpoolModalBtn.addEventListener("click", () => {
            if (spoolModal) spoolModal.classList.remove("active");
        });
    }

    if (saveSpoolSubmitBtn) {
        saveSpoolSubmitBtn.addEventListener("click", async () => {
            const name = document.getElementById("spool-name").value.trim();
            const type = document.getElementById("spool-type").value;
            const grams = parseFloat(document.getElementById("spool-grams").value) || 1000;
            const price = parseFloat(document.getElementById("spool-price").value) || 650;
            const colEl = document.getElementById("spool-color");
            const color = colEl ? colEl.value : "#3b82f6";

            if (!name) { alert("Введіть назву котушки!"); return; }

            const payload = {
                id: editingSpoolId || undefined,
                name,
                type,
                remaining_grams: grams,
                price_per_kg: price,
                color
            };

            try {
                await fetch("/api/spools", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                if (spoolModal) spoolModal.classList.remove("active");
                loadMaterials();
            } catch (e) {
                console.error("Failed saving spool:", e);
            }
        });
    }

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

    document.getElementById("calc-preset-select")?.addEventListener("change", recalculateCommercial);
    document.getElementById("calc-weight-g")?.addEventListener("input", recalculateCommercial);
    document.getElementById("calc-time-mins")?.addEventListener("input", recalculateCommercial);

    // Preset Modal handlers
    const presetModal = document.getElementById("preset-modal");
    document.getElementById("add-preset-btn")?.addEventListener("click", () => {
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
        if (presetModal) presetModal.classList.add("active");
    });
    document.getElementById("close-preset-modal")?.addEventListener("click", () => {
        if (presetModal) presetModal.classList.remove("active");
    });
    document.getElementById("save-preset-submit")?.addEventListener("click", async () => {
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

    document.getElementById("save-settings-btn")?.addEventListener("click", async () => {
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

    // Initial Load & Fail-Safe Polling Loop (Runs always every 3s)
    fetchPrinters();
    pollInterval = setInterval(fetchPrinters, 3000);
    initSSEStream();
});


