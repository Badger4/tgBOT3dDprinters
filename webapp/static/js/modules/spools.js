/**
 * 3D Farm Manager - Materials Warehouse & Spools Module
 */

import { escapeHtml, triggerHaptic, renderVisualSpoolSvg, evaluateMathExpression } from "./utils.js";
import { state } from "./state.js";
import {
    fetchPrintersApi,
    fetchSpoolsApi,
    saveSpoolApi,
    deleteSpoolApi,
    controlPrinterApi,
    fetchSpoolMovementsApi,
    getMovementsPdfExportUrl
} from "./api.js";

export async function loadMaterials() {
    const container = document.getElementById("ams-printers-container");
    if (container) {
        container.innerHTML = `<div class="loading-spinner"><i class="fa-solid fa-circle-notch fa-spin"></i> Завантаження...</div>`;
    }

    try {
        const [printers, spools] = await Promise.all([
            fetchPrintersApi().catch(() => state.printers),
            fetchSpoolsApi().catch(() => state.spools)
        ]);

        state.printers = printers || [];
        state.spools = spools || {};

        if (container) {
            if (!state.printers || state.printers.length === 0) {
                container.innerHTML = `<p class="text-muted text-center p-3">Немає активних принтерів</p>`;
            } else {
                const spoolsList = Object.values(state.spools);

                container.innerHTML = state.printers.map(p => {
                    const hasAms = Boolean(p.has_ams);
                    const activeKey = String(p.active_slot_key || "254");
                    const slots = p.ams_slots || {};
                    const slotKeys = hasAms ? ["0", "1", "2", "3", "254"] : ["254"];
                    const slotLabels = { "0": "A1", "1": "A2", "2": "A3", "3": "A4", "254": hasAms ? "VT (Зовнішній)" : "Зовнішній котушкотримач", "255": hasAms ? "VT (Зовнішній)" : "Зовнішній котушкотримач" };
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
                                    const grams = slots[k] !== undefined ? slots[k] : (slots["255"] !== undefined && k === "254" ? slots["255"] : 0);
                                    const isActive = (k === activeKey || (k === "254" && activeKey === "255") || (k === "255" && activeKey === "254"));
                                    const assignedSpool = spoolsList.find(s => s.assigned_printer_id === p.id && (String(s.assigned_slot_key) === k || (k === "254" && String(s.assigned_slot_key) === "255")));
                                    const trayInfo = (p.ams_trays_info || {})[k] || (k === "254" ? (p.ams_trays_info || {})["255"] : {}) || {};
                                    const hasAmsTray = Boolean(!trayInfo.empty && trayInfo.type);
                                    const hasAssigned = Boolean(assignedSpool && (assignedSpool.remaining_grams > 0 || assignedSpool.name));
                                    const hasPhysicalSpool = hasAssigned || hasAmsTray || (isActive && p.filament_type && p.filament_type !== "Невизначено" && grams > 0);

                                    if (!hasPhysicalSpool) {
                                        return `
                                            <div class="ams-slot-card empty-slot ${isActive ? 'active-slot' : ''}">
                                                <div class="slot-tag d-flex justify-content-between align-items-center mb-1">
                                                    <span><b>${slotLabels[k]}</b> ${isActive ? '⚡' : ''}</span>
                                                </div>
                                                <div class="empty-slot-placeholder">
                                                    <i class="fa-regular fa-circle-dashed"></i>
                                                    <span>Порожній простір</span>
                                                </div>
                                            </div>`;
                                    }

                                    let spoolColor = '#3b82f6';
                                    let spoolName = 'Котушка';
                                    let spoolType = 'PLA';
                                    let pct = Math.min(100, Math.max(0, Math.round((grams / 1000) * 100)));

                                    if (assignedSpool) {
                                        spoolColor = assignedSpool.color || '#3b82f6';
                                        spoolName = escapeHtml(assignedSpool.name);
                                        spoolType = escapeHtml(assignedSpool.type);
                                        const maxCap = assignedSpool.initial_grams || assignedSpool.total_grams || 1000;
                                        pct = Math.min(100, Math.max(0, Math.round((grams / maxCap) * 100)));
                                    } else if (hasAmsTray) {
                                        spoolColor = trayInfo.color || (isActive ? '#22c55e' : '#3b82f6');
                                        spoolType = escapeHtml(trayInfo.type);
                                        spoolName = trayInfo.sub_brands ? `Bambu ${spoolType} ${escapeHtml(trayInfo.sub_brands)}` : `Bambu ${spoolType}`;
                                        if (trayInfo.remain !== undefined && trayInfo.remain >= 0) {
                                            pct = trayInfo.remain;
                                        }
                                    } else if (isActive) {
                                        spoolColor = '#22c55e';
                                        spoolName = 'Активна нитка';
                                        spoolType = escapeHtml(p.filament_type || 'PLA');
                                    }

                                    return `
                                        <div class="ams-slot-card ${isActive ? 'active-slot' : ''}">
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
                                                ${renderVisualSpoolSvg(spoolColor, grams, assignedSpool ? (assignedSpool.initial_grams || 1000) : 1000, 26)}
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
            }
        }

        renderFilteredSpoolsInventory();
    } catch (e) {
        console.error("Error loading materials:", e);
    }
}

export function renderFilteredSpoolsInventory() {
    const spoolsList = document.getElementById("spools-list");
    if (!spoolsList) return;
    const allUnassigned = Object.values(state.spools || {}).filter(s => !s.assigned_printer_id && (s.quantity || 1) > 0);

    if (allUnassigned.length === 0) {
        spoolsList.innerHTML = `<p class="text-muted text-center p-3">Склад порожній. Натисніть "+ Нова котушка", щоб додати.</p>`;
        return;
    }

    const searchEl = document.getElementById("spool-search-input");
    const query = (searchEl?.value || "").trim().toLowerCase();
    const activeMatBtn = document.querySelector("#spool-filter-pills .pill-btn.active");
    const matFilter = (activeMatBtn?.getAttribute("data-mat-filter") || "all").toUpperCase();

    const filtered = allUnassigned.filter(s => {
        const sType = String(s.type || "PLA").toUpperCase();
        const sName = String(s.name || "").toLowerCase();
        const sColor = String(s.color || "").toLowerCase();

        const matchesQuery = !query || sName.includes(query) || sType.toLowerCase().includes(query) || sColor.includes(query);
        if (!matchesQuery) return false;

        if (matFilter === "ALL") return true;
        if (matFilter === "PLA") return sType.includes("PLA");
        if (matFilter === "PETG") return sType.includes("PETG") || sType.includes("PCTG") || sType.includes("PET");
        if (matFilter === "TPU") return sType.includes("TPU");
        if (matFilter === "ABS/ASA") return sType.includes("ABS") || sType.includes("ASA");
        if (matFilter === "OTHER") {
            return !(sType.includes("PLA") || sType.includes("PETG") || sType.includes("PCTG") || sType.includes("PET") || sType.includes("TPU") || sType.includes("ABS") || sType.includes("ASA"));
        }
        return true;
    });

    if (filtered.length === 0) {
        spoolsList.innerHTML = `<p class="text-muted text-center p-3">За вибраним фільтром котушок не знайдено.</p>`;
        return;
    }

    spoolsList.innerHTML = filtered.map(s => `
        <div class="spool-item glass-card p-3 mb-2 d-flex justify-content-between align-items-center">
            <div class="spool-left d-flex align-items-center gap-2">
                ${renderVisualSpoolSvg(s.color || '#3b82f6', s.remaining_grams, s.initial_grams || s.total_grams, 44)}
                <div class="spool-details">
                    <h4 style="margin:0; font-size:14px;">
                        ${escapeHtml(s.name)} 
                        <span class="badge badge-secondary" style="font-size:10px; font-weight:500; margin-left:4px;">📦 ${s.quantity || 1} шт</span>
                    </h4>
                    <small class="text-muted">${escapeHtml(s.type || 'PLA')} • ${s.price_per_kg || s.price_uah || 650} ₴/кг • ⚡ ${s.remaining_grams || 1000}g</small>
                </div>
            </div>
            <div class="spool-right d-flex align-items-center gap-2">
                <button class="btn btn-xs btn-outline btn-history-spool" data-id="${s.id}" title="Історія аудиту руху">
                    <i class="fa-solid fa-clock-rotate-left"></i>
                </button>
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

export function openAssignSpoolModal(printers) {
    const modal = document.getElementById("assign-spool-modal");
    if (!modal) return;
    const selPrinter = document.getElementById("assign-printer-select");
    const selSlot = document.getElementById("assign-slot-select");
    const spoolNameSpan = document.getElementById("assign-spool-name");

    if (spoolNameSpan && state.selectedSpoolForAssign) {
        spoolNameSpan.textContent = `${state.selectedSpoolForAssign.name} (${state.selectedSpoolForAssign.remaining_grams}g)`;
    }

    if (selPrinter) {
        selPrinter.innerHTML = (printers || []).map(p => `
            <option value="${p.id}">${escapeHtml(p.name)} (${p.has_ams ? 'З AMS' : 'Без AMS'})</option>
        `).join("");
    }

    function updateSlots() {
        const pId = selPrinter?.value;
        const p = (printers || []).find(x => x.id === pId);
        if (!selSlot || !p) return;
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
    }

    if (selPrinter) selPrinter.onchange = updateSlots;
    updateSlots();

    triggerHaptic("light");
    modal.classList.add("active");
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

    const now = new Date();
    let minTime = 0;
    if (filterDate === "today") {
        minTime = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() / 1000;
    } else if (filterDate === "yesterday") {
        minTime = (new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() / 1000) - 86400;
    } else if (filterDate === "week") {
        minTime = (now.getTime() / 1000) - (7 * 86400);
    } else if (filterDate === "month") {
        minTime = (now.getTime() / 1000) - (30 * 86400);
    }

    const filtered = (state.allMovementsCache || []).filter(item => {
        if (filterSpool !== "all" && String(item.spool_id) !== String(filterSpool)) return false;
        if (filterAction !== "all" && String(item.action) !== String(filterAction)) return false;
        if (minTime > 0 && (item.timestamp || 0) < minTime) return false;
        if (filterQuery) {
            const searchable = `${item.spool_name || ''} ${item.note || ''} ${item.reason || ''} ${item.printer_name || ''}`.toLowerCase();
            if (!searchable.includes(filterQuery)) return false;
        }
        return true;
    });

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted p-3">За обраними фільтрами записів не знайдено</td></tr>`;
        return;
    }

    tbody.innerHTML = filtered.map(item => {
        const delta = Number(item.delta_grams || item.grams || 0);
        const deltaClass = delta > 0 ? "text-success font-weight-bold" : (delta < 0 ? "text-danger font-weight-bold" : "text-muted");
        const deltaSign = delta > 0 ? `+${delta.toFixed(1)}г` : `${delta.toFixed(1)}г`;
        const actionLabel = item.action || "Операція";
        const dateStr = item.created_at || (item.timestamp ? new Date(item.timestamp * 1000).toLocaleString("uk-UA") : "—");

        return `
            <tr>
                <td><small class="text-muted">${escapeHtml(dateStr)}</small></td>
                <td><strong>${escapeHtml(item.spool_name || "Котушка")}</strong></td>
                <td><span class="badge badge-secondary">${escapeHtml(actionLabel)}</span></td>
                <td class="${deltaClass}">${deltaSign}</td>
                <td>${Number(item.remaining_grams || 0).toFixed(1)}г</td>
                <td><small class="text-muted">${escapeHtml(item.note || item.reason || "—")}</small></td>
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
    document.getElementById("btn-reset-movements-filters")?.addEventListener("click", () => {
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
