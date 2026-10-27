/**
 * 3D Farm Manager - Materials Warehouse & Spools Module
 */

import { escapeHtml, triggerHaptic, renderVisualSpoolSvg, evaluateMathExpression } from "./utils.js";
import { showToast } from "./modals.js";
import { state } from "./state.js";
import {
    fetchPrintersApi,
    fetchSpoolsApi,
    saveSpoolApi,
    deleteSpoolApi,
    mountSpoolApi,
    unmountSpoolApi,
    controlPrinterApi,
    fetchSpoolMovementsApi,
    getMovementsPdfExportUrl
} from "./api.js";

export async function loadMaterials() {
    const spoolsList = document.getElementById("spools-list");
    if (spoolsList && (!state.spools || Object.keys(state.spools).length === 0)) {
        spoolsList.innerHTML = `<div class="loading-spinner"><i class="fa-solid fa-circle-notch fa-spin"></i> Завантаження котушок...</div>`;
    }

    try {
        const [printers, spools] = await Promise.all([
            fetchPrintersApi().catch(() => state.printers),
            fetchSpoolsApi().catch(() => state.spools)
        ]);

        state.printers = printers || [];
        state.spools = spools || {};

        renderFilteredSpoolsInventory();
    } catch (e) {
        console.error("Error loading materials:", e);
    }
}

export function filterWarehouseSpools(spoolsListOrObj, { query = "", matFilter = "all" } = {}) {
    const rawList = Array.isArray(spoolsListOrObj) ? spoolsListOrObj : Object.values(spoolsListOrObj || {});
    const allUnassigned = rawList.filter(s => !s.assigned_printer_id && (s.quantity !== undefined ? Number(s.quantity) : 1) > 0);
    const q = (query || "").trim().toLowerCase();
    const filter = (matFilter || "all").toUpperCase();

    return allUnassigned.filter(s => {
        const sType = String(s.type || "PLA").toUpperCase();
        const sName = String(s.name || "").toLowerCase();
        const sColor = String(s.color || "").toLowerCase();

        const matchesQuery = !q || sName.includes(q) || sType.toLowerCase().includes(q) || sColor.includes(q);
        if (!matchesQuery) return false;

        if (filter === "ALL") return true;
        if (filter === "PLA") return sType.includes("PLA");
        if (filter === "PETG") return sType.includes("PETG") || sType.includes("PCTG") || sType.includes("PET");
        if (filter === "TPU") return sType.includes("TPU");
        if (filter === "ABS/ASA") return sType.includes("ABS") || sType.includes("ASA");
        if (filter === "OTHER") {
            return !(sType.includes("PLA") || sType.includes("PETG") || sType.includes("PCTG") || sType.includes("PET") || sType.includes("TPU") || sType.includes("ABS") || sType.includes("ASA"));
        }
        return true;
    });
}

export function renderFilteredSpoolsInventory() {
    const spoolsList = document.getElementById("spools-list");
    if (!spoolsList) return;
    const allUnassigned = Object.values(state.spools || {}).filter(s => !s.assigned_printer_id && (s.quantity !== undefined ? Number(s.quantity) : 1) > 0);

    if (allUnassigned.length === 0) {
        spoolsList.innerHTML = `<p class="text-muted text-center p-3">Склад порожній. Натисніть "+ Нова котушка", щоб додати.</p>`;
        return;
    }

    const searchEl = document.getElementById("spool-search-input");
    const query = (searchEl?.value || "").trim().toLowerCase();
    const activeMatBtn = document.querySelector("#spool-filter-pills .pill-btn.active");
    const matFilter = (activeMatBtn?.getAttribute("data-mat-filter") || "all").toUpperCase();

    const filtered = filterWarehouseSpools(allUnassigned, { query, matFilter });

    if (filtered.length === 0) {
        spoolsList.innerHTML = `<p class="text-muted text-center p-3">За вибраним фільтром котушок не знайдено.</p>`;
        return;
    }

    spoolsList.innerHTML = filtered.map(s => {
        const remGrams = s.remaining_grams !== undefined ? s.remaining_grams : 1000;
        const totalGrams = s.initial_grams || s.total_grams || 1000;
        const safeId = escapeHtml(String(s.id));
        return `
        <div class="spool-item glass-card p-3 mb-2 d-flex justify-content-between align-items-center">
            <div class="spool-left d-flex align-items-center gap-2">
                ${renderVisualSpoolSvg(s.color || '#3b82f6', remGrams, totalGrams, 44)}
                <div class="spool-details">
                    <h4 style="margin:0; font-size:14px;">
                        ${escapeHtml(s.name)} 
                        <span class="badge badge-secondary" style="font-size:10px; font-weight:500; margin-left:4px;">📦 ${s.quantity || 1} шт</span>
                    </h4>
                    <small class="text-muted">${escapeHtml(s.type || 'PLA')} • ${s.price_per_kg || s.price_uah || 650} ₴/кг • ⚡ ${remGrams}g</small>
                </div>
            </div>
            <div class="spool-right d-flex align-items-center gap-2">
                <button class="btn btn-xs btn-outline btn-history-spool" data-id="${safeId}" title="Історія аудиту руху">
                    <i class="fa-solid fa-clock-rotate-left"></i>
                </button>
                <button class="btn btn-xs btn-primary btn-assign-spool" data-id="${safeId}" title="Встановити на принтер">
                    <i class="fa-solid fa-truck-ramp-box"></i> На принтер
                </button>
                <button class="btn btn-xs btn-outline btn-edit-spool" data-id="${safeId}" title="Редагувати">
                    <i class="fa-solid fa-pen-to-square"></i>
                </button>
                <button class="btn btn-xs btn-outline-danger btn-delete-spool" data-id="${safeId}" title="Видалити">
                    <i class="fa-solid fa-trash"></i>
                </button>
            </div>
        </div>`;
    }).join("");
}

export function openAddSpoolModal(spool = null) {
    const modal = document.getElementById("spool-modal");
    const titleEl = document.getElementById("spool-modal-title");
    const nameEl = document.getElementById("spool-name");
    const typeEl = document.getElementById("spool-type");
    const gramsEl = document.getElementById("spool-grams");
    const qtyEl = document.getElementById("spool-quantity");
    const priceEl = document.getElementById("spool-price");
    const totalPriceEl = document.getElementById("spool-total-price");
    const colEl = document.getElementById("spool-color");

    if (!modal) return;

    if (spool && typeof spool === "object") {
        state.editingSpoolId = spool.id || null;
        if (titleEl) titleEl.textContent = "✏️ Редагувати котушку";
        if (nameEl) nameEl.value = spool.name || "";
        if (typeEl) typeEl.value = spool.type || "PLA";
        const curGrams = spool.remaining_grams !== undefined ? spool.remaining_grams : 1000;
        const curPrice = spool.price_per_kg || spool.price_uah || 650;
        if (gramsEl) gramsEl.value = curGrams;
        if (qtyEl) qtyEl.value = spool.quantity || 1;
        if (priceEl) priceEl.value = curPrice;
        if (totalPriceEl) totalPriceEl.value = Math.round((curPrice * curGrams / 1000) * 100) / 100;
        if (colEl) colEl.value = spool.color || "#3b82f6";
    } else {
        state.editingSpoolId = null;
        if (titleEl) titleEl.textContent = "➕ Додати котушку";
        if (nameEl) nameEl.value = "";
        if (typeEl) typeEl.value = "PLA";
        if (gramsEl) gramsEl.value = 1000;
        if (qtyEl) qtyEl.value = 1;
        if (priceEl) priceEl.value = 650;
        if (totalPriceEl) totalPriceEl.value = 650;
        if (colEl) colEl.value = "#3b82f6";
    }

    triggerHaptic("light");
    modal.classList.add("active");
}

export function closeSpoolModal() {
    const modal = document.getElementById("spool-modal");
    if (modal) modal.classList.remove("active");
    state.editingSpoolId = null;
}

export function syncSpoolPrices(source) {
    const priceEl = document.getElementById("spool-price");
    const totalPriceEl = document.getElementById("spool-total-price");
    const gramsEl = document.getElementById("spool-grams");
    if (!priceEl || !totalPriceEl || !gramsEl) return;

    const grams = parseFloat(gramsEl.value) || 1000;
    if (grams <= 0) return;

    if (source === "per_kg") {
        const pKg = parseFloat(priceEl.value) || 0;
        totalPriceEl.value = Math.round((pKg * grams / 1000) * 100) / 100;
    } else if (source === "total") {
        const pTot = parseFloat(totalPriceEl.value) || 0;
        priceEl.value = Math.round((pTot / (grams / 1000)) * 100) / 100;
    }
}

export async function submitSaveSpool(e) {
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
        id: state.editingSpoolId || undefined,
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
        const result = await saveSpoolApi(payload);
        if (result.status === "ok" || result.spool || !result.error) {
            triggerHaptic("success");
            closeSpoolModal();
            await loadMaterials();
        } else {
            triggerHaptic("error");
            alert("⚠️ Помилка: " + (result.error || "Невідома помилка"));
        }
    } catch (err) {
        triggerHaptic("error");
        console.error("Save spool error:", err);
        alert("⚠️ Мережева помилка збереження котушки.");
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = "Зберегти котушку";
        }
    }
}

export function openAssignSpoolModal(printers = null, defaultPrinterId = null, defaultSlotId = null) {
    const modal = document.getElementById("assign-spool-modal");
    if (!modal) return;
    const selPrinter = document.getElementById("assign-printer-select");
    const selSlot = document.getElementById("assign-slot-select");
    const spoolNameSpan = document.getElementById("assign-spool-name");
    const spoolInfoBox = document.getElementById("assign-spool-info");
    const spoolSelectGroup = document.getElementById("assign-spool-select-group");
    const spoolSelect = document.getElementById("assign-spool-select");

    const spool = state.selectedSpoolForAssign;
    if (spool) {
        if (spoolInfoBox) spoolInfoBox.style.display = "block";
        if (spoolSelectGroup) spoolSelectGroup.style.display = "none";
        if (spoolNameSpan) {
            const remGrams = spool.remaining_grams !== undefined ? spool.remaining_grams : 1000;
            spoolNameSpan.textContent = `${spool.name || 'Котушка'} (${spool.type || 'PLA'} • ${remGrams}g)`;
        }
    } else {
        if (spoolInfoBox) spoolInfoBox.style.display = "none";
        if (spoolSelectGroup) {
            spoolSelectGroup.style.display = "block";
            const spoolsMap = state.spools || {};
            const availableSpools = Object.values(spoolsMap).filter(s => !s.assigned_printer_id && (s.quantity === undefined || Number(s.quantity) > 0));
            if (spoolSelect) {
                if (availableSpools.length === 0) {
                    spoolSelect.innerHTML = `<option value="">На складі немає вільних котушок</option>`;
                } else {
                    spoolSelect.innerHTML = availableSpools.map(s => `
                        <option value="${s.id}">${escapeHtml(s.name)} (${s.type || 'PLA'} • ${s.remaining_grams || 1000}g)</option>
                    `).join("");
                }
            }
        }
    }

    const printerList = printers || state.printers || [];
    if (selPrinter) {
        if (printerList.length === 0) {
            selPrinter.innerHTML = `<option value="">Немає доступних принтерів</option>`;
        } else {
            selPrinter.innerHTML = printerList.map(p => `
                <option value="${p.id}">${escapeHtml(p.name)} (${p.has_ams ? 'З AMS' : 'Пряма подача'})</option>
            `).join("");
        }
        if (defaultPrinterId) selPrinter.value = defaultPrinterId;
    }

    function updateSlots() {
        const pId = selPrinter?.value;
        const p = printerList.find(x => x.id === pId);
        if (!selSlot) return;
        if (!p) {
            selSlot.innerHTML = `<option value="">Немає слотів</option>`;
            return;
        }
        if (p.has_ams) {
            selSlot.innerHTML = `
                <option value="0">Слот A1</option>
                <option value="1">Слот A2</option>
                <option value="2">Слот A3</option>
                <option value="3">Слот A4</option>
                <option value="254">VT (Зовнішній)</option>
            `;
        } else {
            selSlot.innerHTML = `<option value="254">Зовнішній котушкотримач</option>`;
        }
        if (defaultSlotId !== null && defaultSlotId !== undefined) {
            selSlot.value = String(defaultSlotId);
        }
    }

    if (selPrinter) selPrinter.onchange = updateSlots;
    updateSlots();

    triggerHaptic("light");
    modal.classList.add("active");
}

export function closeAssignSpoolModal() {
    const modal = document.getElementById("assign-spool-modal");
    if (modal) modal.classList.remove("active");
    state.selectedSpoolForAssign = null;
}

export async function confirmAssignSpool() {
    const btn = document.getElementById("confirm-assign-spool-btn");
    if (btn && btn.disabled) return;

    const spool = state.selectedSpoolForAssign;
    const spoolSelect = document.getElementById("assign-spool-select");
    const spoolId = spool?.id || (spoolSelect ? spoolSelect.value : "");

    if (!spoolId) {
        showToast("⚠️ Будь ласка, оберіть котушку зі складу!", "warning");
        return;
    }

    const selPrinter = document.getElementById("assign-printer-select");
    const selSlot = document.getElementById("assign-slot-select");
    const printerId = selPrinter ? selPrinter.value : "";
    const slotKey = selSlot ? selSlot.value : "0";

    if (!printerId) {
        showToast("⚠️ Будь ласка, оберіть принтер для встановлення котушки!", "warning");
        return;
    }

    const origText = btn ? btn.innerHTML : "";
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Встановлення...`;
    }

    try {
        const res = await mountSpoolApi(spoolId, printerId, slotKey);
        const isSuccess = Boolean(res && !res.error && (res.status === "ok" || res.spool));
        if (isSuccess) {
            triggerHaptic("success");
            showToast("✅ Котушку успішно встановлено на принтер!", "success");
            closeAssignSpoolModal();
            await loadMaterials();
            if (typeof window.fetchPrinters === "function") {
                await window.fetchPrinters();
            }
        } else {
            triggerHaptic("error");
            showToast("⚠️ Помилка призначення: " + (res?.error || "Невідома помилка"), "error");
        }
    } catch (err) {
        triggerHaptic("error");
        console.error("Mount spool error:", err);
        showToast("⚠️ Мережева помилка при призначенні котушки на принтер.", "error");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origText || "Встановити на принтер";
        }
    }
}

export async function openSpoolMovementsModal(options = {}) {
    const modal = document.getElementById("spool-movements-modal");
    const tbody = document.getElementById("spool-movements-table-body");
    const spoolSelect = document.getElementById("mov-filter-spool");
    const actionSelect = document.getElementById("mov-filter-action");
    const dateSelect = document.getElementById("mov-filter-date");
    const searchInput = document.getElementById("mov-filter-search");

    if (!modal) return;
    modal.style.display = "flex";
    modal.classList.add("active");
    triggerHaptic("light");

    initMovementsFilterEvents();

    if (spoolSelect) {
        const desiredSpool = options.spoolId || spoolSelect.value || "all";
        let optHtml = `<option value="all">🧵 Всі котушки</option>`;
        Object.values(state.spools || {}).forEach(s => {
            optHtml += `<option value="${s.id}">${escapeHtml(s.name || "Котушка")} (${escapeHtml(s.type || "")})</option>`;
        });
        spoolSelect.innerHTML = optHtml;
        if (options.spoolId) spoolSelect.value = options.spoolId;
        else if (desiredSpool) spoolSelect.value = desiredSpool;
    }

    if (options.action && actionSelect) actionSelect.value = options.action;
    if (options.date && dateSelect) dateSelect.value = options.date;
    if (options.query && searchInput) searchInput.value = options.query;

    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="6" class="text-center p-3"><i class="fa-solid fa-spinner fa-spin me-2"></i>Завантаження журналу аудиту...</td></tr>`;

    try {
        const data = await fetchSpoolMovementsApi();
        state.allMovementsCache = Array.isArray(data) ? [...data].reverse() : [];
        renderFilteredMovements();
    } catch (e) {
        console.error("Spool movements load error:", e);
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger p-3">Помилка завантаження журналу аудиту</td></tr>`;
    }
}

export function openSpoolMovementsFor(spoolId) {
    openSpoolMovementsModal({ spoolId });
}

export function closeSpoolMovementsModal(e) {
    if (e) {
        if (typeof e.preventDefault === "function") e.preventDefault();
        if (typeof e.stopPropagation === "function") e.stopPropagation();
    }
    const modal = document.getElementById("spool-movements-modal");
    if (modal) {
        modal.classList.remove("active");
        modal.style.display = "none";
    }
}

export function filterSpoolMovements(movementsList, { spoolId = "all", action = "all", period = "all", query = "" } = {}) {
    const list = Array.isArray(movementsList) ? movementsList : [];
    const now = Date.now() / 1000;
    let minTime = 0;
    if (period === "today") {
        const d = new Date();
        minTime = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() / 1000;
    } else if (period === "yesterday") {
        const d = new Date();
        minTime = (new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() / 1000) - 86400;
    } else if (period === "week") {
        minTime = now - (7 * 86400);
    } else if (period === "month") {
        minTime = now - (30 * 86400);
    }

    const q = (query || "").trim().toLowerCase();

    return list.filter(item => {
        if (spoolId !== "all" && String(item.spool_id) !== String(spoolId)) return false;
        if (action !== "all") {
            if (action === "stock") {
                if (item.action !== "stock" && item.action !== "initial_stock" && item.action !== "refill") return false;
            } else if (String(item.action) !== String(action)) {
                return false;
            }
        }
        if (minTime > 0 && (item.timestamp || 0) < minTime) return false;
        if (q) {
            const searchable = `${item.spool_name || ''} ${item.note || ''} ${item.reason || ''} ${item.printer_name || ''} ${item.user || ''}`.toLowerCase();
            if (!searchable.includes(q)) return false;
        }
        return true;
    });
}

export function renderFilteredMovements() {
    const tbody = document.getElementById("spool-movements-table-body");
    const spoolSelect = document.getElementById("mov-filter-spool");
    const actionSelect = document.getElementById("mov-filter-action");
    const dateSelect = document.getElementById("mov-filter-date");
    const searchInput = document.getElementById("mov-filter-search");
    if (!tbody) return;

    const filterSpool = spoolSelect ? spoolSelect.value : "all";
    const filterAction = actionSelect ? actionSelect.value : "all";
    const filterDate = dateSelect ? dateSelect.value : "all";
    const filterQuery = searchInput ? searchInput.value.trim().toLowerCase() : "";

    const filtered = filterSpoolMovements(state.allMovementsCache || [], {
        spoolId: filterSpool,
        action: filterAction,
        period: filterDate,
        query: filterQuery
    });

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted p-3">За обраними фільтрами записів не знайдено</td></tr>`;
        return;
    }

    const actionLabels = {
        "initial_stock": "📦 Поповнення",
        "refill": "📦 Поповнення",
        "stock": "📦 Поповнення",
        "print": "🖨️ Друк",
        "manual_edit": "✏️ Коригування",
        "write_off": "🗑️ Списання"
    };

    tbody.innerHTML = filtered.map(item => {
        const delta = Number(item.weight_change_g ?? item.delta_grams ?? item.grams ?? 0);
        const deltaClass = delta > 0 ? "text-success font-weight-bold" : (delta < 0 ? "text-danger font-weight-bold" : "text-muted");
        const deltaSign = delta > 0 ? `+${delta.toFixed(1)}г` : `${delta.toFixed(1)}г`;
        const actionLabel = actionLabels[item.action] || item.action || "Операція";
        const remGrams = Number(item.new_weight_g ?? item.remaining_grams ?? 0);
        const dateStr = item.datetime || item.created_at || (item.timestamp ? new Date(item.timestamp * 1000).toLocaleString("uk-UA") : "—");
        const userDisplay = item.user || item.user_id || "System";
        const noteDisplay = item.reason || item.note || "";

        return `
            <tr>
                <td><small class="text-muted">${escapeHtml(dateStr)}</small></td>
                <td><strong>${escapeHtml(item.spool_name || "Котушка")}</strong></td>
                <td><span class="badge badge-secondary">${escapeHtml(actionLabel)}</span></td>
                <td class="${deltaClass}">${deltaSign}</td>
                <td>${remGrams.toFixed(1)}г</td>
                <td>
                    <div><i class="fa-solid fa-user-circle me-1 text-muted"></i><strong>${escapeHtml(userDisplay)}</strong></div>
                    ${noteDisplay ? `<small class="text-muted d-block" style="font-size:0.75rem;">${escapeHtml(noteDisplay)}</small>` : ""}
                </td>
            </tr>`;
    }).join("");
}

export function initMovementsFilterEvents() {
    if (state.movementsFiltersBound) return;
    state.movementsFiltersBound = true;

    ["mov-filter-spool", "mov-filter-action", "mov-filter-date"].forEach(id => {
        document.getElementById(id)?.addEventListener("change", renderFilteredMovements);
    });
    document.getElementById("mov-filter-search")?.addEventListener("input", renderFilteredMovements);

    const resetBtn = document.getElementById("mov-filter-reset-btn") || document.getElementById("btn-reset-movements-filters");
    resetBtn?.addEventListener("click", () => {
        const sSelect = document.getElementById("mov-filter-spool");
        const aSelect = document.getElementById("mov-filter-action");
        const dSelect = document.getElementById("mov-filter-date");
        const qInput = document.getElementById("mov-filter-search");
        if (sSelect) sSelect.value = "all";
        if (aSelect) aSelect.value = "all";
        if (dSelect) dSelect.value = "all";
        if (qInput) qInput.value = "";
        renderFilteredMovements();
    });

    document.getElementById("btn-export-movements-pdf")?.addEventListener("click", () => {
        const spoolSelect = document.getElementById("mov-filter-spool");
        const actionSelect = document.getElementById("mov-filter-action");
        const dateSelect = document.getElementById("mov-filter-date");
        const searchInput = document.getElementById("mov-filter-search");
        const url = getMovementsPdfExportUrl({
            spool_id: spoolSelect?.value !== "all" ? spoolSelect?.value : undefined,
            action: actionSelect?.value !== "all" ? actionSelect?.value : undefined,
            period: dateSelect?.value !== "all" ? dateSelect?.value : undefined,
            q: searchInput?.value?.trim() || undefined
        });
        window.open(url, "_blank");
    });
}

export function initSpoolsModule() {
    if (state.spoolsModuleBound) return;
    state.spoolsModuleBound = true;

    // 1. Spool search input & clear button
    const searchInput = document.getElementById("spool-search-input");
    const clearBtn = document.getElementById("spool-search-clear-btn");

    if (searchInput) {
        searchInput.addEventListener("input", () => {
            if (clearBtn) {
                clearBtn.style.display = searchInput.value.trim().length > 0 ? "inline-block" : "none";
            }
            renderFilteredSpoolsInventory();
        });
    }

    if (clearBtn && searchInput) {
        clearBtn.addEventListener("click", () => {
            searchInput.value = "";
            clearBtn.style.display = "none";
            searchInput.focus();
            renderFilteredSpoolsInventory();
        });
    }

    // 2. Material filter pills
    const pillContainer = document.getElementById("spool-filter-pills");
    if (pillContainer) {
        pillContainer.querySelectorAll(".pill-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                triggerHaptic("selection");
                pillContainer.querySelectorAll(".pill-btn").forEach(b => b.classList.remove("active"));
                btn.classList.add("active");
                renderFilteredSpoolsInventory();
            });
        });
    }

    // 3. Confirm assign spool button in assign modal
    const assignBtn = document.getElementById("confirm-assign-spool-btn");
    if (assignBtn) {
        assignBtn.addEventListener("click", confirmAssignSpool);
    }

    // 4. Close assign spool modal button
    const closeAssignBtn = document.getElementById("close-assign-spool-modal");
    if (closeAssignBtn) {
        closeAssignBtn.addEventListener("click", closeAssignSpoolModal);
    }

    // 5. Preset chips in spool modal
    document.querySelectorAll("#spool-modal .preset-chip").forEach(chip => {
        chip.addEventListener("click", () => {
            triggerHaptic("selection");
            const nameInput = document.getElementById("spool-name");
            const typeSelect = document.getElementById("spool-type");
            const colorInput = document.getElementById("spool-color");
            const priceInput = document.getElementById("spool-price");
            if (nameInput && chip.dataset.name) nameInput.value = chip.dataset.name;
            if (typeSelect && chip.dataset.type) typeSelect.value = chip.dataset.type;
            if (colorInput && chip.dataset.color) colorInput.value = chip.dataset.color;
            if (priceInput && chip.dataset.price) {
                priceInput.value = chip.dataset.price;
                syncSpoolPrices("per_kg");
            }
        });
    });

    // 6. Spool price calculation listeners
    const pricePerKgInput = document.getElementById("spool-price");
    const totalPriceInput = document.getElementById("spool-total-price");
    const gramsInput = document.getElementById("spool-grams");

    if (pricePerKgInput) {
        pricePerKgInput.addEventListener("input", () => syncSpoolPrices("per_kg"));
    }
    if (totalPriceInput) {
        totalPriceInput.addEventListener("input", () => syncSpoolPrices("total"));
    }
    if (gramsInput) {
        gramsInput.addEventListener("input", () => syncSpoolPrices("per_kg"));
    }
}
