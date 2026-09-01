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

function getBambuModelCode(nameStr) {
    if (!nameStr) return "UNKNOWN";
    const s = String(nameStr).toLowerCase().replace(/[\-_]/g, " ").trim();

    if (s.includes("a1 mini") || s.includes("a1mini") || s.includes("a1m") || s.includes("@bbl a1m") || s.includes("n2s") || s.includes("n2")) {
        return "@BBL A1M";
    }
    if (s.includes("a1") || s.includes("@bbl a1") || s.includes("n1")) {
        return "@BBL A1";
    }
    if (s.includes("a2l") || s.includes("@bbl a2l")) {
        return "@BBL A2L";
    }
    if (s.includes("h2d pro") || s.includes("h2dpro") || s.includes("h2dp") || s.includes("@bbl h2dp")) {
        return "@BBL H2DP";
    }
    if (s.includes("h2c") || s.includes("@bbl h2c")) {
        return "@BBL H2C";
    }
    if (s.includes("h2d") || s.includes("@bbl h2d")) {
        return "@BBL H2D";
    }
    if (s.includes("h2s") || s.includes("@bbl h2s")) {
        return "@BBL H2S";
    }
    if (s.includes("p1p") || s.includes("@bbl p1p")) {
        return "@BBL P1P";
    }
    if (s.includes("p2s") || s.includes("@bbl p2s")) {
        return "@BBL P2S";
    }
    if (s.includes("x2d") || s.includes("@bbl x2d")) {
        return "@BBL X2D";
    }
    if (s.includes("p1s") || s.includes("x1 carbon") || s.includes("x1c") || s.includes("x1e") || s.includes("x1") || s.includes("@bbl x1c") || s.includes("c12") || s.includes("c10")) {
        return "@BBL X1C";
    }

    return "UNKNOWN";
}

function normalizeFilamentName(rawName) {
    if (!rawName || String(rawName).trim().toLowerCase() === "unknown" || String(rawName).trim().toLowerCase() === "невизначено" || !String(rawName).trim()) {
        return "";
    }
    const s = String(rawName).trim().toUpperCase();
    const hardcodedTypes = [
        "ASA-AERO", "PETG-CF", "PLA-AERO", "PPA-CF", "PPA-GF", "TPU-AMS", "ABS-GF", "ASA-CF",
        "PA6-CF", "PLA-CF", "PET-CF", "PA-GF", "PP-CF", "PP-GF", "PE-CF", "PCTG", "BVOH",
        "CoPE", "HIPS", "PA6", "PETG", "PLA", "ABS", "TPU", "ASA", "PVA", "SBS", "EVA",
        "PHA", "PP", "PE", "PC", "PA"
    ];
    for (const t of hardcodedTypes) {
        const regex = new RegExp("(?:^|[^A-Z0-9\\-])" + t + "(?:$|[^A-Z0-9\\-])", "i");
        if (regex.test(s)) {
            return t;
        }
    }
    return s;
}

window.openAddPartModal = function(part = null) {
    const modal = document.getElementById("add-part-modal");
    const titleEl = document.getElementById("part-modal-title");
    const editIdInput = document.getElementById("edit-part-id");
    const nameInput = document.getElementById("part-name-input");
    const imageInput = document.getElementById("part-image-input");
    const countInput = document.getElementById("part-count-input");
    const threeMfInput = document.getElementById("part-3mf-input");
    const threeMfFileInput = document.getElementById("part-3mf-file-input");
    const detectedModelEl = document.getElementById("part-detected-model");

    const partImageFileInput = document.getElementById("part-image-file-input");
    const previewWrap = document.getElementById("part-image-preview-wrap");
    const previewImg = document.getElementById("part-image-preview");

    if (!modal) return;

    if (threeMfFileInput) threeMfFileInput.value = "";
    if (partImageFileInput) partImageFileInput.value = "";

    if (part && typeof part === "object") {
        if (titleEl) titleEl.textContent = "✏️ Редагувати деталь";
        if (editIdInput) editIdInput.value = part.id || "";
        if (nameInput) nameInput.value = part.name || "";
        if (imageInput) imageInput.value = part.image || "";
        if (countInput) countInput.value = part.count || part.quantity || 1;
        if (threeMfInput) threeMfInput.value = part.three_mf || "";

        if (part.image && previewWrap && previewImg) {
            previewImg.src = part.image;
            previewWrap.style.display = "block";
        } else if (previewWrap) {
            previewWrap.style.display = "none";
        }

        if (detectedModelEl) {
            if (part.printer_model && part.printer_model !== 'Unknown') {
                detectedModelEl.textContent = `🖨️ Визначена модель принтера: ${part.printer_model}`;
                detectedModelEl.style.display = "block";
            } else {
                detectedModelEl.style.display = "none";
            }
        }
    } else {
        if (titleEl) titleEl.textContent = "➕ Нова деталь";
        if (editIdInput) editIdInput.value = "";
        if (nameInput) nameInput.value = "";
        if (imageInput) imageInput.value = "";
        if (countInput) countInput.value = 1;
        if (threeMfInput) threeMfInput.value = "";
        if (previewWrap) previewWrap.style.display = "none";
        if (detectedModelEl) detectedModelEl.style.display = "none";
    }

    if (window.Telegram?.WebApp?.HapticFeedback) {
        try { window.Telegram.WebApp.HapticFeedback.impactOccurred("light"); } catch(e){}
    }
    modal.classList.add("active");
};

window.openAddSpoolModal = function(spool = null) {
    const modal = document.getElementById("spool-modal");
    const titleEl = document.getElementById("spool-modal-title");
    const nameEl = document.getElementById("spool-name");
    const typeEl = document.getElementById("spool-type");
    const gramsEl = document.getElementById("spool-grams");
    const qtyEl = document.getElementById("spool-quantity");
    const priceEl = document.getElementById("spool-price");
    const colEl = document.getElementById("spool-color");

    if (!modal) return;

    if (spool && typeof spool === "object") {
        window._editingSpoolId = spool.id || null;
        if (titleEl) titleEl.textContent = "✏️ Редагувати котушку";
        if (nameEl) nameEl.value = spool.name || "";
        if (typeEl) typeEl.value = spool.type || "PLA";
        if (gramsEl) gramsEl.value = spool.remaining_grams !== undefined ? spool.remaining_grams : 1000;
        if (qtyEl) qtyEl.value = spool.quantity || 1;
        if (priceEl) priceEl.value = spool.price_per_kg || spool.price_uah || 650;
        if (colEl) colEl.value = spool.color || "#3b82f6";
    } else {
        window._editingSpoolId = null;
        if (titleEl) titleEl.textContent = "➕ Додати котушку";
        if (nameEl) nameEl.value = "";
        if (typeEl) typeEl.value = "PLA";
        if (gramsEl) gramsEl.value = 1000;
        if (qtyEl) qtyEl.value = 1;
        if (priceEl) priceEl.value = 650;
        if (colEl) colEl.value = "#3b82f6";
    }

    if (window.Telegram?.WebApp?.HapticFeedback) {
        try { window.Telegram.WebApp.HapticFeedback.impactOccurred("light"); } catch(e){}
    }
    modal.classList.add("active");
};

window.closeSpoolModal = function() {
    const modal = document.getElementById("spool-modal");
    if (modal) modal.classList.remove("active");
};

window.submitSaveSpool = async function(e) {
    if (e) {
        e.preventDefault();
        e.stopPropagation();
    }
    const nameEl = document.getElementById("spool-name");
    const name = nameEl ? nameEl.value.trim() : "";
    const type = document.getElementById("spool-type")?.value || "PLA";
    const grams = parseFloat(document.getElementById("spool-grams")?.value) || 1000;
    const qtyEl = document.getElementById("spool-quantity");
    const quantity = qtyEl ? (parseInt(qtyEl.value, 10) || 1) : 1;
    const price = parseFloat(document.getElementById("spool-price")?.value) || 650;
    const colEl = document.getElementById("spool-color");
    const color = colEl ? colEl.value : "#3b82f6";

    if (!name) {
        alert("⚠️ Будь ласка, введіть назву котушки!");
        return;
    }

    const payload = {
        id: window._editingSpoolId || undefined,
        name,
        type,
        remaining_grams: grams,
        quantity: Math.max(1, quantity),
        price_per_kg: price,
        color
    };

    const submitBtn = document.getElementById("save-spool-submit");
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Збереження...";
    }

    try {
        const initData = window.Telegram?.WebApp?.initData || "";
        const sessionToken = localStorage.getItem("web_session_token") || "";
        const headers = { "Content-Type": "application/json" };
        if (initData) headers["X-Telegram-Init-Data"] = initData;
        if (sessionToken) headers["Authorization"] = `Bearer ${sessionToken}`;

        const res = await fetch("/api/spools", {
            method: "POST",
            headers,
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            alert("⚠️ Помилка збереження котушки: " + (errData.error || res.statusText));
            return;
        }

        window.closeSpoolModal();
        if (window.Telegram?.WebApp?.HapticFeedback) {
            try { window.Telegram.WebApp.HapticFeedback.notificationOccurred("success"); } catch(e){}
        }
        if (typeof window.loadMaterialsGlobal === "function") {
            await window.loadMaterialsGlobal();
        }
    } catch (err) {
        console.error("Failed saving spool:", err);
        alert("⚠️ Помилка зв'язку при збереженні котушки.");
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = "Зберегти котушку";
        }
    }
};

function safeMathEval(expr) {
    if (!expr) return 0;
    const clean = String(expr).replace(/[^0-9\+\-\*\/\.\(\)\s]/g, '').trim();
    if (!clean) return 0;
    const tokens = clean.match(/\d+(?:\.\d+)?|[+\-*/()]/g);
    if (!tokens) return 0;

    let idx = 0;
    function parsePrimary() {
        if (idx >= tokens.length) return 0;
        let tok = tokens[idx++];
        if (tok === '(') {
            let val = parseAddSub();
            if (tokens[idx] === ')') idx++;
            return val;
        }
        if (tok === '-') return -parsePrimary();
        if (tok === '+') return parsePrimary();
        return parseFloat(tok) || 0;
    }

    function parseMulDiv() {
        let left = parsePrimary();
        while (idx < tokens.length && (tokens[idx] === '*' || tokens[idx] === '/')) {
            let op = tokens[idx++];
            let right = parsePrimary();
            if (op === '*') left *= right;
            else if (op === '/') left = right !== 0 ? left / right : 0;
        }
        return left;
    }

    function parseAddSub() {
        let left = parseMulDiv();
        while (idx < tokens.length && (tokens[idx] === '+' || tokens[idx] === '-')) {
            let op = tokens[idx++];
            let right = parseMulDiv();
            if (op === '+') left += right;
            else if (op === '-') left -= right;
        }
        return left;
    }

    try { return parseAddSub(); } catch (e) { return 0; }
}

document.addEventListener("DOMContentLoaded", () => {

    // 1. Initialize Telegram WebApp SDK
    const tg = window.Telegram?.WebApp;
    if (tg) {
        tg.ready();
        tg.expand();
        tg.enableClosingConfirmation();
    }

    function triggerHaptic(type = "medium") {
        if (window.Telegram?.WebApp?.HapticFeedback) {
            try { window.Telegram.WebApp.HapticFeedback.impactOccurred(type); } catch(e){}
        }
    }
    window.triggerHaptic = triggerHaptic;

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



    // Fleet search and filter pill listeners
    const searchInputEl = document.getElementById("printer-search-input");
    const clearSearchBtn = document.getElementById("clear-search-btn");

    if (searchInputEl) {
        searchInputEl.addEventListener("input", () => {
            if (clearSearchBtn) {
                clearSearchBtn.style.display = searchInputEl.value ? "flex" : "none";
            }
            applyPrinterFilters();
        });

        searchInputEl.addEventListener("focus", () => {
            if (tg?.expand) tg.expand();
        });
    }

    if (clearSearchBtn) {
        clearSearchBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            if (searchInputEl) {
                searchInputEl.value = "";
                clearSearchBtn.style.display = "none";
                searchInputEl.focus();
                applyPrinterFilters();
            }
        });
    }

    const pillBtns = document.querySelectorAll(".filter-pills .pill-btn");
    pillBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            triggerHaptic("light");
            pillBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            applyPrinterFilters();
        });
    });

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
            if (targetTab === "tab-parts") loadParts();
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
                        if (data.some(p => String(p.state || "").toUpperCase() === "FINISH")) {
                            loadHistory();
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

            if (!window.latestSpools) {
                try {
                    const sRes = await fetch("/api/spools");
                    if (sRes.ok) window.latestSpools = await sRes.json();
                } catch (e) {}
            }

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

    function formatRemainingTime(mins) {
        if (!mins || mins <= 0) return "";
        const h = Math.floor(mins / 60);
        const m = mins % 60;
        if (h > 0) return `${h}г ${m}хв`;
        return `${m} хв`;
    }

    function cleanSubtaskName(subtask, isPrinting) {
        if (!subtask) return isPrinting ? "Друк..." : "Вільний";
        let clean = String(subtask).replace(/^Metadata\//i, "");
        clean = clean.replace(/\.(gcode|3mf)+$/gi, "").replace(/\.(gcode|3mf)+$/gi, "").trim();
        return clean || (isPrinting ? "Друк..." : "Вільний");
    }

    function getPrinterStatusInfo(rawState) {
        const st = String(rawState || "IDLE").toUpperCase();
        if (st === "RUNNING" || st === "PREPARE" || st === "PRINTING" || st === "CHANGING_FILAMENT" || st === "SLICING" || st === "BUILDING" || st === "BUSY") {
            return { code: "RUNNING", label: "🟢 Друкує", badgeClass: "status-RUNNING" };
        }
        if (st === "PAUSE" || st === "PAUSED") {
            return { code: "PAUSE", label: "⏸️ Пауза", badgeClass: "status-PAUSE" };
        }
        return { code: "IDLE", label: "⚪ Готовий", badgeClass: "status-IDLE" };
    }

    function updateFilterBadges(printers) {
        if (!printers) return;
        const total = printers.length;
        let running = 0;
        let pause = 0;
        let idle = 0;

        printers.forEach(p => {
            const info = getPrinterStatusInfo(p.state);
            if (info.code === "RUNNING") running++;
            else if (info.code === "PAUSE") pause++;
            else idle++;
        });

        const cAll = document.getElementById("count-filter-all");
        const cRun = document.getElementById("count-filter-running");
        const cPause = document.getElementById("count-filter-pause");
        const cIdle = document.getElementById("count-filter-idle");

        if (cAll) cAll.textContent = total;
        if (cRun) cRun.textContent = running;
        if (cPause) cPause.textContent = pause;
        if (cIdle) cIdle.textContent = idle;
    }

    function applyPrinterFilters() {
        const searchInput = document.getElementById("printer-search-input");
        const rawQuery = (searchInput?.value || "").trim().toLowerCase();
        const activeBtn = document.querySelector(".filter-pills .pill-btn.active");
        const filterState = activeBtn?.dataset.filter || "all";

        document.querySelectorAll(".printer-card").forEach(card => {
            const name = (card.getAttribute("data-name") || "").toLowerCase();
            const state = (card.getAttribute("data-state") || "IDLE").toUpperCase();
            const statusInfo = getPrinterStatusInfo(state);

            const matchesQuery = !rawQuery || name.includes(rawQuery);
            let matchesFilter = true;
            if (filterState === "RUNNING") {
                matchesFilter = statusInfo.code === "RUNNING";
            } else if (filterState === "PAUSE") {
                matchesFilter = statusInfo.code === "PAUSE";
            } else if (filterState === "IDLE") {
                matchesFilter = statusInfo.code === "IDLE";
            }

            card.style.display = (matchesQuery && matchesFilter) ? "" : "none";
        });
    }

    function populatePrinterSettingsSelect(printers) {
        const sel = document.getElementById("printer-settings-select");
        if (!sel) return;
        const curVal = sel.value;
        const opts = `<option value="">-- Оберіть принтер --</option>` +
            (printers || []).map(p => `<option value="${p.id}">${escapeHtml(p.name || p.id)} (${p.ip || 'no IP'})</option>`).join("");
        if (sel.innerHTML !== opts) {
            sel.innerHTML = opts;
            if (curVal && (printers || []).some(p => p.id === curVal)) {
                sel.value = curVal;
            }
        }
    }

    function renderPrinters(printers) {
        updateFilterBadges(printers);
        populatePrinterSettingsSelect(printers);

        if (!printers || printers.length === 0) {
            printersGrid.innerHTML = `
                <div class="glass-card text-center p-4">
                    <i class="fa-solid fa-triangle-exclamation color-orange fa-2x mb-2"></i>
                    <p>Не знайдено жодного підключеного принтера Bambu Lab.</p>
                </div>`;
            activeCountEl.textContent = "0/0";
            return;
        }

        const runningCount = printers.filter(p => getPrinterStatusInfo(p.state).code === "RUNNING").length;
        const pauseCount = printers.filter(p => getPrinterStatusInfo(p.state).code === "PAUSE").length;

        let subDetail = [];
        if (runningCount > 0) subDetail.push(`друк: ${runningCount}`);
        if (pauseCount > 0) subDetail.push(`пауза: ${pauseCount}`);
        const subStr = subDetail.length > 0 ? ` (${subDetail.join(', ')})` : '';

        activeCountEl.textContent = `${printers.length}/${printers.length}${subStr}`;

        printersGrid.innerHTML = printers.map(p => {
            const rawSt = String(p.state || "IDLE").toUpperCase();
            const st = rawSt;
            const statusInfo = getPrinterStatusInfo(rawSt);
            const isPrinting = statusInfo.code === "RUNNING";
            let progress = p.progress_pct !== undefined ? p.progress_pct : 0;

            const modelName = cleanSubtaskName(p.subtask_name, isPrinting);
            let timeStr = formatRemainingTime(p.remaining_mins);
            if (statusInfo.code === "PAUSE") timeStr = "Пауза";
            else if (statusInfo.code === "IDLE") timeStr = "Вільний";
            else if (!timeStr && isPrinting) timeStr = "Підготовка...";

            const layerStr = (statusInfo.code === "IDLE" && p.current_layer === 0) ? "—" : `${p.current_layer}/${p.total_layers}`;

            const spoolsList = Object.values(window.latestSpools || {});
            const assignedSpools = spoolsList.filter(s => s.assigned_printer_id === p.id);
            const activeKey = String(p.active_slot_key || "255");
            const slotLabels = { "0": "A1", "1": "A2", "2": "A3", "3": "A4", "255": "VT" };
            const hasAms = Boolean(p.has_ams);

            let displaySlotKey = activeKey;
            let assignedSpool = assignedSpools.find(s => String(s.assigned_slot_key) === activeKey);

            if (!assignedSpool && assignedSpools.length > 0) {
                assignedSpool = assignedSpools[0];
                displaySlotKey = String(assignedSpool.assigned_slot_key !== undefined ? assignedSpool.assigned_slot_key : "255");
            } else if (!assignedSpool && hasAms && activeKey === "255") {
                const amsKeys = ["0", "1", "2", "3"];
                const firstNonEmptyKey = amsKeys.find(k => {
                    const g = p.ams_slots ? p.ams_slots[k] : 0;
                    const t = (p.ams_trays_info || {})[k] || {};
                    return (g > 0 || (t.type && !t.empty));
                });
                if (firstNonEmptyKey !== undefined) {
                    displaySlotKey = firstNonEmptyKey;
                }
            }

            const slotGrams = (p.ams_slots && p.ams_slots[displaySlotKey] !== undefined)
                ? p.ams_slots[displaySlotKey]
                : (assignedSpool ? assignedSpool.remaining_grams : (p.filament_grams_left !== undefined ? p.filament_grams_left : 1000));

            const slotTag = (hasAms && slotLabels[displaySlotKey]) ? `[${slotLabels[displaySlotKey]}] ` : "";

            let filamentDisplay = "";
            if (assignedSpool) {
                filamentDisplay = `${slotTag}${escapeHtml(assignedSpool.name)} (${slotGrams}g)`;
            } else if (p.ams_trays_info && p.ams_trays_info[displaySlotKey] && p.ams_trays_info[displaySlotKey].type) {
                const tInfo = p.ams_trays_info[displaySlotKey];
                const name = tInfo.sub_brands ? `Bambu ${tInfo.type} ${tInfo.sub_brands}` : `Bambu ${tInfo.type}`;
                filamentDisplay = `${slotTag}${escapeHtml(name)} (${slotGrams}g)`;
            } else if (p.filament_type && p.filament_type !== "Невизначено") {
                filamentDisplay = `${slotTag}${escapeHtml(p.filament_type)} (${slotGrams}g)`;
            } else {
                filamentDisplay = `${slotTag}${slotGrams}g`;
            }

            const serialVal = p.serial || p.serial_number || p.serialNumber || p.sn || "";
            const printerModelVal = p.printer_model || p.model || "";
            const fullSearchText = [
                p.name,
                printerModelVal,
                p.ip,
                serialVal,
                modelName,
                p.subtask_name,
                filamentDisplay,
                p.filament_type,
                `${slotGrams}g`,
                `${progress}%`,
                timeStr
            ].filter(Boolean).join(" ").toLowerCase();

            return `
                <div class="printer-card" data-id="${p.id}" data-name="${escapeHtml(p.name)}" data-model="${escapeHtml(modelName)}" data-pmodel="${escapeHtml(printerModelVal)}" data-ip="${escapeHtml(p.ip || '')}" data-sn="${escapeHtml(serialVal)}" data-search="${escapeHtml(fullSearchText)}" data-state="${statusInfo.code}">
                    <div class="printer-card-header">
                        <div class="printer-name-group">
                            <h3>${escapeHtml(p.name)}</h3>
                            <div class="printer-model-sub"><i class="fa-solid fa-file-code"></i> ${escapeHtml(modelName)}</div>
                        </div>
                        <div class="d-flex align-items-center">
                            <span class="status-pill ${statusInfo.badgeClass}">${statusInfo.label}</span>
                            <button type="button" class="btn-card-gear" data-id="${p.id}" title="Налаштування принтера"><i class="fa-solid fa-gear"></i></button>
                        </div>
                    </div>

                    <div class="progress-container">
                        <div class="progress-header">
                            <span>Прогрес: ${progress}%</span>
                            <span>${timeStr}</span>
                        </div>
                        <div class="progress-bar-wrap">
                            <div class="progress-bar ${st === 'PAUSE' || st === 'PAUSED' ? 'amber' : st === 'FAILED' ? 'red' : ''}" style="width: ${progress}%;"></div>
                        </div>
                    </div>

                    <div class="printer-stats-row">
                        <span><i class="fa-solid fa-temperature-high color-red"></i> ${p.nozzle_temp}°C</span>
                        <span><i class="fa-solid fa-hot-tub-person color-orange"></i> ${p.bed_temp}°C</span>
                        <span><i class="fa-solid fa-layer-group color-blue"></i> ${layerStr}</span>
                        <span><i class="fa-solid fa-spool color-purple"></i> ${filamentDisplay}</span>
                    </div>
                </div>`;
        }).join("");

        // Attach click listeners to cards & settings gear buttons
        document.querySelectorAll(".printer-card").forEach(card => {
            card.addEventListener("click", () => {
                const pId = card.getAttribute("data-id");
                openPrinterModal(pId);
            });
        });

        document.querySelectorAll(".btn-card-gear").forEach(btn => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const pId = btn.getAttribute("data-id");
                openPrinterSettingsModal(pId);
            });
        });

        applyPrinterFilters();
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
        const st = String(p.state || "IDLE").toUpperCase();
        const isPrinting = ["RUNNING", "PREPARE", "PRINTING", "CHANGING_FILAMENT"].includes(st);
        let progress = p.progress_pct !== undefined ? p.progress_pct : 0;
        if (st === "FINISH") progress = 100;
        if (st === "OFFLINE" || st === "OFF") progress = 0;

        let timeStr = formatRemainingTime(p.remaining_mins);
        if (st === "FINISH") timeStr = "Завершено";
        else if (st === "FAILED") timeStr = "Збій";
        else if (st === "IDLE") timeStr = "Вільний";
        else if (!timeStr && isPrinting) timeStr = "Підготовка...";

        const layerStr = (st === "IDLE" && p.current_layer === 0) ? "—" : `${p.current_layer} / ${p.total_layers}`;

        modalNameEl.textContent = p.name;
        modalStatusEl.textContent = st;
        modalStatusEl.className = `status-pill status-${st}`;

        modalNozzleTemp.textContent = `${p.nozzle_temp}°C`;
        modalBedTemp.textContent = `${p.bed_temp}°C`;
        modalLayer.textContent = layerStr;
        modalTime.textContent = timeStr || "0 хв";

        const modalSubtask = document.getElementById("modal-subtask-name");
        const modalProgText = document.getElementById("modal-progress-text");
        const modalProgBar = document.getElementById("modal-progress-bar");
        if (modalSubtask && modalProgText && modalProgBar) {
            const modelName = cleanSubtaskName(p.subtask_name, isPrinting);
            modalSubtask.innerHTML = `<i class="fa-solid fa-file-code color-blue"></i> ${escapeHtml(modelName)}`;
            modalProgText.textContent = `${progress}%`;
            modalProgBar.style.width = `${progress}%`;
            modalProgBar.className = `progress-bar ${st === 'PAUSE' || st === 'PAUSED' ? 'amber' : st === 'FAILED' ? 'red' : ''}`;
        }

        const isActivelyPrintingOrPaused = ["RUNNING", "PREPARE", "PREPARATION", "BUILDING", "PRINTING", "CHANGING_FILAMENT", "PAUSE", "PAUSED"].includes(st);

        // Speed Controls Section Visibility
        const speedSection = document.querySelector(".speed-selector")?.closest(".control-section");
        if (speedSection) {
            speedSection.style.display = isActivelyPrintingOrPaused ? "block" : "none";
        }

        // Speed buttons active state
        speedBtns.forEach(btn => {
            const lvl = parseInt(btn.getAttribute("data-level"));
            btn.classList.toggle("active", lvl === p.spd_lvl);
        });

        // Action buttons state: Pause, Resume, Stop
        if (isActivelyPrintingOrPaused) {
            if (st === "PAUSE" || st === "PAUSED") {
                btnPause.style.display = "none";
                btnResume.style.display = "inline-flex";
            } else {
                btnPause.style.display = "inline-flex";
                btnResume.style.display = "none";
            }
            btnStop.style.display = "inline-flex";
        } else {
            btnPause.style.display = "none";
            btnResume.style.display = "none";
            btnStop.style.display = "none";
        }

        // Framework Button Class Toggling: Light & Notifications (btn-warning = ON, btn-neutral = OFF)
        const btnLightModal = document.getElementById("btn-action-light");
        const btnNotifyModal = document.getElementById("btn-action-notify");

        if (btnLightModal) {
            const isLightOn = String(p.chamber_light_state || "off").toLowerCase() === "on";
            if (isLightOn) {
                btnLightModal.classList.add("btn-warning");
                btnLightModal.classList.remove("btn-neutral");
                btnLightModal.innerHTML = `<i class="fa-solid fa-lightbulb"></i> Світло`;
            } else {
                btnLightModal.classList.add("btn-neutral");
                btnLightModal.classList.remove("btn-warning");
                btnLightModal.innerHTML = `<i class="fa-regular fa-lightbulb"></i> Світло`;
            }
        }

        if (btnNotifyModal) {
            const isNotifyOn = Boolean(p.notify);
            if (isNotifyOn) {
                btnNotifyModal.classList.add("btn-warning");
                btnNotifyModal.classList.remove("btn-neutral");
                btnNotifyModal.innerHTML = `<i class="fa-solid fa-bell"></i> Сповіщення`;
            } else {
                btnNotifyModal.classList.add("btn-neutral");
                btnNotifyModal.classList.remove("btn-warning");
                btnNotifyModal.innerHTML = `<i class="fa-solid fa-bell-slash"></i> Сповіщення`;
            }
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
                const rawGrams = slots[k] !== undefined ? slots[k] : 1000;
                const isActive = (k === activeKey);
                const assignedSpool = spoolsList.find(s => s.assigned_printer_id === p.id && String(s.assigned_slot_key) === k);
                const trayInfo = (p.ams_trays_info || {})[k] || {};
                const isTrayEmpty = trayInfo.empty === true || (!assignedSpool && !trayInfo.type);

                let spoolColor = '#334155';
                let spoolName = 'Порожньо';
                let spoolType = 'Порожньо';
                let pct = 0;
                let displayGrams = 0;

                if (assignedSpool) {
                    spoolColor = assignedSpool.color || '#3b82f6';
                    spoolName = escapeHtml(assignedSpool.name);
                    spoolType = escapeHtml(assignedSpool.type);
                    displayGrams = rawGrams;
                    pct = Math.min(100, Math.max(0, Math.round((displayGrams / 1000) * 100)));
                } else if (!isTrayEmpty && trayInfo.type) {
                    spoolColor = trayInfo.color || (isActive ? '#22c55e' : '#3b82f6');
                    spoolType = escapeHtml(trayInfo.type);
                    spoolName = trayInfo.sub_brands ? `Bambu ${spoolType} ${escapeHtml(trayInfo.sub_brands)}` : `Bambu ${spoolType}`;
                    displayGrams = rawGrams;
                    if (trayInfo.remain !== undefined && trayInfo.remain >= 0) {
                        pct = trayInfo.remain;
                    } else {
                        pct = Math.min(100, Math.max(0, Math.round((displayGrams / 1000) * 100)));
                    }
                } else if (isActive && !isTrayEmpty && (p.filament_type && p.filament_type !== "Невизначено")) {
                    spoolColor = '#22c55e';
                    spoolName = 'Активна нитка';
                    spoolType = escapeHtml(p.filament_type);
                    displayGrams = rawGrams;
                    pct = Math.min(100, Math.max(0, Math.round((displayGrams / 1000) * 100)));
                } else {
                    spoolColor = '#334155';
                    spoolName = 'Порожньо';
                    spoolType = 'Порожньо';
                    pct = 0;
                    displayGrams = 0;
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
                                </button>` : `
                                <button class="btn btn-xs btn-outline-primary btn-assign-slot-spool" data-printer="${p.id}" data-slot="${k}" title="Встановити котушку зі Складу">
                                    <i class="fa-solid fa-plus"></i>
                                </button>`}
                            </div>
                        </div>
                        <div class="d-flex align-items-center gap-2 mb-1" style="min-width:0;">
                            <div class="spool-color-dot" style="background-color:${spoolColor}; width:14px; height:14px; border-radius:50%; border:1px solid rgba(255,255,255,0.4); flex-shrink:0;"></div>
                            <div style="font-size:11px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:1; min-width:0;">
                                <strong>${spoolName}</strong> <small class="text-muted">(${spoolType})</small>
                            </div>
                        </div>
                        <div class="d-flex align-items-center justify-content-between" style="font-size:11px;">
                            <span>${displayGrams}g</span>
                            <span class="text-muted">${pct}%</span>
                        </div>
                        <div class="progress-bar-wrap sm mt-1">
                            <div class="progress-bar ${pct < 15 ? 'red' : 'green'}" style="width: ${pct}%;"></div>
                        </div>
                    </div>`;
            }).join("");

            amsSlotsContainer.querySelectorAll(".btn-assign-slot-spool").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const sId = btn.getAttribute("data-slot");
                    let spoolsMap = window.latestSpools;
                    if (!spoolsMap) {
                        try {
                            const res = await fetch("/api/spools");
                            if (res.ok) spoolsMap = await res.json();
                        } catch (e) {}
                    }
                    const availableSpools = Object.values(spoolsMap || {}).filter(s => !s.assigned_printer_id);
                    if (availableSpools.length === 0) {
                        alert("На Складі немає вільних котушок. Додайте котушку у вкладці 'Склад'.");
                        return;
                    }
                    const optionsText = availableSpools.map((s, idx) => `${idx + 1}. ${s.name} (${s.type || 'PLA'}, ${s.remaining_grams || 1000}g)`).join("\n");
                    const choice = prompt(`Виберіть котушку зі Складу для слоту ${slotLabels[sId]}:\n\n${optionsText}\n\nВведіть номер (1-${availableSpools.length}):`);
                    if (choice) {
                        const idx = parseInt(choice.trim()) - 1;
                        if (!isNaN(idx) && availableSpools[idx]) {
                            const targetSpool = availableSpools[idx];
                            await sendPrinterAction({ action: "assign_spool", spool_id: targetSpool.id, slot_id: sId });
                        } else {
                            alert("Невірно вибраний номер!");
                        }
                    }
                });
            });

            amsSlotsContainer.querySelectorAll(".btn-edit-slot-grams").forEach(btn => {
                btn.addEventListener("click", () => {
                    const sId = btn.getAttribute("data-slot");
                    const curG = (p.ams_slots || {})[sId] !== undefined ? p.ams_slots[sId] : 1000;
                    const val = prompt(`Введіть новий залишок ваги (в грамах) для слоту ${slotLabels[sId]}:`, curG);
                    if (val !== null && val.trim() !== "") {
                        try {
                            const parsed = safeMathEval(val.trim());
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

        // Render Skip Objects List in Modal
        const skipObjectsSection = document.getElementById("modal-skip-objects-section");
        const skipObjectsList = document.getElementById("modal-skip-objects-list");
        const btnSkipObject = document.getElementById("btn-action-skip-object");

        if (skipObjectsSection && skipObjectsList) {
            const isPrintingState = ["RUNNING", "PAUSE", "PREPARATION", "BUILDING", "PAUSED"].includes((p.state || p.gcode_state || "").toUpperCase());
            let objects = isPrintingState ? (p.current_job_objects || []).slice() : [];
            const skipped = p.skipped_objects || [];
            if (isPrintingState && objects.length === 0) {
                let maxId = 1;
                skipped.forEach(s => {
                    let val = parseInt(s);
                    if (!isNaN(val) && val > maxId) maxId = val;
                });
                for (let i = 1; i <= maxId; i++) {
                    objects.push({ id: i, name: `Об'єкт #${i}` });
                }
            }

            if (isPrintingState) {
                skipObjectsSection.style.display = "block";
                if (btnSkipObject) btnSkipObject.style.display = "inline-block";

                const stateKey = `${p.id}_${skipped.join(",")}_${objects.map(o => o.id + ":" + (o.name || "")).join(",")}`;
                if (skipObjectsList.dataset.renderedKey !== stateKey) {
                    skipObjectsList.dataset.renderedKey = stateKey;

                    if (objects.length > 0) {
                        const sanitizeObjName = (nameStr) => {
                            if (!nameStr) return "";
                            let clean = String(nameStr).trim();
                            let mNum = clean.match(/#(\d+)/);
                            let numStr = mNum ? (" #" + mNum[1]) : "";

                            let nLow = clean.toLowerCase();
                            let yWord = "";
                            if (nLow.includes("ззаду")) yWord = "Ззаду";
                            else if (nLow.includes("спереду")) yWord = "Спереду";

                            let xWord = "";
                            if (nLow.includes("ліворуч")) xWord = "Ліворуч";
                            else if (nLow.includes("праворуч")) xWord = "Праворуч";

                            let centerWord = "";
                            if (!yWord && !xWord && (nLow.includes("по центру") || nLow.includes("центр"))) {
                                centerWord = "По центру";
                            }

                            let spatialParts = [yWord, xWord, centerWord].filter(w => w !== "");
                            let posTag = spatialParts.length > 0 ? (" (" + spatialParts.join(" ") + ")") : "";

                            let base = clean.replace(/\s*#\d+.*/, "").replace(/\s*\(.*?\)/g, "").trim();
                            if (!base) base = "Об'єкт";

                            return `${base}${numStr}${posTag}`.trim();
                        };
                        const initDataParam = window.Telegram?.WebApp?.initData ? ('&initData=' + encodeURIComponent(window.Telegram.WebApp.initData)) : '';
                        const tokenParam = localStorage.getItem("token") ? ('&token=' + encodeURIComponent(localStorage.getItem("token"))) : '';
                        const mapHtml = `<div class="text-center mb-2"><img src="/api/printers/${p.id}/plate_map?format=jpg&v=${encodeURIComponent(stateKey)}${initDataParam}${tokenParam}" class="img-fluid rounded border border-secondary shadow-sm" style="max-height: 260px; background-color: #16161a;" alt="Схема столу" /></div>`;
                        const btnsHtml = objects.map(obj => {
                            const objId = obj.id;
                            const isSkipped = skipped.includes(parseInt(objId)) || skipped.includes(String(objId));
                            const labelText = isSkipped ? `#${objId} (Пропущено)` : `#${objId}`;
                            return `
                                <button class="btn btn-sm py-1 px-2 ${isSkipped ? 'btn-secondary disabled' : 'btn-outline-danger'} btn-skip-obj-item me-1 mb-1 font-monospace fw-bold" 
                                        data-id="${objId}" ${isSkipped ? 'disabled' : ''}>
                                    ${isSkipped ? '<i class="fa-solid fa-xmark"></i> ' : '<i class="fa-solid fa-ban me-1"></i>'}
                                    ${escapeHtml(labelText)}
                                </button>`;
                        }).join("");
                        skipObjectsList.innerHTML = mapHtml + btnsHtml;

                        skipObjectsList.querySelectorAll(".btn-skip-obj-item:not(.disabled)").forEach(b => {
                            b.addEventListener("click", async () => {
                                const objId = parseInt(b.getAttribute("data-id"));
                                if (confirm(`Пропустити об'єкт #${objId} на плейті без зупинки друку?`)) {
                                    await sendPrinterAction({ action: "skip_objects", obj_ids: [objId] });
                                }
                            });
                        });
                    }
                }
            } else {
                skipObjectsSection.style.display = "none";
                if (btnSkipObject) btnSkipObject.style.display = "none";
                skipObjectsList.dataset.renderedKey = "";
            }
        }
    }

    const fullscreenCamModal = document.getElementById("camera-fullscreen-modal");
    const fullscreenCamImg = document.getElementById("fullscreen-camera-img");
    const fullscreenCamTitle = document.getElementById("fullscreen-camera-title");
    const fullscreenCamBtn = document.getElementById("fullscreen-cam-btn");
    const closeFullscreenCamBtn = document.getElementById("close-fullscreen-cam-btn");
    const fullscreenRefreshCamBtn = document.getElementById("fullscreen-refresh-cam-btn");

    function loadCameraSnapshot(pId) {
        if (!pId) return;
        const initDataParam = tg?.initData ? "?initData=" + encodeURIComponent(tg.initData) : "";
        const streamUrl = `/api/printers/${pId}/stream${initDataParam}`;

        if (cameraImg) {
            cameraImg.style.display = "block";
            if (cameraImg.nextElementSibling) cameraImg.nextElementSibling.style.display = "none";
            if (!cameraImg.src.includes(`/api/printers/${pId}/stream`)) {
                cameraImg.src = streamUrl;
                cameraImg.onerror = () => {
                    setTimeout(() => {
                        if (selectedPrinterId === pId && cameraImg) {
                            cameraImg.src = `/api/printers/${pId}/stream?t=${Date.now()}${tg?.initData ? "&initData=" + encodeURIComponent(tg.initData) : ""}`;
                        }
                    }, 2000);
                };
            }
        }

        if (fullscreenCamImg && fullscreenCamModal && fullscreenCamModal.classList.contains("active")) {
            fullscreenCamImg.style.display = "block";
            if (fullscreenCamImg.nextElementSibling) fullscreenCamImg.nextElementSibling.style.display = "none";
            if (!fullscreenCamImg.src.includes(`/api/printers/${pId}/stream`)) {
                fullscreenCamImg.src = streamUrl;
                fullscreenCamImg.onerror = () => {
                    setTimeout(() => {
                        if (selectedPrinterId === pId && fullscreenCamImg) {
                            fullscreenCamImg.src = `/api/printers/${pId}/stream?t=${Date.now()}${tg?.initData ? "&initData=" + encodeURIComponent(tg.initData) : ""}`;
                        }
                    }, 2000);
                };
            }
        }
    }

    function openFullscreenCamera() {
        if (!selectedPrinterId) return;
        triggerHaptic("medium");
        const currentP = printersData.find(p => p.id === selectedPrinterId);
        if (fullscreenCamTitle && currentP) {
            fullscreenCamTitle.innerHTML = `<i class="fa-solid fa-video color-green"></i> ${escapeHtml(currentP.name)} (Жива камера)`;
        }
        if (fullscreenCamModal) {
            fullscreenCamModal.classList.add("active");
            if (fullscreenCamModal.requestFullscreen) {
                fullscreenCamModal.requestFullscreen().catch(() => {});
            }
        }
        loadCameraSnapshot(selectedPrinterId);
    }

    function closeFullscreenCamera() {
        triggerHaptic("light");
        if (fullscreenCamModal) {
            fullscreenCamModal.classList.remove("active");
        }
        if (document.fullscreenElement && document.exitFullscreen) {
            document.exitFullscreen().catch(() => {});
        }
    }

    if (fullscreenCamBtn) {
        fullscreenCamBtn.addEventListener("click", openFullscreenCamera);
    }

    if (cameraImg) {
        cameraImg.addEventListener("click", openFullscreenCamera);
    }

    if (closeFullscreenCamBtn) {
        closeFullscreenCamBtn.addEventListener("click", closeFullscreenCamera);
    }

    if (fullscreenRefreshCamBtn) {
        fullscreenRefreshCamBtn.addEventListener("click", () => {
            triggerHaptic("light");
            if (selectedPrinterId) loadCameraSnapshot(selectedPrinterId);
        });
    }

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && fullscreenCamModal && fullscreenCamModal.classList.contains("active")) {
            closeFullscreenCamera();
        }
    });

    closeModalBtn.addEventListener("click", () => {
        triggerHaptic("light");
        printerModal.classList.remove("active");
        if (fullscreenCamModal) fullscreenCamModal.classList.remove("active");
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
                if (["assign_spool", "unassign_spool", "set_slot_grams", "set_filament"].includes(actionPayload.action)) {
                    try {
                        const sRes = await fetch("/api/spools");
                        if (sRes.ok) window.latestSpools = await sRes.json();
                    } catch (e) {}
                }
                await fetchPrinters();
                if (selectedPrinterId && printerModal.classList.contains("active")) {
                    const currentP = printersData.find(p => p.id === selectedPrinterId);
                    if (currentP) updatePrinterModalContent(currentP);
                }
            } else {
                alert("Помилка при виконанні дії: " + (data.error || "Невідомо"));
            }
        } catch (e) {
            console.error("Action error:", e);
        }
    }

    const btnNotify = document.getElementById("btn-action-notify");
    const btnCalibrate = document.getElementById("btn-action-calibrate");
    const btnSkipObjectModal = document.getElementById("btn-action-skip-object");

    if (btnSkipObjectModal) {
        btnSkipObjectModal.addEventListener("click", () => {
            const sec = document.getElementById("modal-skip-objects-section");
            if (sec) sec.scrollIntoView({ behavior: "smooth" });
        });
    }

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
            const form = document.getElementById("add-printer-form");
            if (form) form.reset();
            if (addPrinterModal) addPrinterModal.classList.add("active");
            setTimeout(() => {
                const nameInput = document.getElementById("new-p-name");
                if (nameInput) nameInput.focus();
            }, 100);
        });
    }

    if (closeAddPrinterModalBtn) {
        closeAddPrinterModalBtn.addEventListener("click", () => {
            triggerHaptic("light");
            if (addPrinterModal) addPrinterModal.classList.remove("active");
        });
    }

    if (addPrinterModal) {
        addPrinterModal.addEventListener("click", (e) => {
            if (e.target === addPrinterModal) {
                addPrinterModal.classList.remove("active");
            }
        });
    }

    async function submitAddPrinterForm() {
        const nameInput = document.getElementById("new-p-name");
        const ipInput = document.getElementById("new-p-ip");
        const codeInput = document.getElementById("new-p-code");
        const snInput = document.getElementById("new-p-sn");
        const modelInput = document.getElementById("new-p-model");

        const name = nameInput ? nameInput.value.trim() : "";
        const ip = ipInput ? ipInput.value.trim() : "";
        const accessCode = codeInput ? codeInput.value.trim() : "";
        const serialNumber = snInput ? snInput.value.trim() : "";
        const printer_model = modelInput ? modelInput.value.trim() : "P1S";

        if (!name || !ip || !accessCode || !serialNumber) {
            alert("Будь ласка, заповніть всі поля (Назва, Модель, IP, Код доступу, Серійний номер)!");
            return;
        }

        triggerHaptic("medium");
        if (savePrinterSubmitBtn) {
            savePrinterSubmitBtn.disabled = true;
            savePrinterSubmitBtn.textContent = "Збереження...";
        }

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);

        try {
            const res = await fetch("/api/printers", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name, ip, accessCode, serialNumber, printer_model }),
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            const data = await res.json();
            if (data.status === "ok") {
                if (addPrinterModal) addPrinterModal.classList.remove("active");
                const form = document.getElementById("add-printer-form");
                if (form) form.reset();
                fetchPrinters();
            } else {
                alert("Помилка додавання принтера: " + (data.error || "Невідомо"));
            }
        } catch (e) {
            clearTimeout(timeoutId);
            console.error("Add printer error:", e);
            alert("Помилка з'єднання або таймаут при додаванні принтера.");
        } finally {
            if (savePrinterSubmitBtn) {
                savePrinterSubmitBtn.disabled = false;
                savePrinterSubmitBtn.textContent = "Зберегти принтер";
            }
        }
    }

    const addPrinterFormEl = document.getElementById("add-printer-form");
    if (addPrinterFormEl) {
        addPrinterFormEl.addEventListener("submit", (e) => {
            e.preventDefault();
            submitAddPrinterForm();
        });
    }

    if (savePrinterSubmitBtn) {
        savePrinterSubmitBtn.addEventListener("click", (e) => {
            e.preventDefault();
            submitAddPrinterForm();
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
        window.loadMaterialsGlobal = loadMaterials;
        const container = document.getElementById("ams-printers-container");
        if (container) {
            container.innerHTML = `<div class="loading-spinner"><i class="fa-solid fa-circle-notch fa-spin"></i> Завантаження...</div>`;
        }

        try {
            const [printersRes, spoolsRes] = await Promise.all([
                fetch("/api/printers"),
                fetch("/api/spools")
            ]);
            const printers = await printersRes.json();
            const spools = await spoolsRes.json();

            // Render AMS for printers if container exists
            if (container) {
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
                                let grams = safeMathEval(inputVal);

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
            }

            // Render Spool Inventory
            const spoolsList = document.getElementById("spools-list");
            const spoolsArray = Object.values(spools || {}).filter(s => !s.assigned_printer_id && (s.quantity || 1) > 0);
            if (spoolsArray.length === 0) {
                spoolsList.innerHTML = `<p class="text-muted text-center p-3">Склад порожній. Натисніть "+ Нова котушка", щоб додати.</p>`;
            } else {
                spoolsList.innerHTML = spoolsArray.map(s => `
                    <div class="spool-item glass-card p-3 mb-2 d-flex justify-content-between align-items-center">
                        <div class="spool-left d-flex align-items-center gap-2">
                            <div class="spool-color-circle" style="background-color: ${s.color || '#3b82f6'}; width: 24px; height: 24px; border-radius: 50%; border: 1px solid rgba(255,255,255,0.3);"></div>
                            <div class="spool-details">
                                <h4 style="margin:0; font-size:14px;">
                                    ${escapeHtml(s.name)} 
                                    <span class="badge badge-secondary" style="font-size:10px; font-weight:500; margin-left:4px;">📦 ${s.quantity || 1} шт</span>
                                </h4>
                                <small class="text-muted">${escapeHtml(s.type || 'PLA')} • ${s.price_per_kg || s.price_uah || 650} ₴/кг • ⚡ ${s.remaining_grams || 1000}g</small>
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
                            window.openAddSpoolModal(s);
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

        const list = Array.isArray(printers) && printers.length > 0 ? printers : (printersData || []);
        if (list.length === 0) {
            alert("Немає підключених принтерів для встановлення котушки.");
            return;
        }

        selectPrinter.innerHTML = list.map(p => `<option value="${p.id}">${escapeHtml(p.name)} (${p.ip})</option>`).join("");
        triggerHaptic("light");
        modal.classList.add("active");
    }

    const closeAssignSpoolModalBtn = document.getElementById("close-assign-spool-modal");
    if (closeAssignSpoolModalBtn) {
        closeAssignSpoolModalBtn.addEventListener("click", () => {
            const modal = document.getElementById("assign-spool-modal");
            if (modal) modal.classList.remove("active");
        });
    }

    const confirmAssignBtn = document.getElementById("confirm-assign-spool-btn");
    if (confirmAssignBtn) {
        confirmAssignBtn.addEventListener("click", async () => {
            if (!selectedSpoolForAssign) return;
            const printerSelect = document.getElementById("assign-printer-select");
            const slotSelect = document.getElementById("assign-slot-select");
            const printerId = printerSelect ? printerSelect.value : "";
            const slotId = slotSelect ? slotSelect.value : "255";

            if (!printerId) {
                alert("Виберіть принтер зі списку!");
                return;
            }

            triggerHaptic("medium");
            confirmAssignBtn.disabled = true;
            confirmAssignBtn.textContent = "⏳ Встановлення...";

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
                const result = await res.json().catch(() => ({}));
                if (res.ok && result.status === "ok") {
                    try {
                        const sRes = await fetch("/api/spools");
                        if (sRes.ok) window.latestSpools = await sRes.json();
                    } catch (e) {}

                    const modal = document.getElementById("assign-spool-modal");
                    if (modal) modal.classList.remove("active");
                    await loadMaterials();
                    await fetchPrinters();

                    if (selectedPrinterId && printerModal.classList.contains("active")) {
                        const currentP = printersData.find(p => p.id === selectedPrinterId);
                        if (currentP) updatePrinterModalContent(currentP);
                    }
                } else {
                    alert("Помилка встановлення: " + (result.error || `HTTP ${res.status}`));
                }
            } catch (err) {
                console.error("Assign spool error:", err);
                alert("Помилка з'єднання при встановленні котушки.");
            } finally {
                confirmAssignBtn.disabled = false;
                confirmAssignBtn.textContent = "Встановити на принтер";
            }
        });
    }

    // Preset Chips Handlers
    document.querySelectorAll(".preset-chip").forEach(chip => {
        chip.addEventListener("click", () => {
            triggerHaptic("light");
            const pName = chip.getAttribute("data-name");
            const pType = chip.getAttribute("data-type");
            const pColor = chip.getAttribute("data-color");
            const pPrice = chip.getAttribute("data-price");

            const nameEl = document.getElementById("spool-name");
            const typeEl = document.getElementById("spool-type");
            const colorEl = document.getElementById("spool-color");
            const priceEl = document.getElementById("spool-price");

            if (nameEl && pName) nameEl.value = pName;
            if (typeEl && pType) typeEl.value = pType;
            if (colorEl && pColor) colorEl.value = pColor;
            if (priceEl && pPrice) priceEl.value = pPrice;
        });
    });

    if (addSpoolBtn) {
        addSpoolBtn.addEventListener("click", (e) => {
            if (e) {
                e.preventDefault();
                e.stopPropagation();
            }
            window.openAddSpoolModal();
        });
    }

    if (closeSpoolModalBtn) {
        closeSpoolModalBtn.addEventListener("click", (e) => {
            if (e) {
                e.preventDefault();
                e.stopPropagation();
            }
            window.closeSpoolModal();
        });
    }

    if (saveSpoolSubmitBtn) {
        saveSpoolSubmitBtn.addEventListener("click", (e) => {
            window.submitSaveSpool(e);
        });
    }

    // 8. Tab 3: History & Analytics
    function formatHistoryDate(ts, dtStr) {
        if (dtStr && typeof dtStr === "string" && dtStr !== "-") return dtStr;
        if (!ts) return "-";
        if (typeof ts === "number") {
            const d = new Date(ts * 1000);
            if (!isNaN(d.getTime())) {
                return d.toLocaleString("uk-UA", {
                    year: "numeric",
                    month: "2-digit",
                    day: "2-digit",
                    hour: "2-digit",
                    minute: "2-digit"
                });
            }
        }
        return String(ts);
    }

    let cachedHistoryEntries = [];

    function populateHistoryPrinterSelect(history) {
        const sel = document.getElementById("history-filter-printer");
        if (!sel) return;
        const curVal = sel.value;
        const printersMap = new Map();

        (history || []).forEach(item => {
            const pId = item.printer_id || item.printer_sn || item.printer || "";
            const pName = item.printer_name || item.printer || pId || "Принтер";
            if (pId || pName) {
                printersMap.set(pId || pName, pName);
            }
        });

        if (window.printersData && Array.isArray(window.printersData)) {
            window.printersData.forEach(p => {
                printersMap.set(p.id, p.name || p.id);
            });
        }

        let optionsHtml = `<option value="">🌐 Усі принтери</option>`;
        printersMap.forEach((name, id) => {
            optionsHtml += `<option value="${escapeHtml(id)}">${escapeHtml(name)}</option>`;
        });

        if (sel.innerHTML !== optionsHtml) {
            sel.innerHTML = optionsHtml;
            if (curVal && printersMap.has(curVal)) {
                sel.value = curVal;
            }
        }
    }

    function renderHistoryList(history) {
        const tbody = document.getElementById("history-table-body");
        if (!tbody) return;

        const statJobsEl = document.getElementById("stat-total-jobs");
        const statWeightEl = document.getElementById("stat-total-weight");

        let totalGrams = 0;
        history.forEach(item => {
            const g = item.weight_g !== undefined ? item.weight_g : (item.weight ? Math.round(item.weight) : 0);
            totalGrams += g;
        });

        if (statJobsEl) statJobsEl.textContent = history.length;
        if (statWeightEl) {
            const formattedGrams = totalGrams > 0 && totalGrams < 10 ? (Math.round(totalGrams * 10) / 10) : Math.round(totalGrams);
            statWeightEl.textContent = `${formattedGrams} g`;
        }

        if (!history || history.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="text-center">Записи історії за обраними фільтрами не знайдені</td></tr>`;
            return;
        }

        tbody.innerHTML = history.slice(-100).reverse().map(item => {
            const dateFormatted = formatHistoryDate(item.timestamp, item.datetime);
            const printerName = escapeHtml(item.printer_name || item.printer || "Принтер");
            const taskName = escapeHtml(item.subtask_name || item.task || "Модель");
            const printerId = escapeHtml(item.printer_id || item.printer_sn || "");
            const weightVal = item.weight_g !== undefined ? item.weight_g : (item.weight ? Math.round(item.weight) : 0);

            return `
            <tr>
                <td>${dateFormatted}</td>
                <td><strong>${printerName}</strong></td>
                <td>
                    <div class="d-flex align-items-center justify-content-between gap-2">
                        <code>${taskName}</code>
                        <button type="button" class="icon-btn btn-reprint-history" data-task="${taskName}" data-printer="${printerName}" data-printer-id="${printerId}" title="Повторно кинути на друк">
                            <i class="fa-solid fa-rotate-right"></i>
                        </button>
                    </div>
                </td>
                <td>${weightVal}g</td>
                <td class="text-center">
                    <button class="btn btn-xs btn-outline-danger btn-delete-history-entry" data-ts="${item.timestamp}" title="Видалити запис">
                        <i class="fa-solid fa-xmark"></i>
                    </button>
                </td>
            </tr>`;
        }).join("");

        tbody.querySelectorAll(".btn-reprint-history").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                e.preventDefault();
                const taskName = btn.getAttribute("data-task") || "Модель";
                const origPrinterName = btn.getAttribute("data-printer") || "Принтер";
                const origPrinterId = btn.getAttribute("data-printer-id") || "";

                if (!printersData || printersData.length === 0) {
                    alert("⚠️ Немає підключених принтерів у фермі!");
                    return;
                }

                const targetPrinter = printersData.find(p => p.id === origPrinterId || p.name === origPrinterName || (p.name && origPrinterName && p.name.toLowerCase().includes(origPrinterName.toLowerCase()))) || printersData[0];

                const confirmed = confirm(`🚀 Повторно кинути на друк модель "${taskName}"?\n\nПринтер: ${targetPrinter.name}`);
                if (!confirmed) return;

                triggerHaptic("medium");

                try {
                    let partsList = [];
                    try {
                        const partsRes = await fetch("/api/parts");
                        const partsData = await partsRes.json();
                        partsList = Object.values(partsData || {});
                    } catch (e) {
                        console.error("Failed fetching parts for reprint:", e);
                    }

                    const normTask = taskName.trim().toLowerCase();
                    const matchedPart = partsList.find(p => {
                        if (!p.name) return false;
                        const normP = p.name.trim().toLowerCase();
                        return normP === normTask || normTask.includes(normP) || normP.includes(normTask);
                    });

                    if (matchedPart && matchedPart.id) {
                        const res = await fetch(`/api/parts/${matchedPart.id}/print/${targetPrinter.id}`, { method: "POST" });
                        const result = await res.json().catch(() => ({}));
                        if (res.ok && result.status === "ok") {
                            alert(`✅ Модель "${taskName}" успішно відправлено на друк на принтер ${targetPrinter.name}!`);
                        } else {
                            alert(`⚠️ Помилка запуску друку: ${result.error || `HTTP ${res.status}`}`);
                        }
                    } else {
                        let filesList = [];
                        try {
                            const filesRes = await fetch("/api/files");
                            const filesData = await filesRes.json();
                            filesList = Array.isArray(filesData.files) ? filesData.files : [];
                        } catch (e) {}

                        const matchedFile = filesList.find(f => {
                            const fName = (f.filename || f.name || "").trim().toLowerCase();
                            return fName === normTask || normTask.includes(fName) || fName.includes(normTask);
                        });

                        if (matchedFile && (matchedFile.file_token || matchedFile.filename)) {
                            const fileToken = matchedFile.file_token || matchedFile.filename;
                            const res = await fetch(`/api/printers/${targetPrinter.id}/print_file`, {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({ file_token: fileToken, filename: matchedFile.filename || taskName })
                            });
                            const result = await res.json().catch(() => ({}));
                            if (res.ok && result.status === "ok") {
                                alert(`✅ Файл "${taskName}" успішно відправлено на друк на принтер ${targetPrinter.name}!`);
                            } else {
                                alert(`⚠️ Помилка запуску друку: ${result.error || `HTTP ${res.status}`}`);
                            }
                        } else {
                            alert(`⚠️ Модель або файл "${taskName}" не знайдено в Складі деталей чи Завантаженнях. Неможливо заново запустити друк.`);
                        }
                    }
                } catch (err) {
                    console.error("Reprint error:", err);
                    alert("⚠️ Помилка зв'язку при запуску повторного друку.");
                }
            });
        });

        tbody.querySelectorAll(".btn-delete-history-entry").forEach(btn => {
            btn.addEventListener("click", async () => {
                const ts = btn.getAttribute("data-ts");
                if (ts && confirm("Видалити цей запис із історії?")) {
                    await fetch(`/api/history?timestamp=${encodeURIComponent(ts)}`, { method: "DELETE" });
                    loadHistory();
                }
            });
        });
    }

    function applyHistoryFilters() {
        if (!cachedHistoryEntries) return;

        const searchQuery = (document.getElementById("history-filter-search")?.value || "").toLowerCase().trim();
        const selectedPrinter = (document.getElementById("history-filter-printer")?.value || "").toLowerCase().trim();
        const selectedDate = document.getElementById("history-filter-date")?.value || "";

        const filtered = cachedHistoryEntries.filter(item => {
            const taskName = String(item.subtask_name || item.task || "").toLowerCase();
            const printerName = String(item.printer_name || item.printer || "").toLowerCase();
            const printerId = String(item.printer_id || item.printer_sn || "").toLowerCase();

            // 1. Search Query filter (task name or printer name)
            if (searchQuery && !taskName.includes(searchQuery) && !printerName.includes(searchQuery)) {
                return false;
            }

            // 2. Printer filter
            if (selectedPrinter) {
                if (printerId !== selectedPrinter && printerName !== selectedPrinter && !printerName.includes(selectedPrinter)) {
                    return false;
                }
            }

            // 3. Date filter
            if (selectedDate) {
                let itemDate = "";
                if (item.timestamp) {
                    const rawTs = typeof item.timestamp === "number" && item.timestamp < 10000000000 ? item.timestamp * 1000 : item.timestamp;
                    const d = new Date(rawTs);
                    if (!isNaN(d.getTime())) {
                        const yyyy = d.getFullYear();
                        const mm = String(d.getMonth() + 1).padStart(2, '0');
                        const dd = String(d.getDate()).padStart(2, '0');
                        itemDate = `${yyyy}-${mm}-${dd}`;
                    }
                }
                if (!itemDate && item.datetime) {
                    itemDate = String(item.datetime).slice(0, 10);
                }
                if (itemDate && itemDate !== selectedDate) {
                    return false;
                }
            }

            return true;
        });

        renderHistoryList(filtered);
    }

    // Attach listeners for history filter bar
    document.getElementById("history-filter-search")?.addEventListener("input", applyHistoryFilters);
    document.getElementById("history-filter-printer")?.addEventListener("change", applyHistoryFilters);
    document.getElementById("history-filter-date")?.addEventListener("change", applyHistoryFilters);

    async function loadHistory() {
        try {
            const res = await fetch("/api/history");
            const data = await res.json();

            cachedHistoryEntries = data.history || [];
            populateHistoryPrinterSelect(cachedHistoryEntries);
            applyHistoryFilters();
        } catch (e) {
            console.error("Failed loading history:", e);
        }
    }

    const btnRefreshHistory = document.getElementById("btn-refresh-history");
    if (btnRefreshHistory) {
        btnRefreshHistory.addEventListener("click", () => {
            triggerHaptic("light");
            loadHistory();
        });
    }

    const btnClearHistory = document.getElementById("btn-clear-history");
    if (btnClearHistory) {
        btnClearHistory.addEventListener("click", async () => {
            triggerHaptic("heavy");
            if (confirm("Ви дійсно хочете ОЧИСТИТИ всю історію друку?")) {
                await fetch("/api/history", { method: "DELETE" });
                loadHistory();
            }
        });
    }

    async function downloadReportFile(urlOrBlob, defaultFilename) {
        try {
            const initData = window.Telegram?.WebApp?.initData || "";
            const sessionToken = localStorage.getItem("web_session_token") || "";

            // String URL (GET API Endpoint)
            if (typeof urlOrBlob === "string") {
                const downloadUrl = new URL(urlOrBlob, window.location.origin);
                if (initData) downloadUrl.searchParams.set("initData", initData);
                if (sessionToken) downloadUrl.searchParams.set("token", sessionToken);

                const fullUrlStr = downloadUrl.toString();

                if (window.Telegram?.WebApp?.downloadFile) {
                    try {
                        window.Telegram.WebApp.downloadFile({ url: fullUrlStr, filename: defaultFilename });
                        return;
                    } catch (e) {
                        console.warn("Telegram downloadFile failed, fallback:", e);
                    }
                }

                if (window.Telegram?.WebApp?.openLink) {
                    try {
                        window.Telegram.WebApp.openLink(fullUrlStr);
                        return;
                    } catch (e) {
                        console.warn("Telegram openLink failed, fallback:", e);
                    }
                }

                // Standard browser fallback
                window.location.href = fullUrlStr;
                return;
            }

            // Blob object (e.g. generated PDF)
            if (urlOrBlob instanceof Blob) {
                const reader = new FileReader();
                reader.readAsDataURL(urlOrBlob);
                reader.onloadend = function () {
                    const dataUrl = reader.result;

                    const a = document.createElement("a");
                    a.href = dataUrl;
                    a.download = defaultFilename;
                    a.target = "_blank";
                    document.body.appendChild(a);
                    a.click();
                    setTimeout(() => a.remove(), 1000);
                };
            }
        } catch (err) {
            console.error("Report Download Error:", err);
            alert("Помилка завантаження звіту: " + (err.message || err));
        }
    }

    function attachDirectDownloadLink(linkId, baseUrl) {
        const el = document.getElementById(linkId);
        if (!el) return;
        const updateHref = () => {
            const initData = window.Telegram?.WebApp?.initData || "";
            const sessionToken = localStorage.getItem("web_session_token") || "";
            const url = new URL(baseUrl, window.location.origin);
            if (initData) url.searchParams.set("initData", initData);
            if (sessionToken) url.searchParams.set("token", sessionToken);
            el.href = url.toString();
        };
        el.addEventListener("mouseenter", updateHref);
        el.addEventListener("touchstart", updateHref, { passive: true });
        el.addEventListener("click", (e) => {
            updateHref();
            if (window.Telegram?.WebApp?.openLink) {
                e.preventDefault();
                window.Telegram.WebApp.openLink(el.href);
            }
        });
        updateHref();
    }

    attachDirectDownloadLink("btn-export-history-pdf", "/api/history/export_pdf");
    attachDirectDownloadLink("btn-export-spools-pdf", "/api/spools/export_pdf");
    attachDirectDownloadLink("btn-export-parts-pdf", "/api/parts/export_pdf");

    const exportPdfBtn = document.getElementById("btn-export-calc-pdf");
    if (exportPdfBtn) {
        exportPdfBtn.addEventListener("click", (e) => {
            e.preventDefault();
            const presetSelect = document.getElementById("calc-preset-select");
            const presetId = presetSelect?.value || "";
            const weightG = document.getElementById("calc-weight-g")?.value || "100";
            const timeMins = document.getElementById("calc-time-mins")?.value || "60";

            const endpoint = `/api/commercial/export_pdf?preset_id=${encodeURIComponent(presetId)}&weight_g=${encodeURIComponent(weightG)}&time_mins=${encodeURIComponent(timeMins)}`;
            downloadReportFile(endpoint, `print_cost_calculation_${new Date().toISOString().slice(0, 10)}.html`);
        });
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

            const presetList = [];
            const seenKeys = new Set();
            for (const p of Object.values(currentPresets || {})) {
                const key = (p.name || p.id || "").trim();
                if (key && !seenKeys.has(key)) {
                    seenKeys.add(key);
                    presetList.push(p);
                }
            }

            if (presetList.length === 0) {
                selectEl.innerHTML = `<option value="">(Пресети відсутні)</option>`;
                listEl.innerHTML = `<p class="text-muted text-center p-3">Список пресетів порожній. Натисніть "+ Новий пресет", щоб додати.</p>`;
            } else {
                selectEl.innerHTML = presetList.map(p =>
                    `<option value="${p.id}">${escapeHtml(p.name)}</option>`
                ).join("");
                if (!selectEl.value) selectEl.value = presetList[0].id;

                listEl.innerHTML = presetList.map(p => `
                    <div class="spool-item">
                        <div class="spool-left">
                            <i class="fa-solid fa-calculator color-orange" style="font-size:20px;"></i>
                            <div class="spool-details">
                                <h4>${escapeHtml(p.name)}</h4>
                                <p>Пластик: ${p.price_per_g} грн/г | Світло: ${p.electricity_rate_uah || 4.32} ₴/кВт·год (${p.power_watts || 120} Вт) | Маржа: ${p.profit_val}</p>
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
            }

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
                    const elecEl = document.getElementById("preset-elec-rate");
                    if (elecEl) elecEl.value = p.electricity_rate_uah !== undefined ? p.electricity_rate_uah : 4.32;
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
    if (presetModal) {
        presetModal.addEventListener("click", (e) => {
            if (e.target === presetModal) {
                presetModal.classList.remove("active");
            }
        });
    }

    document.getElementById("add-preset-btn")?.addEventListener("click", () => {
        editingPresetId = null;
        const titleEl = document.getElementById("preset-modal-title");
        if (titleEl) titleEl.textContent = "➕ Створити пресет ціноутворення";

        document.getElementById("preset-name").value = "";
        document.getElementById("preset-price-g").value = "0.85";
        const elecEl = document.getElementById("preset-elec-rate");
        if (elecEl) elecEl.value = "4.32";
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

    async function submitPresetForm() {
        triggerHaptic("medium");
        const name = document.getElementById("preset-name").value.trim();
        const raw_price = String(document.getElementById("preset-price-g").value || "").replace(",", ".");
        const price_per_g = (raw_price && !isNaN(parseFloat(raw_price))) ? parseFloat(raw_price) : 0.85;
        const elecEl = document.getElementById("preset-elec-rate");
        const raw_elec = String(elecEl ? elecEl.value : "4.32").replace(",", ".");
        const electricity_rate_uah = (raw_elec && !isNaN(parseFloat(raw_elec))) ? parseFloat(raw_elec) : 4.32;
        const raw_power = String(document.getElementById("preset-power").value || "").replace(",", ".");
        const power_watts = (raw_power && !isNaN(parseFloat(raw_power))) ? parseFloat(raw_power) : 120.0;
        const depreciation_val = document.getElementById("preset-depreciation").value.trim() || "10";
        const consumables_val = document.getElementById("preset-consumables").value.trim() || "5";
        const profit_val = document.getElementById("preset-profit").value.trim() || "100%";

        if (!name) return alert("⚠️ Введіть назву пресета");

        const payload = {
            name, price_per_g, electricity_rate_uah, power_watts, depreciation_val, consumables_val, profit_val
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
                if (presetModal) presetModal.classList.remove("active");
                editingPresetId = null;
                await loadCommercialPresets();
            } else {
                alert(`⚠️ Помилка збереження: ${data.error || "Невідома"}`);
            }
        } catch (e) {
            console.error("Failed saving preset:", e);
            alert(`⚠️ Не вдалося зберегти пресет: ${e.message || e}`);
        }
    }

    const presetFormEl = document.getElementById("preset-form");
    if (presetFormEl) {
        presetFormEl.addEventListener("submit", (e) => {
            e.preventDefault();
            submitPresetForm();
        });
    }

    document.getElementById("save-preset-submit")?.addEventListener("click", (e) => {
        e.preventDefault();
        submitPresetForm();
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

    // 10. Tab 5: Settings & User Notifications Management
    async function loadSettings() {
        try {
            const [userSettingsRes, globalSettingsRes, healthRes] = await Promise.all([
                fetch("/api/user/settings"),
                fetch("/api/settings"),
                fetch("/health")
            ]);

            const userSettingsData = userSettingsRes.ok ? await userSettingsRes.json() : {};
            const globalSettings = globalSettingsRes.ok ? await globalSettingsRes.json() : {};
            const health = healthRes.ok ? await healthRes.json() : {};

            const notify = userSettingsData.notify || {};

            const chkStart = document.getElementById("setting-notify-start");
            const chkFinish = document.getElementById("setting-notify-finish");
            const chkPause = document.getElementById("setting-notify-pause");
            const chkHms = document.getElementById("setting-notify-hms");
            const chkRemindClear = document.getElementById("setting-notify-remind-clear");

            if (chkStart) chkStart.checked = notify.start !== false;
            if (chkFinish) chkFinish.checked = notify.finish !== false;
            if (chkPause) chkPause.checked = notify.pause !== false;
            if (chkHms) chkHms.checked = notify.hms !== false;
            if (chkRemindClear) chkRemindClear.checked = notify.remind_clear !== false;

            const selMinTime = document.getElementById("setting-notify-min-time");
            if (selMinTime) selMinTime.value = String(notify.min_time_to_end || 0);

            const selMinFilament = document.getElementById("setting-notify-min-filament");
            if (selMinFilament) selMinFilament.value = String(notify.min_filament || 0);

            const uptimeMins = Math.floor((health.uptime_seconds || 0) / 60);
            document.getElementById("sys-uptime").textContent = `${uptimeMins} хв`;
            document.getElementById("sys-printers-count").textContent = health.total_printers || 0;

            const adminUsersCard = document.getElementById("admin-users-card");
            const isUserAdmin = userSettingsData.user?.role === "ADMIN" || Boolean(userSettingsData.user?.is_admin);

            if (isUserAdmin) {
                if (adminUsersCard) adminUsersCard.style.display = "block";
                loadUsersTable();
            } else {
                if (adminUsersCard) adminUsersCard.style.display = "none";
            }

            // Populate Printer Settings Selector Dropdown
            const printerSel = document.getElementById("printer-settings-select");
            if (printerSel) {
                const printersRes = await fetch("/api/printers");
                const printersList = printersRes.ok ? await printersRes.json() : [];
                const curVal = printerSel.value;
                printerSel.innerHTML = '<option value="">-- Оберіть принтер для налаштування --</option>' +
                    printersList.map(p => `<option value="${p.id}">${p.name || p.id} (${p.printer_model || "3D"})</option>`).join("");
                if (curVal && printersList.some(p => p.id === curVal)) {
                    printerSel.value = curVal;
                }
            }
        } catch (e) {
            console.error("Failed loading settings:", e);
        }
    }

    async function loadPrinterSettings(printerId) {
        const formContainer = document.getElementById("printer-settings-form-container");
        if (!printerId) {
            if (formContainer) formContainer.style.display = "none";
            return;
        }
        try {
            const res = await fetch(`/api/printers/${printerId}/settings`);
            if (!res.ok) return;
            const p = await res.json();
            
            if (formContainer) formContainer.style.display = "block";

            const elName = document.getElementById("p-setting-name");
            const elIp = document.getElementById("p-setting-ip");
            const elAc = document.getElementById("p-setting-access-code");
            const elSn = document.getElementById("p-setting-sn");
            const elModel = document.getElementById("p-setting-model");
            const elAms = document.getElementById("p-setting-ams");
            const elMaintInt = document.getElementById("p-setting-maint-interval");
            const elNotify = document.getElementById("p-setting-notify");
            const elMaintVal = document.getElementById("p-setting-maint-counter-val");

            if (elName) elName.value = p.name || "";
            if (elIp) elIp.value = p.ip || "";
            if (elAc) elAc.value = p.accessCode || "";
            if (elSn) elSn.value = p.serialNumber || "";
            if (elModel) elModel.value = p.printer_model || "A1";
            if (elAms) elAms.value = p.ams_enabled === true ? "true" : (p.ams_enabled === false ? "false" : "auto");
            if (elMaintInt) elMaintInt.value = p.maintenance_interval_hours || 100;
            if (elNotify) elNotify.checked = p.notify !== false;
            if (elMaintVal) elMaintVal.textContent = `${(p.maintenance_hours_counter || 0.0).toFixed(1)} год`;
        } catch (e) {
            console.error("Failed loading printer settings:", e);
        }
    }

    async function loadUsersTable() {
        const usersTableBody = document.getElementById("users-table-body");
        const adminUsersCard = document.getElementById("admin-users-card");
        if (!usersTableBody) return;

        try {
            const res = await fetch("/api/users");
            if (!res.ok) {
                if (adminUsersCard) adminUsersCard.style.display = "none";
                usersTableBody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">Потрібні права адміністратора</td></tr>`;
                return;
            }
            const data = await res.json();
            const users = data.users || [];

            if (users.length === 0) {
                usersTableBody.innerHTML = `<tr><td colspan="5" class="text-center">Немає зареєстрованих користувачів</td></tr>`;
                return;
            }

            usersTableBody.innerHTML = users.map(u => {
                const isAdmin = u.role === "ADMIN";
                const isApproved = Boolean(u.approved || u.is_approved);
                const displayName = u.name || u.first_name || `User ${u.user_id}`;
                return `
                    <tr>
                        <td><strong>${escapeHtml(displayName)}</strong></td>
                        <td><code>${escapeHtml(u.user_id)}</code></td>
                        <td><span class="badge ${isAdmin ? 'badge-primary' : 'badge-secondary'}">${u.role}</span></td>
                        <td><span class="badge ${isApproved ? 'badge-success' : 'badge-danger'}">${isApproved ? 'Схвалено ✅' : 'Очікує / Заблоковано ⛔'}</span></td>
                        <td>
                            <button class="btn btn-xs ${isApproved ? 'btn-danger' : 'btn-primary'} toggle-user-access-btn" data-id="${u.user_id}" data-approved="${isApproved ? 'false' : 'true'}">
                                ${isApproved ? 'Скасувати' : 'Схвалити'}
                            </button>
                            ${!isAdmin ? `<button class="btn btn-xs btn-outline-danger delete-user-btn ml-1" data-id="${u.user_id}">🗑️ Видалити</button>` : ''}
                        </td>
                    </tr>`;
            }).join("");

            usersTableBody.querySelectorAll(".toggle-user-access-btn").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const uid = btn.getAttribute("data-id");
                    const nextApproved = btn.getAttribute("data-approved") === "true";
                    try {
                        await fetch("/api/users/access", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ user_id: uid, approved: nextApproved })
                        });
                        loadUsersTable();
                    } catch (err) {
                        alert("Помилка оновлення доступу: " + err);
                    }
                });
            });

            usersTableBody.querySelectorAll(".delete-user-btn").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const uid = btn.getAttribute("data-id");
                    if (!confirm(`Ви впевнені, що хочете остаточно видалити користувача/бота (ID: ${uid})?`)) {
                        return;
                    }
                    try {
                        const delRes = await fetch("/api/users/delete", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ user_id: uid })
                        });
                        if (!delRes.ok) {
                            const errData = await delRes.json();
                            alert("Помилка видалення: " + (errData.error || delRes.statusText));
                            return;
                        }
                        loadUsersTable();
                    } catch (err) {
                        alert("Помилка видалення користувача: " + err);
                    }
                });
            });

        } catch (e) {
            console.error("Failed loading users table:", e);
        }
    }

    // Dynamic WebApp i18n support
    window.setAppLanguage = function(lang) {
        if (!lang || !["uk", "en"].includes(lang.toLowerCase())) lang = "uk";
        lang = lang.toLowerCase();
        localStorage.setItem("app_lang", lang);
        
        const langSelect = document.getElementById("setting-app-language");
        if (langSelect) langSelect.value = lang;

        const dict = {
            uk: {
                nav_printers: "Принтери",
                nav_commercial: "Комерція",
                nav_materials: "Склад",
                nav_history: "Історія",
                nav_settings: "Налаштування",
                farm_status_title: "Стан ферми",
                add_printer_btn: "Додати принтер",
                active_label: "активні",
                filter_all: "Всі",
                filter_running: "Друк 🟢",
                filter_idle: "Готовий ⚪",
                filter_offline: "Офлайн 🔴",
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
                export_csv_btn: "Звіт (CSV)",
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
                th_actions: "Дії",
                loading_users: "Завантаження користувачів...",
                server_farm_status_title: "Стан сервера та ферми",
                sys_uptime_label: "Час безвідмовної роботи:",
                connected_printers_label: "Підключені принтери:",
                rest_api_status_label: "REST API Статус:",
                status_active: "Активний",
            },
            en: {
                nav_printers: "Printers",
                nav_commercial: "Commercial",
                nav_materials: "Stock",
                nav_history: "History",
                nav_settings: "Settings",
                farm_status_title: "Farm Status",
                add_printer_btn: "Add Printer",
                active_label: "active",
                filter_all: "All",
                filter_running: "Printing 🟢",
                filter_idle: "Idle ⚪",
                filter_offline: "Offline 🔴",
                loading_printers: "Loading printers...",
                commercial_title: "Commercial & Pricing",
                new_preset_btn: "New Preset",
                calc_cost_title: "Print Cost Calculation",
                pricing_preset_label: "Pricing Preset",
                loading_presets: "Loading presets...",
                filament_weight_g_label: "Filament Weight (g)",
                print_time_mins_label: "Print Time (mins)",
                total_commercial_price_label: "Final Commercial Price:",
                item_filament: "Filament",
                item_electricity: "Electricity",
                item_depreciation: "Depreciation",
                item_consumables: "Consumables",
                item_prime_cost: "Prime Cost",
                item_margin: "Profit Margin",
                existing_presets_title: "Available Pricing Presets",
                materials_stock_title: "Materials Stock",
                new_spool_btn: "New Spool",
                spools_warehouse_title: "Spools Warehouse",
                history_title: "Analytics & History",
                refresh_btn: "Refresh",
                clear_btn: "Clear",
                export_csv_btn: "Report (CSV)",
                total_jobs_label: "Total Prints",
                total_filament_label: "Filament Used",
                completed_jobs_log: "Completed Print Log",
                th_date: "Date",
                th_printer: "Printer",
                th_model: "Model",
                th_weight_g: "Weight (g)",
                no_history_records: "No history records found",
                settings_title: "Settings & Notifications",
                notification_settings_card: "Notification Preferences",
                notify_start_label: "Print Start Notifications",
                notify_finish_label: "Print Finish Notifications",
                notify_pause_label: "Print Pause Notifications",
                notify_hms_label: "HMS Errors & Alerts",
                notify_remind_clear_label: "Remind to Clear Bed Alert",
                notify_before_end_label: "Notify N mins before finish",
                opt_timer_off: "❌ Disable Timer",
                opt_timer_5: "⏳ 5 mins before finish",
                opt_timer_10: "⏳ 10 mins before finish",
                opt_timer_15: "⏳ 15 mins before finish",
                notify_filament_threshold: "Filament Low Threshold",
                opt_limit_off: "❌ Disable Limit",
                opt_limit_50: "📦 Less than 50g",
                opt_limit_100: "📦 Less than 100g",
                opt_limit_200: "📦 Less than 200g",
                lang_select_label: "Language / Мова",
                save_settings_btn: "Save Settings",
                save_success: "✅ Settings saved successfully!",
                user_access_control_title: "User Access Control (Admin)",
                th_user: "User",
                th_role: "Role",
                th_access_status: "Access Status",
                th_actions: "Actions",
                loading_users: "Loading users...",
                server_farm_status_title: "Server & Farm Status",
                sys_uptime_label: "Server Uptime:",
                connected_printers_label: "Connected Printers:",
                rest_api_status_label: "REST API Status:",
                status_active: "Active",
            }
        }[lang];

        document.querySelectorAll("[data-i18n]").forEach(el => {
            const k = el.getAttribute("data-i18n");
            if (dict[k]) el.innerText = dict[k];
        });
    };

    // Load initial language from localStorage
    const savedLang = localStorage.getItem("app_lang") || "uk";
    window.setAppLanguage(savedLang);

    document.getElementById("setting-app-language")?.addEventListener("change", async (e) => {
        const language = e.target.value;
        window.setAppLanguage(language);
        try {
            await fetch("/api/user/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ language })
            });
        } catch (err) {
            console.error("Failed saving language preference:", err);
        }
    });

    async function loadPrinterSettings(printerId) {
        const container = document.getElementById("printer-settings-form-container");
        if (!printerId) {
            if (container) container.style.display = "none";
            return;
        }
        try {
            const res = await fetch(`/api/printers/${printerId}/settings`);
            if (!res.ok) return;
            const p = await res.json();

            if (container) container.style.display = "block";

            if (document.getElementById("p-setting-name")) document.getElementById("p-setting-name").value = p.name || "";
            if (document.getElementById("p-setting-ip")) document.getElementById("p-setting-ip").value = p.ip || "";
            if (document.getElementById("p-setting-access-code")) document.getElementById("p-setting-access-code").value = p.accessCode || "";
            if (document.getElementById("p-setting-sn")) document.getElementById("p-setting-sn").value = p.serialNumber || "";
            if (document.getElementById("p-setting-model")) document.getElementById("p-setting-model").value = p.printer_model || "A1";
            if (document.getElementById("p-setting-ams")) document.getElementById("p-setting-ams").value = p.ams_enabled === true ? "true" : (p.ams_enabled === false ? "false" : "auto");
            if (document.getElementById("p-setting-maint-interval")) document.getElementById("p-setting-maint-interval").value = p.maintenance_interval_hours || 100;
            if (document.getElementById("p-setting-maint-counter-val")) document.getElementById("p-setting-maint-counter-val").textContent = `${(p.maintenance_hours_counter || 0.0).toFixed(1)} год`;

            const n = typeof p.notify === "object" && p.notify !== null ? p.notify : {};
            const isAllOn = p.notify !== false;

            if (document.getElementById("p-setting-notify-start")) document.getElementById("p-setting-notify-start").checked = n.start ?? isAllOn;
            if (document.getElementById("p-setting-notify-finish")) document.getElementById("p-setting-notify-finish").checked = n.finish ?? isAllOn;
            if (document.getElementById("p-setting-notify-pause")) document.getElementById("p-setting-notify-pause").checked = n.pause ?? isAllOn;
            if (document.getElementById("p-setting-notify-hms")) document.getElementById("p-setting-notify-hms").checked = n.hms ?? isAllOn;
            if (document.getElementById("p-setting-notify-remind-clear")) document.getElementById("p-setting-notify-remind-clear").checked = n.remind_clear ?? isAllOn;
            if (document.getElementById("p-setting-notify-min-time")) document.getElementById("p-setting-notify-min-time").value = n.min_time_to_end ?? 0;
            if (document.getElementById("p-setting-notify-min-filament")) document.getElementById("p-setting-notify-min-filament").value = n.min_filament ?? 0;
        } catch (e) {
            console.error("Failed loading printer settings:", e);
        }
    }
    window.loadPrinterSettings = loadPrinterSettings;

    // Per-Printer Individual Settings Event Handlers
    document.getElementById("printer-settings-select")?.addEventListener("change", (e) => {
        loadPrinterSettings(e.target.value);
    });

    document.getElementById("save-printer-settings-btn")?.addEventListener("click", async () => {
        triggerHaptic("medium");
        const printerId = document.getElementById("printer-settings-select")?.value;
        if (!printerId) return;

        const notifyObj = {
            start: document.getElementById("p-setting-notify-start")?.checked ?? true,
            finish: document.getElementById("p-setting-notify-finish")?.checked ?? true,
            pause: document.getElementById("p-setting-notify-pause")?.checked ?? true,
            hms: document.getElementById("p-setting-notify-hms")?.checked ?? true,
            remind_clear: document.getElementById("p-setting-notify-remind-clear")?.checked ?? true,
            min_time_to_end: parseInt(document.getElementById("p-setting-notify-min-time")?.value || 0),
            min_filament: parseInt(document.getElementById("p-setting-notify-min-filament")?.value || 0),
        };

        const payload = {
            name: document.getElementById("p-setting-name")?.value || "",
            ip: document.getElementById("p-setting-ip")?.value || "",
            accessCode: document.getElementById("p-setting-access-code")?.value || "",
            serialNumber: document.getElementById("p-setting-sn")?.value || "",
            printer_model: document.getElementById("p-setting-model")?.value || "A1",
            ams_enabled: document.getElementById("p-setting-ams")?.value === "true" ? true : (document.getElementById("p-setting-ams")?.value === "false" ? false : "auto"),
            maintenance_interval_hours: parseInt(document.getElementById("p-setting-maint-interval")?.value || 100),
            notify: notifyObj,
        };

        try {
            const res = await fetch(`/api/printers/${printerId}/settings`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                alert("✅ Налаштування принтера успішно збережено!");
                loadPrinterSettings(printerId);
            } else {
                const err = await res.json();
                alert("⚠️ Помилка збереження: " + (err.error || "Невідома помилка"));
            }
        } catch (e) {
            console.error("Failed saving printer settings:", e);
            alert("⚠️ Помилка зв'язку із сервером: " + e);
        }
    });

    document.getElementById("p-setting-reset-maint-btn")?.addEventListener("click", async () => {
        triggerHaptic("heavy");
        const printerId = document.getElementById("printer-settings-select")?.value;
        if (!printerId) return;

        if (!confirm("Ви дійсно бажаєте скинути лічильник напрацьованих годин для цього принтера?")) return;

        try {
            const res = await fetch(`/api/printers/${printerId}/settings`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ reset_maintenance: true })
            });
            if (res.ok) {
                alert("✅ Лічильник обслуговування скинуто на 0.0 год!");
                loadPrinterSettings(printerId);
            }
        } catch (e) {
            console.error("Failed resetting maintenance counter:", e);
        }
    });

    async function openPrinterSettingsModal(pId) {
        triggerHaptic("medium");
        const modal = document.getElementById("printer-settings-modal");
        if (!modal || !pId) return;

        try {
            const res = await fetch(`/api/printers/${pId}/settings`);
            if (!res.ok) return;
            const p = await res.json();

            document.getElementById("ps-modal-printer-id").value = pId;
            document.getElementById("ps-modal-title").textContent = `Налаштування: ${p.name || pId}`;
            document.getElementById("ps-modal-name").value = p.name || "";
            document.getElementById("ps-modal-ip").value = p.ip || "";
            document.getElementById("ps-modal-access-code").value = p.accessCode || "";
            document.getElementById("ps-modal-sn").value = p.serialNumber || "";
            document.getElementById("ps-modal-model").value = p.printer_model || "A1";
            document.getElementById("ps-modal-ams").value = p.ams_enabled === true ? "true" : (p.ams_enabled === false ? "false" : "auto");
            document.getElementById("ps-modal-maint-interval").value = p.maintenance_interval_hours || 100;
            document.getElementById("ps-modal-maint-counter").textContent = `${(p.maintenance_hours_counter || 0.0).toFixed(1)} год`;

            const n = typeof p.notify === "object" && p.notify !== null ? p.notify : {};
            const isAllOn = p.notify !== false;

            if (document.getElementById("ps-modal-notify-start")) document.getElementById("ps-modal-notify-start").checked = n.start ?? isAllOn;
            if (document.getElementById("ps-modal-notify-finish")) document.getElementById("ps-modal-notify-finish").checked = n.finish ?? isAllOn;
            if (document.getElementById("ps-modal-notify-pause")) document.getElementById("ps-modal-notify-pause").checked = n.pause ?? isAllOn;
            if (document.getElementById("ps-modal-notify-hms")) document.getElementById("ps-modal-notify-hms").checked = n.hms ?? isAllOn;
            if (document.getElementById("ps-modal-notify-remind-clear")) document.getElementById("ps-modal-notify-remind-clear").checked = n.remind_clear ?? isAllOn;
            if (document.getElementById("ps-modal-notify-min-time")) document.getElementById("ps-modal-notify-min-time").value = n.min_time_to_end ?? 0;
            if (document.getElementById("ps-modal-notify-min-filament")) document.getElementById("ps-modal-notify-min-filament").value = n.min_filament ?? 0;

            modal.classList.add("active");
        } catch (e) {
            console.error("Failed opening printer settings modal:", e);
        }
    }
    window.openPrinterSettingsModal = openPrinterSettingsModal;

    document.getElementById("close-printer-settings-modal")?.addEventListener("click", () => {
        document.getElementById("printer-settings-modal")?.classList.remove("active");
    });

    document.getElementById("btn-printer-settings")?.addEventListener("click", () => {
        const modalControl = document.getElementById("printer-modal");
        if (modalControl) modalControl.classList.remove("active");
        if (selectedPrinterId) {
            openPrinterSettingsModal(selectedPrinterId);
        }
    });

    document.getElementById("save-printer-settings-modal-btn")?.addEventListener("click", async () => {
        triggerHaptic("medium");
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
            ams_enabled: document.getElementById("ps-modal-ams")?.value === "true" ? true : (document.getElementById("ps-modal-ams")?.value === "false" ? false : "auto"),
            maintenance_interval_hours: parseInt(document.getElementById("ps-modal-maint-interval")?.value || 100),
            notify: notifyObj,
        };

        try {
            const res = await fetch(`/api/printers/${pId}/settings`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                alert("✅ Налаштування принтера успішно збережено!");
                document.getElementById("printer-settings-modal")?.classList.remove("active");
                fetchPrinters();
            } else {
                const err = await res.json();
                alert("⚠️ Помилка збереження: " + (err.error || "Невідома помилка"));
            }
        } catch (e) {
            console.error("Failed saving printer settings via modal:", e);
            alert("⚠️ Помилка зв'язку із сервером: " + e);
        }
    });

    document.getElementById("ps-modal-reset-maint-btn")?.addEventListener("click", async () => {
        triggerHaptic("heavy");
        const pId = document.getElementById("ps-modal-printer-id")?.value;
        if (!pId) return;

        if (!confirm("Ви дійсно бажаєте скинути лічильник напрацьованих годин для цього принтера?")) return;

        try {
            const res = await fetch(`/api/printers/${pId}/settings`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ reset_maintenance: true })
            });
            if (res.ok) {
                alert("✅ Лічильник обслуговування скинуто на 0.0 год!");
                openPrinterSettingsModal(pId);
            }
        } catch (e) {
            console.error("Failed resetting maintenance counter:", e);
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
            filePrintersList.innerHTML = printers.map(p => {
                let badgeText = '✅ Сумісний';
                if (!p.compatible) {
                    badgeText = p.reason_type === 'FILAMENT' ? '🛑 Несумісність пластику' : '🛑 Несумісна модель';
                }
                return `
                <div class="spool-item mb-2" style="flex-direction:column; align-items:stretch;">
                    <div class="d-flex justify-content-between align-items-center">
                        <div class="spool-left">
                            <i class="fa-solid fa-print ${p.state === 'RUNNING' ? 'color-green' : 'color-purple'}" style="font-size:20px;"></i>
                            <div class="spool-details">
                                <h4>${escapeHtml(p.name)}</h4>
                                <p>Статус: <strong>${p.state}</strong> | ${badgeText}</p>
                            </div>
                        </div>
                        <button class="btn btn-sm ${p.compatible ? 'btn-success' : 'btn-outline-danger'} btn-start-print-job" data-id="${p.id}" ${p.state === 'RUNNING' ? 'disabled' : ''}>
                            ${p.state === 'RUNNING' ? 'Зайнятий' : (p.compatible ? '🚀 Друк' : '🛑 Заблокировано')}
                        </button>
                    </div>
                    ${!p.compatible ? `<div class="mt-2 p-2" style="background:rgba(239,68,68,0.15); border:1px solid rgba(239,68,68,0.4); border-radius:6px; font-size:12px; color:#fca5a5;">${escapeHtml(p.reason.replace(/<[^>]*>/g, ""))}</div>` : ''}
                </div>
            `}).join("");

            document.querySelectorAll(".btn-start-print-job").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const printerId = btn.getAttribute("data-id");
                    const targetP = (uploadedFileData.printers || []).find(x => x.id === printerId);
                    if (targetP && !targetP.compatible) {
                        alert(targetP.reason.replace(/<[^>]*>/g, ""));
                        return;
                    }
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

    // ----------------------------------------------------
    // PARTS WAREHOUSE MANAGEMENT
    // ----------------------------------------------------
    let partsData = {};

    function formatTimeMins(mins) {
        if (!mins || mins <= 0) return "—";
        const h = Math.floor(mins / 60);
        const m = mins % 60;
        if (h > 0 && m > 0) return `${h} год ${m} хв`;
        if (h > 0) return `${h} год`;
        return `${m} хв`;
    }

    async function triggerPrintPartById(id) {
        const part = partsData[id];
        if (!part) return;

        if (!part.three_mf) {
            alert("⚠️ Для цієї деталі ще не завантажено файл .3mf!");
            return;
        }

        if (!printersData || printersData.length === 0) {
            alert("⚠️ Немає підключених принтерів у фермі!");
            return;
        }

        const printerChoices = printersData.map((p, idx) => {
            const targetM = part.printer_model || '';
            const partFilament = part.filament_type || '';
            const printerFilament = p.filament_type || '';
            let isComp = true;
            let reasons = [];

            if (targetM && targetM !== 'Unknown') {
                const targetCode = getBambuModelCode(targetM);
                const printerCode = getBambuModelCode(p.name);
                if (targetCode !== 'UNKNOWN' && printerCode !== 'UNKNOWN' && targetCode !== printerCode) {
                    isComp = false;
                    reasons.push(`нарізано для ${targetM}`);
                }
            }

            if (partFilament && printerFilament && printerFilament !== 'Невизначено') {
                const normPartFil = normalizeFilamentName(partFilament);
                const normPrinterFil = normalizeFilamentName(printerFilament);
                if (normPartFil && normPrinterFil && normPartFil !== normPrinterFil) {
                    isComp = false;
                    reasons.push(`пластик: ${printerFilament} vs ${partFilament}`);
                }
            }

            const compTag = isComp ? ' ✅ СУМІСНИЙ' : ` 🛑 НЕСУМІСНИЙ (${reasons.join('; ')})`;
            return `${idx + 1}. ${p.name} (${p.gcode_state || 'IDLE'})${compTag}`;
        }).join("\n");

        const inputIdx = prompt(`🚀 Оберіть номер принтера для запуску друку деталі "${part.name}":\n\n${printerChoices}\n\nВведіть номер (1-${printersData.length}):`);
        if (!inputIdx) return;

        const chosenIndex = parseInt(inputIdx.trim(), 10) - 1;
        if (isNaN(chosenIndex) || chosenIndex < 0 || chosenIndex >= printersData.length) {
            alert("⚠️ Некоректний номер принтера.");
            return;
        }

        const selectedPrinter = printersData[chosenIndex];

        // Strict compatibility blocking
        const targetM = part.printer_model || '';
        const partFilament = part.filament_type || '';
        const printerFilament = selectedPrinter.filament_type || '';

        if (targetM && targetM !== 'Unknown') {
            const targetCode = getBambuModelCode(targetM);
            const printerCode = getBambuModelCode(selectedPrinter.name);
            if (targetCode !== 'UNKNOWN' && printerCode !== 'UNKNOWN' && targetCode !== printerCode) {
                alert(`🛑 Помилка сумісності моделі принтера!\nДеталь нарізано для ${targetM}, а принтер ${selectedPrinter.name} (${printerCode}) не є сумісним.`);
                return;
            }
        }

        if (partFilament && printerFilament && printerFilament !== 'Невизначено') {
            const normPartFil = normalizeFilamentName(partFilament);
            const normPrinterFil = normalizeFilamentName(printerFilament);
            if (normPartFil && normPrinterFil && normPartFil !== normPrinterFil) {
                alert(`🛑 Помилка сумісності пластику!\nДеталь вимагає пластик "${partFilament}", а на принтері ${selectedPrinter.name} встановлено "${printerFilament}".`);
                return;
            }
        }

        try {
            const res = await fetch(`/api/parts/${part.id}/print/${selectedPrinter.id}`, {
                method: "POST"
            });
            const result = await res.json();
            if (res.ok && result.status === "ok") {
                alert(`🚀 Друк деталі "${part.name}" успішно запущено на принтері [${selectedPrinter.name}]!`);
            } else {
                alert(`⚠️ Помилка запуску: ${result.error || `HTTP ${res.status}`}`);
            }
        } catch (err) {
            console.error("Print part error:", err);
            alert("⚠️ Помилка зв'язку при запуску друку.");
        }
    }

    window.showPartDetails = function(partId) {
        const cache = partsData || window._partsCache || {};
        const part = cache ? cache[partId] : null;
        if (!part) return;

        const modal = document.getElementById("part-details-modal");
        if (!modal) return;

        const titleEl = document.getElementById("part-details-title");
        const contentEl = document.getElementById("part-details-content");
        const downloadBtn = document.getElementById("part-details-download-btn");
        const printBtn = document.getElementById("part-details-print-btn");

        if (titleEl) {
            titleEl.innerHTML = `<i class="fa-solid fa-puzzle-piece color-green me-2"></i> ${escapeHtml(part.name)}`;
        }

        const imageSrc = part.image && (part.image.startsWith("http") || part.image.startsWith("/")) ? part.image : "";
        const count = parseInt(part.count || part.quantity || 0, 10);
        const weightDisplay = part.weight_g ? `${part.weight_g} g` : "Не вказано в .3mf";
        const timeDisplay = part.time_mins ? formatTimeMins(part.time_mins) : "Не вказано в .3mf";
        const printerModelDisplay = part.printer_model && part.printer_model !== "Unknown" ? part.printer_model : "Довільний принтер";
        const filamentTypeDisplay = part.filament_type || "PLA";
        const threeMfName = part.three_mf ? escapeHtml(part.three_mf_name || part.three_mf) : "Файл не завантажено";

        let html = `
            <div class="part-details-img-container">
                ${imageSrc
                    ? `<img src="${imageSrc}" class="part-details-full-img" alt="${escapeHtml(part.name)}">`
                    : `<div class="part-details-no-img"><i class="fa-solid fa-cube"></i><span>Немає зображення деталі</span></div>`
                }
            </div>

            <div class="part-details-grid">
                <div class="part-detail-badge">
                    <span class="part-detail-label"><i class="fa-solid fa-weight-hanging color-green"></i> Вага моделі</span>
                    <span class="part-detail-value">${escapeHtml(weightDisplay)}</span>
                </div>

                <div class="part-detail-badge">
                    <span class="part-detail-label"><i class="fa-solid fa-clock color-blue"></i> Час друку</span>
                    <span class="part-detail-value">${escapeHtml(timeDisplay)}</span>
                </div>

                <div class="part-detail-badge">
                    <span class="part-detail-label"><i class="fa-solid fa-print color-purple"></i> Модель принтера</span>
                    <span class="part-detail-value">${escapeHtml(printerModelDisplay)}</span>
                </div>

                <div class="part-detail-badge">
                    <span class="part-detail-label"><i class="fa-solid fa-compact-disc color-amber"></i> Тип пластику</span>
                    <span class="part-detail-value">${escapeHtml(filamentTypeDisplay)}</span>
                </div>

                <div class="part-detail-badge">
                    <span class="part-detail-label"><i class="fa-solid fa-cubes color-cyan"></i> Кількість в наявності</span>
                    <span class="part-detail-value text-info">${count} шт</span>
                </div>

                <div class="part-detail-badge">
                    <span class="part-detail-label"><i class="fa-solid fa-file-code color-orange"></i> Файл .3mf</span>
                    <span class="part-detail-value" style="font-size: 0.85rem; word-break: break-all;">${threeMfName}</span>
                </div>
            </div>
        `;

        if (contentEl) contentEl.innerHTML = html;

        if (downloadBtn) {
            if (part.three_mf) {
                downloadBtn.style.display = "inline-flex";
                downloadBtn.onclick = async () => {
                    try {
                        downloadBtn.disabled = true;
                        downloadBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Завантаження...';
                        const res = await fetch(`/api/parts/${part.id}/download_3mf`);
                        if (!res.ok) {
                            const errData = await res.json().catch(() => ({}));
                            alert(`⚠️ Помилка завантаження: ${errData.error || `HTTP ${res.status}`}`);
                            return;
                        }
                        const blob = await res.blob();
                        const blobUrl = URL.createObjectURL(blob);
                        const a = document.createElement("a");
                        a.href = blobUrl;
                        a.download = `${(part.name || 'model').replace(/\s+/g, '_')}.3mf`;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        URL.revokeObjectURL(blobUrl);
                    } catch (e) {
                        console.error("Download 3mf error:", e);
                        alert("⚠️ Не вдалося завантажити файл .3mf");
                    } finally {
                        downloadBtn.disabled = false;
                        downloadBtn.innerHTML = '<i class="fa-solid fa-file-arrow-down"></i> Завантажити .3mf';
                    }
                };
            } else {
                downloadBtn.style.display = "none";
            }
        }

        if (printBtn) {
            printBtn.onclick = () => {
                modal.classList.remove("active");
                triggerPrintPartById(part.id);
            };
        }

        if (typeof triggerHaptic === "function") triggerHaptic("medium");
        modal.classList.add("active");
    };

    window.closePartDetailsModal = function() {
        const modal = document.getElementById("part-details-modal");
        if (modal) modal.classList.remove("active");
    };

    async function loadParts() {
        const partsListEl = document.getElementById("parts-list");
        const partsBadgeEl = document.getElementById("parts-summary-badge");
        if (!partsListEl) return;

        try {
            const res = await fetch("/api/parts");
            if (!res.ok) throw new Error("Failed fetching parts");
            partsData = await res.json();
            window._partsCache = partsData;

            const partSearchInput = document.getElementById("part-search-input");
            const partSearchClearBtn = document.getElementById("part-search-clear-btn");
            const searchQuery = partSearchInput ? partSearchInput.value.trim().toLowerCase() : "";

            if (partSearchClearBtn) {
                partSearchClearBtn.style.display = searchQuery ? "flex" : "none";
            }

            const allKeys = Object.keys(partsData);
            let totalCount = 0;

            allKeys.forEach(k => {
                const cnt = parseInt(partsData[k].count || partsData[k].quantity || 0, 10);
                totalCount += cnt;
            });

            if (partsBadgeEl) {
                partsBadgeEl.textContent = `${totalCount} шт`;
            }

            const keys = allKeys.filter(id => {
                if (!searchQuery) return true;
                const p = partsData[id];
                const nameMatch = p.name && p.name.toLowerCase().includes(searchQuery);
                const modelMatch = p.printer_model && p.printer_model.toLowerCase().includes(searchQuery);
                return nameMatch || modelMatch;
            });

            if (keys.length === 0) {
                partsListEl.innerHTML = searchQuery ? `
                    <div class="empty-state p-4 text-center">
                        <i class="fa-solid fa-magnifying-glass color-amber" style="font-size: 2.5rem;"></i>
                        <p class="mt-2 text-muted">За запитом "${escapeHtml(searchQuery)}" деталей не знайдено.</p>
                    </div>
                ` : `
                    <div class="empty-state p-4 text-center">
                        <i class="fa-solid fa-puzzle-piece color-amber" style="font-size: 2.5rem;"></i>
                        <p class="mt-2 text-muted">Склад деталей порожній. Натисніть "+ Нова деталь", щоб додати першу деталь.</p>
                    </div>
                `;
                return;
            }

            let html = "";
            keys.forEach(id => {
                const part = partsData[id];
                const count = parseInt(part.count || part.quantity || 0, 10);
                const threeMf = part.three_mf ? escapeHtml(part.three_mf_name || "Файл .3mf") : "";
                const imageSrc = part.image && (part.image.startsWith("http") || part.image.startsWith("/")) ? part.image : "";
                const pModelBadge = part.printer_model && part.printer_model !== 'Unknown'
                    ? `<span class="badge badge-outline text-info border-info ms-2" style="font-size: 0.75rem;"><i class="fa-solid fa-print"></i> ${escapeHtml(part.printer_model)}</span>`
                    : '';

                html += `
                    <div class="spool-item-card part-item-card glass-card mb-3 p-3">
                        <div class="part-card-header">
                            <div class="part-card-main-info" data-id="${part.id}" title="Натисніть для перегляду деталей моделі">
                                ${imageSrc
                                    ? `<img src="${imageSrc}" class="part-preview-thumb" alt="${escapeHtml(part.name)}">`
                                    : `<div class="part-preview-placeholder"><i class="fa-solid fa-cube color-green fs-5"></i></div>`
                                }
                                <div class="part-card-title-group">
                                    <div class="part-card-title-row">
                                        <h4 class="m-0 text-light fs-6 fw-bold">
                                            <i class="fa-solid fa-puzzle-piece color-green me-1"></i> ${escapeHtml(part.name)}
                                        </h4>
                                        ${pModelBadge}
                                    </div>
                                    <small class="text-muted" style="font-size: 0.72rem;"><i class="fa-solid fa-circle-info"></i> Натисніть для детальної інформації</small>
                                </div>
                            </div>
                            <div class="part-card-actions">
                                <button class="icon-btn btn-edit-part" data-id="${part.id}" title="Редагувати">
                                    <i class="fa-solid fa-pen-to-square"></i>
                                </button>
                                <button class="icon-btn btn-delete-part text-danger" data-id="${part.id}" title="Видалити">
                                    <i class="fa-solid fa-trash"></i>
                                </button>
                            </div>
                        </div>

                        ${threeMf ? `
                            <div class="part-card-file-row" data-id="${part.id}" style="cursor: pointer;" title="Натисніть для детальної інформації">
                                <i class="fa-solid fa-file"></i>
                                <span><strong>.3mf:</strong> ${threeMf}</span>
                            </div>
                        ` : ''}

                        <div class="part-card-footer">
                            <button class="btn btn-sm btn-primary btn-print-part" data-id="${part.id}">
                                <i class="fa-solid fa-rocket"></i> Кинути на друк
                            </button>
                            <div class="part-card-qty-counter">
                                <button class="btn btn-sm btn-outline btn-part-qty-dec" data-id="${part.id}">-</button>
                                <strong class="fs-6 px-1 text-info">${count} шт</strong>
                                <button class="btn btn-sm btn-outline btn-part-qty-inc" data-id="${part.id}">+</button>
                            </div>
                        </div>
                    </div>
                `;
            });

            partsListEl.innerHTML = html;

            document.querySelectorAll(".part-card-main-info, .part-card-file-row").forEach(el => {
                el.addEventListener("click", (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const id = el.getAttribute("data-id");
                    if (id) window.showPartDetails(id);
                });
            });

            document.querySelectorAll(".btn-print-part").forEach(b => {
                b.addEventListener("click", (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const id = b.getAttribute("data-id");
                    if (id) triggerPrintPartById(id);
                });
            });

            document.querySelectorAll(".btn-edit-part").forEach(b => {
                b.addEventListener("click", (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const btn = e.currentTarget || e.target.closest(".btn-edit-part");
                    const id = btn ? btn.getAttribute("data-id") : null;
                    if (id && partsData[id]) window.openAddPartModal(partsData[id]);
                });
            });

            document.querySelectorAll(".btn-delete-part").forEach(b => {
                b.addEventListener("click", async (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const btn = e.target.closest(".btn-delete-part");
                    const id = btn ? btn.getAttribute("data-id") : null;
                    if (id && confirm("Видалити цю деталь зі складу?")) {
                        await fetch(`/api/parts/${id}`, { method: "DELETE" });
                        loadParts();
                    }
                });
            });

            document.querySelectorAll(".btn-part-qty-dec").forEach(b => {
                b.addEventListener("click", async (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const btn = e.target.closest(".btn-part-qty-dec");
                    const id = btn ? btn.getAttribute("data-id") : null;
                    if (id && partsData[id]) {
                        const current = parseInt(partsData[id].count || partsData[id].quantity || 0, 10);
                        const newCount = Math.max(0, current - 1);
                        await savePartApi({ ...partsData[id], count: newCount, quantity: newCount });
                        loadParts();
                    }
                });
            });

            document.querySelectorAll(".btn-part-qty-inc").forEach(b => {
                b.addEventListener("click", async (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const btn = e.target.closest(".btn-part-qty-inc");
                    const id = btn ? btn.getAttribute("data-id") : null;
                    if (id && partsData[id]) {
                        const current = parseInt(partsData[id].count || partsData[id].quantity || 0, 10);
                        const newCount = current + 1;
                        await savePartApi({ ...partsData[id], count: newCount, quantity: newCount });
                        loadParts();
                    }
                });
            });

        } catch (e) {
            console.error("Error loading parts:", e);
        }
    }

    async function savePartApi(partData) {
        try {
            const res = await fetch("/api/parts", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(partData)
            });
            return await res.json();
        } catch (e) {
            console.error("Failed saving part:", e);
            return { error: String(e) };
        }
    }

    window.editPartModal = function(id) {
        const cache = window._partsCache || partsData || {};
        if (cache && cache[id]) {
            window.openAddPartModal(cache[id]);
        } else {
            window.openAddPartModal();
        }
    };

    // Direct Image Upload Listener in Modal
    const partImageFileInput = document.getElementById("part-image-file-input");
    if (partImageFileInput) {
        partImageFileInput.addEventListener("change", async (e) => {
            const file = e.target.files ? e.target.files[0] : null;
            if (!file) return;

            const isImageExt = /\.(jpg|jpeg|png|webp|gif)$/i.test(file.name);
            if (!file.type.startsWith("image/") && !isImageExt) {
                alert("⚠️ Помилка! Файл зображення повинен бути у форматі JPG, PNG, WEBP або GIF!");
                partImageFileInput.value = "";
                return;
            }

            const imageInput = document.getElementById("part-image-input");
            const previewWrap = document.getElementById("part-image-preview-wrap");
            const previewImg = document.getElementById("part-image-preview");

            try {
                const formData = new FormData();
                formData.append("file", file);

                const res = await fetch("/api/files/upload_image", {
                    method: "POST",
                    body: formData
                });

                const data = await res.json();
                if (res.ok && data.image_url) {
                    if (imageInput) imageInput.value = data.image_url;
                    if (previewImg) previewImg.src = data.image_url;
                    if (previewWrap) previewWrap.style.display = "block";
                    triggerHaptic("medium");
                } else {
                    alert(`⚠️ Помилка завантаження фото: ${data.error || 'Невдала спроба'}`);
                }
            } catch (err) {
                console.error("Image Upload error:", err);
                alert("⚠️ Не вдалося завантажити фото");
            }
        });
    }

    // Direct .3mf File Upload Listener in Modal
    const part3mfFileInput = document.getElementById("part-3mf-file-input");
    if (part3mfFileInput) {
        part3mfFileInput.addEventListener("change", async (e) => {
            const file = e.target.files ? e.target.files[0] : null;
            if (!file) return;

            const detectedModelEl = document.getElementById("part-detected-model");
            const threeMfInput = document.getElementById("part-3mf-input");

            if (!file.name.toLowerCase().endsWith(".3mf")) {
                alert("⚠️ Помилка! Файл для друку повинен бути у форматі .3mf!");
                part3mfFileInput.value = "";
                if (detectedModelEl) detectedModelEl.style.display = "none";
                return;
            }

            if (detectedModelEl) {
                detectedModelEl.textContent = "⏳ Зчитування метаданих файлу .3mf...";
                detectedModelEl.style.display = "block";
            }

            try {
                const formData = new FormData();
                formData.append("file", file);

                const res = await fetch("/api/files/upload", {
                    method: "POST",
                    body: formData
                });

                const data = await res.json();
                if (res.ok && data.file_token) {
                    if (threeMfInput) threeMfInput.value = data.file_token;
                    if (detectedModelEl) {
                        detectedModelEl.textContent = `✅ Файл розпізнано! Принтер: ${data.printer_model || 'Bambu Lab'}`;
                        detectedModelEl.style.display = "block";
                    }
                    triggerHaptic("medium");
                } else {
                    alert(`⚠️ Помилка завантаження файлу: ${data.error || 'Недійсний .3mf файл'}`);
                    if (detectedModelEl) detectedModelEl.style.display = "none";
                }
            } catch (err) {
                console.error(".3mf Upload error:", err);
                alert("⚠️ Не вдалося завантажити файл .3mf");
                if (detectedModelEl) detectedModelEl.style.display = "none";
            }
        });
    }

    const partSearchInput = document.getElementById("part-search-input");
    const partSearchClearBtn = document.getElementById("part-search-clear-btn");
    if (partSearchInput) {
        partSearchInput.addEventListener("input", () => {
            loadParts();
        });
    }
    if (partSearchClearBtn) {
        partSearchClearBtn.addEventListener("click", () => {
            if (partSearchInput) partSearchInput.value = "";
            loadParts();
        });
    }

    const addPartBtn = document.getElementById("add-part-btn");
    if (addPartBtn) {
        addPartBtn.addEventListener("click", (e) => {
            if (e) {
                e.preventDefault();
                e.stopPropagation();
            }
            window.openAddPartModal();
        });
    }

    const closePartDetailsBtn = document.getElementById("close-part-details-modal-btn");
    if (closePartDetailsBtn) {
        closePartDetailsBtn.addEventListener("click", (e) => {
            if (e) {
                e.preventDefault();
                e.stopPropagation();
            }
            window.closePartDetailsModal();
        });
    }

    const partDetailsModal = document.getElementById("part-details-modal");
    if (partDetailsModal) {
        partDetailsModal.addEventListener("click", (e) => {
            if (e.target === partDetailsModal) {
                window.closePartDetailsModal();
            }
        });
    }

    const closeAddPartModalBtn = document.getElementById("close-add-part-modal");
    if (closeAddPartModalBtn) {
        closeAddPartModalBtn.addEventListener("click", () => {
            const modal = document.getElementById("add-part-modal");
            if (modal) modal.classList.remove("active");
        });
    }

    const cancelPartSubmitBtn = document.getElementById("cancel-part-submit");
    if (cancelPartSubmitBtn) {
        cancelPartSubmitBtn.addEventListener("click", () => {
            const modal = document.getElementById("add-part-modal");
            if (modal) modal.classList.remove("active");
        });
    }

    const savePartSubmitBtn = document.getElementById("save-part-submit");
    if (savePartSubmitBtn) {
        savePartSubmitBtn.addEventListener("click", async () => {
            const editIdInput = document.getElementById("edit-part-id");
            const nameInput = document.getElementById("part-name-input");
            const imageInput = document.getElementById("part-image-input");
            const countInput = document.getElementById("part-count-input");
            const threeMfInput = document.getElementById("part-3mf-input");

            const name = nameInput ? nameInput.value.trim() : "";
            if (!name) {
                alert("⚠️ Помилка! Назва деталі не може бути порожньою!");
                if (nameInput) nameInput.focus();
                return;
            }

            const rawCount = countInput ? countInput.value.trim() : "";
            if (rawCount === "" || isNaN(rawCount) || parseInt(rawCount, 10) < 0) {
                alert("⚠️ Помилка! Кількість повинна бути цілим додатним числом (наприклад: 1, 5, 10)!");
                if (countInput) countInput.focus();
                return;
            }
            const cnt = parseInt(rawCount, 10);

            const partData = {
                id: editIdInput ? editIdInput.value : "",
                name: name,
                image: imageInput ? imageInput.value.trim() : "",
                count: cnt,
                quantity: cnt,
                three_mf: threeMfInput ? threeMfInput.value.trim() : ""
            };

            triggerHaptic("medium");
            savePartSubmitBtn.disabled = true;
            savePartSubmitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Збереження...';

            try {
                const res = await savePartApi(partData);
                if (res && res.status === "ok") {
                    const modal = document.getElementById("add-part-modal");
                    if (modal) modal.classList.remove("active");
                    await loadParts();
                } else {
                    alert(`⚠️ Помилка збереження деталі: ${res?.error || "Невідома помилка"}`);
                }
            } catch (err) {
                console.error("Save part submit error:", err);
                alert("⚠️ Помилка зв'язку при збереженні деталі.");
            } finally {
                savePartSubmitBtn.disabled = false;
                savePartSubmitBtn.innerHTML = '💾 Зберегти деталь';
            }
        });
    }

    refreshBtn.addEventListener("click", () => {
        triggerHaptic("light");
        fetchPrinters();
    });

    // Initial Load & Fail-Safe Polling Loop (Runs always every 3s)
    fetchPrinters();
    loadHistory();
    pollInterval = setInterval(fetchPrinters, 3000);
    initSSEStream();
});
