/**
 * 3D Farm Manager - Print History, Scrap Accounting & Export
 */

import { escapeHtml, triggerHaptic } from "./utils.js";
import { state } from "./state.js";
import {
    fetchHistoryApi,
    deleteHistoryItemApi,
    clearAllHistoryApi,
    markScrapApi,
    fetchPartsApi,
    fetchFilesApi,
    printPartApi
} from "./api.js";

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

export async function loadHistory() {
    const tbody = document.getElementById("history-table-body");
    if (!tbody) return;

    try {
        const history = await fetchHistoryApi();
        state.history = Array.isArray(history) ? history : [];
        populateHistoryPrinterSelect(state.history);
        applyHistoryFilters();
    } catch (e) {
        console.error("Failed loading history:", e);
    }
}

export function populateHistoryPrinterSelect(history) {
    const sel = document.getElementById("history-filter-printer");
    if (!sel) return;
    const curVal = sel.value;
    const printerNames = new Set();

    (state.printers || []).forEach(p => {
        const name = (p.name || p.id || "").trim();
        if (name) printerNames.add(name);
    });

    (history || []).forEach(item => {
        const name = (item.printer_name || item.printer || item.printer_id || "").trim();
        if (name) printerNames.add(name);
    });

    const sorted = Array.from(printerNames).sort((a, b) =>
        a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' })
    );

    let optionsHtml = `<option value="">🌐 Усі принтери</option>`;
    sorted.forEach(name => {
        optionsHtml += `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`;
    });

    if (sel.innerHTML !== optionsHtml) {
        sel.innerHTML = optionsHtml;
        if (curVal && printerNames.has(curVal)) {
            sel.value = curVal;
        }
    }
}

export function renderHistoryList(history) {
    const tbody = document.getElementById("history-table-body");
    if (!tbody) return;

    const statJobsEl = document.getElementById("stat-total-jobs");
    const statWeightEl = document.getElementById("stat-total-weight");
    const statScrapEl = document.getElementById("stat-total-scrap");
    const scrapSummaryEl = document.getElementById("scrap-reasons-summary");

    let totalGrams = 0;
    let scrapJobs = 0;
    const reasonCounts = {};
    history.forEach(item => {
        const g = item.weight_g !== undefined ? item.weight_g : (item.weight ? Math.round(item.weight) : 0);
        totalGrams += g;
        if (item.is_scrap) {
            scrapJobs++;
            const r = String(item.scrap_reason || "Інший дефект").trim();
            reasonCounts[r] = (reasonCounts[r] || 0) + 1;
        }
    });

    if (statJobsEl) statJobsEl.textContent = history.length;
    if (statWeightEl) {
        const formattedGrams = totalGrams > 0 && totalGrams < 10 ? (Math.round(totalGrams * 10) / 10) : Math.round(totalGrams);
        statWeightEl.textContent = `${formattedGrams} g`;
    }
    if (statScrapEl) {
        const scrapPct = history.length ? Math.round((scrapJobs / history.length) * 100) : 0;
        statScrapEl.textContent = `${scrapJobs} (${scrapPct}%)`;
    }
    if (scrapSummaryEl) {
        const entries = Object.entries(reasonCounts).sort((a, b) => b[1] - a[1]);
        if (entries.length > 0) {
            scrapSummaryEl.style.display = "flex";
            scrapSummaryEl.innerHTML = `<span style="font-size:11px; color:var(--text-muted); align-self:center; margin-right:4px;"><i class="fa-solid fa-chart-simple color-red"></i> Причини браку:</span>` +
                entries.map(([reason, cnt]) => `<span class="badge-scrap" style="font-size:10.5px;">${escapeHtml(reason)}: <b>${cnt}</b></span>`).join("");
        } else {
            scrapSummaryEl.style.display = "none";
            scrapSummaryEl.innerHTML = "";
        }
    }

    if (!history || history.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center">Записи історії за обраними фільтрами не знайдені</td></tr>`;
        return;
    }

    tbody.innerHTML = history.slice(-100).reverse().map(item => {
        const dateFormatted = formatHistoryDate(item.timestamp, item.datetime);
        const printerName = escapeHtml(item.printer_name || item.printer || "Принтер");
        const taskName = escapeHtml(item.subtask_name || item.task || "Модель");
        const printerId = escapeHtml(item.printer_id || item.printer_sn || "");
        const clientOrder = escapeHtml(item.client_order || "");
        const weightVal = item.weight_g !== undefined ? item.weight_g : (item.weight ? Math.round(item.weight) : 0);
        const isScrap = Boolean(item.is_scrap);
        const wastedW = item.wasted_weight_g !== undefined ? item.wasted_weight_g : weightVal;

        const scrapBadge = isScrap
            ? `<span class="badge-scrap" title="Списано як брак: ${wastedW}г (${item.scrap_reason || 'Дефект'})">⚠️ БРАК: ${escapeHtml(item.scrap_reason || 'Дефект')} (-${wastedW}г)</span>`
            : "";
        const orderBadge = clientOrder
            ? `<span class="badge-order-ref" title="Замовлення/Клієнт">🏷️ ${clientOrder}</span>`
            : "";

        return `
            <tr>
                <td><small class="text-muted">${escapeHtml(dateFormatted)}</small></td>
                <td><strong>${printerName}</strong></td>
                <td>
                    <div class="d-flex flex-column gap-1">
                        <span>${taskName}</span>
                        <div class="d-flex gap-1 flex-wrap align-items-center">
                            ${orderBadge}
                            ${scrapBadge}
                        </div>
                    </div>
                </td>
                <td>${weightVal} g</td>
                <td>
                    <div class="d-flex gap-1">
                        <button class="btn btn-xs btn-outline btn-reprint-entry" data-task="${taskName}" data-printer="${printerName}" data-printer-id="${printerId}" title="Повторити друк">
                            <i class="fa-solid fa-rotate-right"></i>
                        </button>
                        ${!isScrap ? `
                        <button class="btn btn-xs btn-outline-warning btn-mark-scrap" data-ts="${item.timestamp}" data-weight="${weightVal}" data-task="${taskName}" data-printer="${printerName}" data-printer-id="${printerId}" data-slot="${item.slot_key || ''}" data-spool-id="${item.spool_id || ''}" data-date="${dateFormatted}" title="Зафіксувати брак та списати">
                            <i class="fa-solid fa-triangle-exclamation"></i> Брак
                        </button>` : ''}
                        <button class="btn btn-xs btn-outline-danger btn-delete-history-entry" data-ts="${item.timestamp}" title="Видалити запис">
                            <i class="fa-solid fa-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>`;
    }).join("");
}

export function applyHistoryFilters() {
    if (!state.history) return;

    const searchQuery = (document.getElementById("history-filter-search")?.value || "").toLowerCase().trim();
    const selectedPrinter = (document.getElementById("history-filter-printer")?.value || "").toLowerCase().trim();
    const selectedDate = document.getElementById("history-filter-date")?.value || "";

    const filtered = state.history.filter(item => {
        const taskName = String(item.subtask_name || item.task || "").toLowerCase();
        const printerName = String(item.printer_name || item.printer || "").toLowerCase().trim();
        const printerId = String(item.printer_id || item.printer_sn || "").toLowerCase().trim();
        const clientOrder = String(item.client_order || "").toLowerCase().trim();

        if (searchQuery && !taskName.includes(searchQuery) && !printerName.includes(searchQuery) && !clientOrder.includes(searchQuery)) {
            return false;
        }

        if (selectedPrinter) {
            let matched = (printerName === selectedPrinter || printerId === selectedPrinter);
            if (!matched && Array.isArray(state.printers)) {
                const pObj = state.printers.find(p =>
                    String(p.name || "").toLowerCase().trim() === selectedPrinter ||
                    String(p.id || "").toLowerCase().trim() === selectedPrinter ||
                    String(p.serialNumber || "").toLowerCase().trim() === selectedPrinter
                );
                if (pObj) {
                    const targetName = String(pObj.name || "").toLowerCase().trim();
                    const targetId = String(pObj.id || "").toLowerCase().trim();
                    const targetSn = String(pObj.serialNumber || "").toLowerCase().trim();
                    if (
                        (targetName && printerName === targetName) ||
                        (targetId && (printerId === targetId || printerName === targetId)) ||
                        (targetSn && (printerId === targetSn || printerName === targetSn))
                    ) {
                        matched = true;
                    }
                }
            }
            if (!matched) return false;
        }

        if (selectedDate) {
            let itemDateStr = "";
            if (typeof item.timestamp === "number" && item.timestamp > 0) {
                const d = new Date(item.timestamp * 1000);
                const yyyy = d.getFullYear();
                const mm = String(d.getMonth() + 1).padStart(2, "0");
                const dd = String(d.getDate()).padStart(2, "0");
                itemDateStr = `${yyyy}-${mm}-${dd}`;
            } else if (item.datetime && typeof item.datetime === "string") {
                const parts = item.datetime.split(" ")[0].split(".");
                if (parts.length === 3) itemDateStr = `${parts[2]}-${parts[1]}-${parts[0]}`;
            }
            if (itemDateStr && itemDateStr !== selectedDate) return false;
        }

        return true;
    });

    renderHistoryList(filtered);
}

export async function reprintJob(taskName, origPrinterName, origPrinterId) {
    if (!state.printers || state.printers.length === 0) {
        alert("⚠️ Немає підключених принтерів у фермі!");
        return;
    }

    const targetPrinter = state.printers.find(p => p.id === origPrinterId || p.name === origPrinterName || (p.name && origPrinterName && p.name.toLowerCase().includes(origPrinterName.toLowerCase()))) || state.printers[0];

    const confirmed = confirm(`🚀 Повторно кинути на друк модель "${taskName}"?\n\nПринтер: ${targetPrinter.name}`);
    if (!confirmed) return;

    triggerHaptic("medium");

    try {
        let partsList = Object.values(state.parts || {});
        if (partsList.length === 0) {
            try {
                const partsData = await fetchPartsApi();
                state.parts = partsData || {};
                partsList = Object.values(state.parts);
            } catch (e) {}
        }

        const normTask = taskName.trim().toLowerCase();
        const matchedPart = partsList.find(p => {
            if (!p.name) return false;
            const normP = p.name.trim().toLowerCase();
            return normP === normTask || normTask.includes(normP) || normP.includes(normTask);
        });

        if (matchedPart && matchedPart.id) {
            const result = await printPartApi(matchedPart.id, targetPrinter.id);
            if (result.status === "ok") {
                alert(`✅ Модель "${taskName}" успішно відправлено на друк на принтер ${targetPrinter.name}!`);
            } else {
                alert(`⚠️ Помилка запуску друку: ${result.error || "Невідомо"}`);
            }
        } else {
            let filesList = [];
            try {
                const filesData = await fetchFilesApi();
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
                alert(`⚠️ Модель або файл "${taskName}" не знайдено в Складі деталей чи Завантаженнях.`);
            }
        }
    } catch (err) {
        console.error("Reprint error:", err);
        alert("⚠️ Помилка зв'язку при запуску повторного друку.");
    }
}

export function openScrapModal(data) {
    state.activeScrapTarget = data;
    triggerHaptic("medium");

    const tsEl = document.getElementById("scrap-entry-ts");
    const pIdEl = document.getElementById("scrap-printer-id");
    const slotEl = document.getElementById("scrap-slot-key");
    const spoolEl = document.getElementById("scrap-spool-id");

    if (tsEl) tsEl.value = data.ts || "";
    if (pIdEl) pIdEl.value = data.printerId || "";
    if (slotEl) slotEl.value = data.slotKey || "";
    if (spoolEl) spoolEl.value = data.spoolId || "";

    const nameEl = document.getElementById("scrap-model-name");
    const badgeEl = document.getElementById("scrap-printer-badge");
    const weightEl = document.getElementById("scrap-planned-weight");
    const dateEl = document.getElementById("scrap-date-str");

    if (nameEl) nameEl.textContent = data.task || "Модель";
    if (badgeEl) badgeEl.textContent = data.printer || "Принтер";
    if (weightEl) weightEl.textContent = data.weight || "0";
    if (dateEl) dateEl.textContent = data.date || "-";

    const slider = document.getElementById("scrap-pct-slider");
    if (slider) slider.value = 50;
    updateScrapCalculations();

    const modal = document.getElementById("scrap-modal");
    if (modal) modal.classList.add("active");
}

export function closeScrapModal() {
    const modal = document.getElementById("scrap-modal");
    if (modal) modal.classList.remove("active");
    state.activeScrapTarget = null;
}

function updateScrapCalculations() {
    if (!state.activeScrapTarget) return;
    const slider = document.getElementById("scrap-pct-slider");
    const pct = parseInt(slider?.value || 50, 10);
    const weight = parseFloat(state.activeScrapTarget.weight || 0);

    const wasted = Math.round(weight * (pct / 100.0) * 10) / 10;
    const refund = Math.max(0, Math.round((weight - wasted) * 10) / 10);

    const pctDisp = document.getElementById("scrap-pct-display");
    const wastedEl = document.getElementById("scrap-wasted-grams");
    const refundEl = document.getElementById("scrap-refund-grams");

    if (pctDisp) pctDisp.textContent = `${pct}%`;
    if (wastedEl) wastedEl.textContent = wasted.toFixed(1);
    if (refundEl) refundEl.textContent = refund.toFixed(1);
}

export async function submitMarkScrap() {
    if (!state.activeScrapTarget) return;
    const ts = document.getElementById("scrap-entry-ts")?.value;
    const slider = document.getElementById("scrap-pct-slider");
    const pct = parseInt(slider?.value || 50, 10);
    const weight = parseFloat(state.activeScrapTarget.weight || 0);
    const wasted = Math.round(weight * (pct / 100.0) * 10) / 10;
    const refund = Math.max(0, Math.round((weight - wasted) * 10) / 10);
    const reason = document.getElementById("scrap-reason-select")?.value || "Брак";
    const shouldRefund = document.getElementById("scrap-refund-checkbox")?.checked ?? true;

    const payload = {
        timestamp: parseFloat(ts),
        wasted_weight_g: wasted,
        refund_grams: shouldRefund ? refund : 0.0,
        reason: reason,
        printer_id: document.getElementById("scrap-printer-id")?.value || null,
        slot_key: document.getElementById("scrap-slot-key")?.value || null,
        spool_id: document.getElementById("scrap-spool-id")?.value || null,
    };

    const btn = document.getElementById("btn-submit-scrap");
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Збереження...`;
    }

    try {
        const resData = await markScrapApi(payload);
        if (resData.status === "ok") {
            triggerHaptic("success");
            closeScrapModal();
            alert(`⚠️ Брак зафіксовано (${wasted}г)!${shouldRefund && refund > 0 ? ` Повернено ${refund}г на баланс котушки.` : ''}`);
            await loadHistory();
        } else {
            triggerHaptic("error");
            alert(`Помилка: ${resData.error || "Не вдалося зберегти брак"}`);
        }
    } catch (err) {
        triggerHaptic("error");
        console.error("Scrap submit error:", err);
        alert("Помилка зв'язку при збереженні браку.");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-check"></i> Зафіксувати брак та списати`;
        }
    }
}

export async function deleteHistoryItem(ts) {
    if (ts && confirm("Видалити цей запис із історії?")) {
        try {
            await deleteHistoryItemApi(ts);
            await loadHistory();
        } catch (e) {
            console.error("Delete history error:", e);
        }
    }
}

export function initHistoryEventListeners() {
    ["history-filter-search", "history-filter-printer", "history-filter-date"].forEach(id => {
        document.getElementById(id)?.addEventListener("input", applyHistoryFilters);
        document.getElementById(id)?.addEventListener("change", applyHistoryFilters);
    });
    document.getElementById("scrap-pct-slider")?.addEventListener("input", updateScrapCalculations);
    document.getElementById("btn-submit-scrap")?.addEventListener("click", submitMarkScrap);
    document.getElementById("close-scrap-modal")?.addEventListener("click", closeScrapModal);
}
