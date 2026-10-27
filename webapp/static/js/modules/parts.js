/**
 * 3D Farm Manager - Parts Warehouse & 3MF Job Dispatching
 */

import { escapeHtml, formatTimeMins, getBambuModelCode, normalizeFilamentName, triggerHaptic } from "./utils.js";
import { state } from "./state.js";
import {
    fetchPartsApi,
    savePartApi,
    deletePartApi,
    printPartApi,
    uploadFileApi,
    uploadImageApi
} from "./api.js";

export function filterParts(partsMapOrArray, query = "") {
    const list = Array.isArray(partsMapOrArray)
        ? partsMapOrArray
        : Object.values(partsMapOrArray || {});
    const q = (query || "").trim().toLowerCase();
    if (!q) return list;

    return list.filter(p => {
        const nameMatch = p.name && String(p.name).toLowerCase().includes(q);
        const modelMatch = p.printer_model && String(p.printer_model).toLowerCase().includes(q);
        const filMatch = p.filament_type && String(p.filament_type).toLowerCase().includes(q);
        const fileMatch = (p.three_mf || p.three_mf_name) && String(p.three_mf || p.three_mf_name).toLowerCase().includes(q);
        return Boolean(nameMatch || modelMatch || filMatch || fileMatch);
    });
}

export async function loadParts(fromCache = false) {
    const partsListEl = document.getElementById("parts-list");
    const partsBadgeEl = document.getElementById("parts-summary-badge");
    if (!partsListEl) return;

    try {
        if (!fromCache || !state.parts || Object.keys(state.parts).length === 0) {
            const data = await fetchPartsApi();
            state.parts = data || {};
        }

        const partSearchInput = document.getElementById("part-search-input");
        const partSearchClearBtn = document.getElementById("part-search-clear-btn");
        const searchQuery = partSearchInput ? partSearchInput.value.trim().toLowerCase() : "";

        if (partSearchClearBtn) {
            partSearchClearBtn.style.display = searchQuery ? "flex" : "none";
        }

        const allParts = Object.values(state.parts || {});
        let totalCount = 0;
        allParts.forEach(p => {
            const cnt = parseInt(p.count || p.quantity || 0, 10);
            totalCount += cnt;
        });

        if (partsBadgeEl) {
            partsBadgeEl.textContent = `${totalCount} шт`;
        }

        const filteredParts = filterParts(allParts, searchQuery);

        if (filteredParts.length === 0) {
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
        filteredParts.forEach(part => {
            const count = parseInt(part.count || part.quantity || 0, 10);
            const safeId = escapeHtml(String(part.id));
            const threeMf = part.three_mf ? escapeHtml(part.three_mf_name || part.three_mf) : "";
            const imageSrc = part.image && (part.image.startsWith("http") || part.image.startsWith("/")) ? part.image : "";
            const pModelBadge = part.printer_model && part.printer_model !== 'Unknown'
                ? `<span class="badge badge-outline text-info border-info ms-2" style="font-size: 0.75rem;"><i class="fa-solid fa-print"></i> ${escapeHtml(part.printer_model)}</span>`
                : '';
            const pNozzleBadge = part.nozzle_diameter
                ? `<span class="badge badge-outline text-success border-success ms-1" style="font-size: 0.75rem;"><i class="fa-solid fa-circle-dot"></i> ${escapeHtml(part.nozzle_diameter)}мм</span>`
                : '';

            html += `
                <div class="spool-item-card part-item-card glass-card mb-3 p-3">
                    <div class="part-card-header">
                        <div class="part-card-main-info" data-id="${safeId}" title="Натисніть для перегляду деталей моделі">
                            ${imageSrc
                                ? `<img src="${escapeHtml(imageSrc)}" class="part-preview-thumb" alt="${escapeHtml(part.name)}">`
                                : `<div class="part-preview-placeholder"><i class="fa-solid fa-cube color-green fs-5"></i></div>`
                            }
                            <div class="part-card-title-group">
                                <div class="part-card-title-row">
                                    <h4 class="m-0 text-light fs-6 fw-bold">
                                        <i class="fa-solid fa-puzzle-piece color-green me-1"></i> ${escapeHtml(part.name)}
                                    </h4>
                                    ${pModelBadge}${pNozzleBadge}
                                </div>
                                <small class="text-muted" style="font-size: 0.72rem;"><i class="fa-solid fa-circle-info"></i> Натисніть для детальної інформації</small>
                            </div>
                        </div>
                        <div class="part-card-actions">
                            <button class="icon-btn btn-edit-part" data-id="${safeId}" title="Редагувати">
                                <i class="fa-solid fa-pen-to-square"></i>
                            </button>
                            <button class="icon-btn btn-delete-part text-danger" data-id="${safeId}" title="Видалити">
                                <i class="fa-solid fa-trash"></i>
                            </button>
                        </div>
                    </div>

                    ${threeMf ? `
                        <div class="part-card-file-row" data-id="${safeId}" style="cursor: pointer;" title="Натисніть для детальної інформації">
                            <i class="fa-solid fa-file"></i>
                            <span><strong>.3mf:</strong> ${threeMf}</span>
                        </div>
                    ` : ''}

                    <div class="part-card-footer">
                        <button class="btn btn-sm btn-primary btn-print-part" data-id="${safeId}">
                            <i class="fa-solid fa-rocket"></i> Кинути на друк
                        </button>
                        <div class="part-card-qty-counter">
                            <button class="btn btn-sm btn-outline btn-part-qty-dec" data-id="${safeId}">-</button>
                            <strong class="fs-6 px-1 text-info">${count} шт</strong>
                            <button class="btn btn-sm btn-outline btn-part-qty-inc" data-id="${safeId}">+</button>
                        </div>
                    </div>
                </div>
            `;
        });

        partsListEl.innerHTML = html;
    } catch (e) {
        console.error("Failed loading parts:", e);
    }
}

export function openAddPartModal(part = null) {
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

    const progressEl = document.getElementById("part-3mf-upload-progress");
    if (progressEl) {
        progressEl.style.display = "none";
        progressEl.textContent = "";
    }

    if (!modal) return;

    if (threeMfFileInput) threeMfFileInput.value = "";
    if (partImageFileInput) partImageFileInput.value = "";

    if (part && typeof part === "object") {
        state.editingPartId = part.id || null;
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
        state.editingPartId = null;
        if (titleEl) titleEl.textContent = "➕ Нова деталь";
        if (editIdInput) editIdInput.value = "";
        if (nameInput) nameInput.value = "";
        if (imageInput) imageInput.value = "";
        if (countInput) countInput.value = 1;
        if (threeMfInput) threeMfInput.value = "";
        if (previewWrap) previewWrap.style.display = "none";
        if (detectedModelEl) detectedModelEl.style.display = "none";
    }

    triggerHaptic("light");
    modal.classList.add("active");
}

export function closeAddPartModal() {
    const modal = document.getElementById("add-part-modal");
    if (modal) modal.classList.remove("active");
    state.editingPartId = null;
    const progressEl = document.getElementById("part-3mf-upload-progress");
    if (progressEl) {
        progressEl.style.display = "none";
        progressEl.textContent = "";
    }
}

export async function submitSavePart(e) {
    if (e) {
        e.preventDefault();
        e.stopPropagation();
    }
    const saveBtn = document.getElementById("save-part-submit");
    if (saveBtn && saveBtn.disabled) return;

    const editId = document.getElementById("edit-part-id")?.value;
    const name = document.getElementById("part-name-input")?.value?.trim();
    const count = parseInt(document.getElementById("part-count-input")?.value || "1", 10);
    const image = document.getElementById("part-image-input")?.value?.trim();
    const threeMf = document.getElementById("part-3mf-input")?.value?.trim();

    if (!name) {
        alert("⚠️ Будь ласка, введіть назву деталі!");
        return;
    }

    const origText = saveBtn ? saveBtn.innerHTML : "";
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin me-1"></i> Збереження...`;
    }

    const payload = {
        name,
        count: isNaN(count) ? 1 : Math.max(0, count),
        image: image || "",
        three_mf: threeMf || ""
    };
    if (editId) payload.id = editId;

    try {
        const result = await savePartApi(payload);
        const isSuccess = Boolean(result && !result.error && (result.status === "ok" || result.part));
        if (isSuccess) {
            triggerHaptic("success");
            closeAddPartModal();
            await loadParts();
        } else {
            triggerHaptic("error");
            alert("⚠️ Помилка збереження деталі: " + (result?.error || "Невідомо"));
        }
    } catch (err) {
        triggerHaptic("error");
        console.error("Save part error:", err);
        alert("⚠️ Мережева помилка збереження деталі.");
    } finally {
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.innerHTML = origText || "💾 Зберегти деталь";
        }
    }
}

export function editPartModal(id) {
    const part = state.parts[id];
    if (part) openAddPartModal(part);
}

export async function adjustPartQuantity(id, delta) {
    const part = state.parts[id];
    if (!part) return;
    const cur = parseInt(part.count || part.quantity || 0, 10);
    const next = Math.max(0, cur + delta);
    part.count = next;
    triggerHaptic("selection");
    await loadParts(true);
    try {
        await savePartApi({ id, count: next });
    } catch (e) {
        console.error("Adjust qty error:", e);
    }
}

export async function deletePart(id) {
    const part = state.parts[id];
    const name = part?.name || "деталь";
    if (confirm(`Ви дійсно хочете видалити деталь "${name}" зі складу?`)) {
        try {
            await deletePartApi(id);
            await loadParts();
        } catch (e) {
            console.error("Delete part error:", e);
        }
    }
}

export function showPartDetails(partId) {
    const part = state.parts[partId];
    if (!part) return;

    const modal = document.getElementById("part-details-modal");
    const progressEl = document.getElementById("part-3mf-upload-progress");
    if (progressEl) {
        progressEl.style.display = "none";
        progressEl.textContent = "";
    }

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
                ? `<img src="${escapeHtml(imageSrc)}" class="part-details-full-img" alt="${escapeHtml(part.name)}">`
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
                <span class="part-detail-label"><i class="fa-solid fa-circle-dot color-green"></i> Діаметр сопла</span>
                <span class="part-detail-value">${escapeHtml(part.nozzle_diameter || '0.4')} мм</span>
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
            closePartDetailsModal();
            triggerPrintPartById(part.id);
        };
    }

    triggerHaptic("light");
    modal.classList.add("active");
}

export function closePartDetailsModal() {
    const modal = document.getElementById("part-details-modal");
    if (modal) modal.classList.remove("active");
}

export async function triggerPrintPartById(partId) {
    const part = state.parts[partId];
    if (!part) return;

    if (!state.printers || state.printers.length === 0) {
        alert("⚠️ Немає активних принтерів у фермі!");
        return;
    }

    const modal = document.createElement("div");
    modal.className = "modal-backdrop active modal-nested";
    modal.innerHTML = `
        <div class="modal-window">
            <div class="modal-header">
                <h3>🚀 Обрати принтер для друку</h3>
                <button class="icon-btn-close btn-close-printer-select"><i class="fa-solid fa-xmark"></i></button>
            </div>
            <div class="modal-body">
                <p class="text-muted" style="font-size: 13px;">Деталь: <strong>${escapeHtml(part.name)}</strong></p>
                <div class="d-flex flex-column gap-2">
                    ${state.printers.map(p => `
                        <button class="btn btn-outline d-flex justify-content-between align-items-center btn-launch-print-part" data-printer-id="${p.id}">
                            <span>🖨️ ${escapeHtml(p.name)} (${p.printer_model || p.model || "Bambu"})</span>
                            <span class="badge ${p.state === 'RUNNING' ? 'badge-warning' : 'badge-success'}">${p.state || 'IDLE'}</span>
                        </button>
                    `).join("")}
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);

    const closeModal = () => modal.remove();
    modal.querySelectorAll(".btn-close-printer-select").forEach(b => b.addEventListener("click", closeModal));

    modal.querySelectorAll(".btn-launch-print-part").forEach(btn => {
        btn.addEventListener("click", async () => {
            const targetPid = btn.getAttribute("data-printer-id");
            const selectedPrinter = state.printers.find(p => p.id === targetPid);
            if (!selectedPrinter) return;

            closeModal();
            await executeLaunchPartPrint(part, selectedPrinter);
        });
    });
}

async function executeLaunchPartPrint(part, selectedPrinter) {
    const targetM = part.printer_model || '';
    const partFilament = part.filament_type || '';
    const printerFilament = selectedPrinter.filament_type || '';

    if (targetM && targetM !== 'Unknown') {
        const targetCode = getBambuModelCode(targetM);
        const selModel = selectedPrinter.printer_model || selectedPrinter.model || selectedPrinter.name;
        const printerCode = getBambuModelCode(selModel);
        if (targetCode !== 'UNKNOWN' && printerCode !== 'UNKNOWN' && targetCode !== printerCode) {
            const corexyFamily = ["@BBL P1P", "@BBL P1S", "@BBL P2S", "@BBL X1C", "@BBL X1E"];
            if (corexyFamily.includes(targetCode) && corexyFamily.includes(printerCode)) {
                if (!confirm(`⚠️ Увага: деталь нарізано для ${targetM}, а обраний принтер ${selectedPrinter.name} (${selModel}).\nПлатформа 256x256 однакова, але моделі відрізняються.\n\nПродовжити запуск друку?`)) {
                    return;
                }
            } else {
                alert(`🛑 Помилка сумісності моделі принтера!\nДеталь нарізано для ${targetM}, а принтер ${selectedPrinter.name} (${printerCode}) не є сумісним.`);
                return;
            }
        }
    }

    if (partFilament) {
        if (!printerFilament || printerFilament === 'Невизначено') {
            alert(`🛑 Помилка: на принтері ${selectedPrinter.name} не встановлено пластик!\nДля друку потрібен пластик "${partFilament}".`);
            return;
        }
        const normPartFil = normalizeFilamentName(partFilament);
        const normPrinterFil = normalizeFilamentName(printerFilament);
        if (normPartFil && normPrinterFil && normPartFil !== normPrinterFil) {
            alert(`🛑 Помилка сумісності пластику!\nДеталь вимагає пластик "${partFilament}", а на принтері ${selectedPrinter.name} встановлено "${printerFilament}".`);
            return;
        }
    }

    const partNozzle = part.nozzle_diameter ? parseFloat(part.nozzle_diameter) : null;
    const printerNozzle = selectedPrinter.nozzle_diameter ? parseFloat(selectedPrinter.nozzle_diameter) : 0.4;
    if (partNozzle && Math.abs(partNozzle - printerNozzle) > 0.01) {
        alert(`🛑 Помилка сумісності сопла!\nДеталь нарізано під сопло ${partNozzle} мм, а на принтері ${selectedPrinter.name} встановлено ${printerNozzle} мм.`);
        return;
    }

    const partWeight = parseFloat(part.weight_g || 0);
    const activeSlot = String(selectedPrinter.active_slot_key || "254");
    const remGrams = (selectedPrinter.ams_slots && selectedPrinter.ams_slots[activeSlot] !== undefined)
        ? parseFloat(selectedPrinter.ams_slots[activeSlot])
        : parseFloat(selectedPrinter.filament_grams_left !== undefined ? selectedPrinter.filament_grams_left : (selectedPrinter.filament_grams || 0));

    if (partWeight > 0 && remGrams > 0) {
        if (remGrams < partWeight) {
            if (!confirm(`⚠️ УВАГА: Недостатньо пластику на котушці!\n\nМодель вимагає ~${Math.round(partWeight)} г, а розрахунковий залишок на принтері ${selectedPrinter.name} становить лише ${Math.round(remGrams)} г.\n\nВи впевнені, що хочете запустити друк?`)) {
                return;
            }
        } else if (remGrams - partWeight <= 15) {
            if (!confirm(`⚠️ Залишок нитки критично близький до ваги моделі!\n\nПотрібно: ~${Math.round(partWeight)} г | Залишок: ${Math.round(remGrams)} г (запас менше 15 г).\n\nПродовжити запуск друку?`)) {
                return;
            }
        }
    }

    try {
        const result = await printPartApi(part.id, selectedPrinter.id);
        if (result.status === "ok") {
            alert(`🚀 Друк деталі "${part.name}" успішно запущено на принтері [${selectedPrinter.name}]!`);
        } else {
            alert(`⚠️ Помилка запуску: ${result.error || "Невідома помилка"}`);
        }
    } catch (err) {
        console.error("Print part error:", err);
        alert("⚠️ Помилка зв'язку при запуску друку.");
    }
}

export function initPartsModule() {
    if (state.partsModuleBound) return;
    state.partsModuleBound = true;

    // 1. Search input & clear button
    const partSearchInput = document.getElementById("part-search-input");
    const partSearchClearBtn = document.getElementById("part-search-clear-btn");

    if (partSearchInput) {
        partSearchInput.addEventListener("input", () => {
            if (partSearchClearBtn) {
                partSearchClearBtn.style.display = partSearchInput.value.trim().length > 0 ? "inline-flex" : "none";
            }
            loadParts(true);
        });
    }

    if (partSearchClearBtn && partSearchInput) {
        partSearchClearBtn.addEventListener("click", () => {
            partSearchInput.value = "";
            partSearchClearBtn.style.display = "none";
            partSearchInput.focus();
            loadParts(true);
        });
    }

    // 2. 3MF File input (always wired independently of dropzone presence)
    const fileInput = document.getElementById("part-3mf-file-input");
    if (fileInput) {
        fileInput.addEventListener("change", () => {
            if (fileInput.files?.length) {
                handle3mfFileUpload(fileInput.files[0]);
            }
        });
    }

    // 3. 3MF Dropzone (supports click-to-browse and drag-and-drop)
    const dropZone = document.getElementById("part-3mf-dropzone");
    if (dropZone && fileInput) {
        dropZone.addEventListener("click", () => fileInput.click());
        dropZone.addEventListener("dragover", (e) => {
            e.preventDefault();
            dropZone.classList.add("dragover");
        });
        dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
        dropZone.addEventListener("drop", (e) => {
            e.preventDefault();
            dropZone.classList.remove("dragover");
            if (e.dataTransfer.files?.length) {
                fileInput.files = e.dataTransfer.files;
                handle3mfFileUpload(fileInput.files[0]);
            }
        });
    }

    // 4. Image file input upload
    const imgInput = document.getElementById("part-image-file-input");
    if (imgInput) {
        imgInput.addEventListener("change", async () => {
            if (!imgInput.files?.length) return;
            const formData = new FormData();
            formData.append("file", imgInput.files[0]);
            try {
                const res = await uploadImageApi(formData);
                if (res.status === "ok" && res.url) {
                    const imgUrlInput = document.getElementById("part-image-input");
                    const previewWrap = document.getElementById("part-image-preview-wrap");
                    const previewImg = document.getElementById("part-image-preview");
                    if (imgUrlInput) imgUrlInput.value = res.url;
                    if (previewImg) previewImg.src = res.url;
                    if (previewWrap) previewWrap.style.display = "block";
                    triggerHaptic("success");
                }
            } catch (e) {
                console.error("Upload image error:", e);
                triggerHaptic("error");
            }
        });
    }

    // 5. Close and submit action buttons
    document.getElementById("close-add-part-modal")?.addEventListener("click", closeAddPartModal);
    document.getElementById("cancel-part-submit")?.addEventListener("click", closeAddPartModal);
    document.getElementById("save-part-submit")?.addEventListener("click", submitSavePart);
}

export const initPartUploadListeners = initPartsModule;

async function handle3mfFileUpload(file) {
    if (!file) return;
    const progressEl = document.getElementById("part-3mf-upload-progress");
    const nameInput = document.getElementById("part-name-input");
    const threeMfInput = document.getElementById("part-3mf-input");
    const detectedModelEl = document.getElementById("part-detected-model");

    if (progressEl) {
        progressEl.style.display = "block";
        progressEl.innerHTML = `<i class="fa-solid fa-spinner fa-spin me-1"></i> Завантаження та аналіз .3mf файлу...`;
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
        const res = await uploadFileApi(formData);
        if (res && res.status === "ok") {
            if (threeMfInput) threeMfInput.value = res.file_token || res.filename || file.name;
            if (nameInput && !nameInput.value.trim()) {
                nameInput.value = file.name.replace(/\.(3mf|gcode)$/i, "");
            }
            if (detectedModelEl && res.printer_model && res.printer_model !== "Unknown") {
                const filInfo = res.filament_type ? ` (${res.filament_type})` : "";
                const weightInfo = res.weight_g ? ` • ${res.weight_g}г` : "";
                detectedModelEl.textContent = `🖨️ Визначена модель: ${res.printer_model}${filInfo}${weightInfo}`;
                detectedModelEl.style.display = "block";
            }
            if (progressEl) {
                progressEl.style.display = "block";
                progressEl.innerHTML = `<span class="text-success"><i class="fa-solid fa-check me-1"></i> Файл успішно завантажено (${escapeHtml(file.name)})</span>`;
            }
            triggerHaptic("success");
        } else {
            if (progressEl) {
                progressEl.style.display = "block";
                progressEl.innerHTML = `<span class="text-danger"><i class="fa-solid fa-circle-exclamation me-1"></i> ${escapeHtml(res?.error || "Не вдалося завантажити")}</span>`;
            }
            triggerHaptic("error");
        }
    } catch (e) {
        console.error("3mf upload error:", e);
        if (progressEl) {
            progressEl.style.display = "block";
            progressEl.innerHTML = `<span class="text-danger"><i class="fa-solid fa-circle-exclamation me-1"></i> Мережева помилка завантаження файлу.</span>`;
        }
        triggerHaptic("error");
    }
}

export const renderPartsList = loadParts;
