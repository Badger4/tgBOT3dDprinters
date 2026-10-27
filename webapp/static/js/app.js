/**
 * 3D Farm Manager - Main Application Entrypoint
 * Modular ES Architecture
 */

import { setupFetchInterceptor, api } from "./modules/api.js";
import { state, initLegacyStateBridges } from "./modules/state.js";
import { escapeHtml, formatRemainingTime, getPrinterStatusInfo, triggerHaptic } from "./modules/utils.js";
import { initSSEStream, setupVisibilityHandler } from "./modules/sse.js";
import { initCommercialCalculator, loadCommercialPresets, recalculateCommercial } from "./modules/commercial.js";
import { fetchPrinters, renderPrinters, openPrinterModal, closePrinterModal, initPrintersModule, updatePrinterModalContent } from "./modules/printers.js";
import { loadMaterials, renderFilteredSpoolsInventory, openAddSpoolModal, closeSpoolModal, submitSaveSpool, openAssignSpoolModal, closeAssignSpoolModal, confirmAssignSpool, openSpoolMovementsModal, closeSpoolMovementsModal, openSpoolMovementsFor, initSpoolsModule } from "./modules/spools.js";
import { loadParts, renderPartsList, openAddPartModal, closeAddPartModal, submitSavePart, adjustPartQuantity, deletePart, showPartDetails, closePartDetailsModal, initPartsModule, triggerPrintPartById } from "./modules/parts.js";
import { loadHistory, renderHistoryList, openScrapModal, closeScrapModal, submitMarkScrap, initHistoryModule } from "./modules/history.js";
import { loadSettings, saveSettings, setAppLanguage, applyLanguageDictionary, openPrinterSettingsModal, initSettingsModule } from "./modules/settings.js";
import { initModalsModule, showToast, updateBackButton, closeTopmostModal } from "./modules/modals.js";

// ============================================================================
// Backward-Compatibility Facades on Window
// Required for inline onclick handlers in index.html and Telegram WebApp integration
// ============================================================================
window.openAddSpoolModal = openAddSpoolModal;
window.closeSpoolModal = closeSpoolModal;
window.submitSaveSpool = submitSaveSpool;
window.openAssignSpoolModal = openAssignSpoolModal;
window.closeAssignSpoolModal = closeAssignSpoolModal;
window.confirmAssignSpool = confirmAssignSpool;
window.openSpoolMovementsModal = openSpoolMovementsModal;
window.closeSpoolMovementsModal = closeSpoolMovementsModal;
window.openSpoolMovementsFor = openSpoolMovementsFor;

window.openAddPartModal = openAddPartModal;
window.closePartDetailsModal = closePartDetailsModal;
window.submitSavePart = submitSavePart;
window.showPartDetails = showPartDetails;
window.triggerPrintPartById = triggerPrintPartById;

window.closeScrapModal = closeScrapModal;
window.submitMarkScrap = submitMarkScrap;

window.openPrinterModal = openPrinterModal;
window.closePrinterModal = closePrinterModal;
window.openPrinterSettingsModal = openPrinterSettingsModal;

window.loadMaterials = loadMaterials;
window.loadMaterialsGlobal = loadMaterials;
window.loadParts = loadParts;
window.loadHistory = loadHistory;
window.fetchPrinters = fetchPrinters;
window.showToast = showToast;
window.recalculateCommercial = recalculateCommercial;
window.loadCommercialPresets = loadCommercialPresets;

// ============================================================================
// Header 3MF Upload & Quick Action Modal
// ============================================================================
function initHeaderFileUpload() {
    const uploadBtn = document.getElementById("upload-file-btn");
    const fileInput = document.getElementById("file-upload-input");
    const fileActionModal = document.getElementById("file-action-modal");
    const closeFileModalBtn = document.getElementById("close-file-action-modal");
    const btnChoiceCalc = document.getElementById("btn-choice-calc");
    const btnChoicePrint = document.getElementById("btn-choice-print");
    const filePrintPanel = document.getElementById("file-print-panel");
    const filePrintersList = document.getElementById("file-printers-list");

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
                uploadBtn.innerHTML = `🚀 Завантажити .3mf`;
                fileInput.value = "";

                if (data.status === "ok") {
                    state.uploadedFileData = data;
                    const elFilename = document.getElementById("file-modal-filename");
                    const elModel = document.getElementById("file-modal-model");
                    const elType = document.getElementById("file-modal-type") || document.getElementById("file-modal-filament");
                    const elNozzle = document.getElementById("file-modal-nozzle");
                    const elWeight = document.getElementById("file-modal-weight");
                    const elTime = document.getElementById("file-modal-time");

                    if (elFilename) elFilename.textContent = data.filename || "";
                    if (elModel) elModel.textContent = data.printer_model || "Невизначено";
                    if (elType) elType.textContent = data.filament_type || "PLA";
                    if (elNozzle) elNozzle.textContent = `${data.nozzle_diameter || "0.4"} мм`;
                    if (elWeight) elWeight.textContent = `${data.weight_g} г`;
                    if (elTime) elTime.textContent = `${data.time_mins} хв`;

                    if (filePrintPanel) filePrintPanel.style.display = "none";
                    if (fileActionModal) fileActionModal.classList.add("active");
                } else {
                    alert(`Помилка аналізу файлу: ${data.error || "Невідома"}`);
                }
            } catch (err) {
                uploadBtn.disabled = false;
                uploadBtn.innerHTML = `🚀 Завантажити .3mf`;
                console.error("File upload error:", err);
                alert(`Не вдалося завантажити файл: ${err.message || err}`);
            }
        });
    }

    if (closeFileModalBtn && fileActionModal) {
        closeFileModalBtn.addEventListener("click", () => {
            fileActionModal.classList.remove("active");
        });
    }

    if (btnChoiceCalc && fileActionModal) {
        btnChoiceCalc.addEventListener("click", async () => {
            triggerHaptic("medium");
            if (!state.uploadedFileData) return;

            fileActionModal.classList.remove("active");

            // Switch to Commercial Tab
            document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
            document.querySelectorAll(".tab-page").forEach(p => p.classList.remove("active"));

            const commNavBtn = document.querySelector('.nav-btn[data-tab="tab-commercial"]');
            if (commNavBtn) commNavBtn.classList.add("active");
            document.getElementById("tab-commercial")?.classList.add("active");

            const weightInput = document.getElementById("calc-weight-g");
            const timeInput = document.getElementById("calc-time-mins");
            if (weightInput) weightInput.value = state.uploadedFileData.weight_g || 100;
            if (timeInput) timeInput.value = state.uploadedFileData.time_mins || 60;

            await loadCommercialPresets();
            await recalculateCommercial();
        });
    }

    if (btnChoicePrint && filePrintPanel && filePrintersList) {
        btnChoicePrint.addEventListener("click", () => {
            triggerHaptic("medium");
            if (!state.uploadedFileData) return;

            filePrintPanel.style.display = "block";

            const printers = state.uploadedFileData.printers || [];
            filePrintersList.innerHTML = printers.map(p => {
                let badgeText = '✅ Сумісний';
                if (!p.compatible) {
                    if (p.reason_type === 'NOZZLE') {
                        badgeText = '🛑 Несумісне сопло';
                    } else if (p.reason_type === 'FILAMENT') {
                        badgeText = '🛑 Несумісність пластику';
                    } else {
                        badgeText = '🛑 Несумісна модель';
                    }
                }
                const pNozzle = p.nozzle_diameter ? ` | 🎯 ${p.nozzle_diameter}мм` : '';
                return `
                <div class="spool-item mb-2" style="flex-direction:column; align-items:stretch;">
                    <div class="d-flex justify-content-between align-items-center">
                        <div class="spool-left">
                            <i class="fa-solid fa-print ${p.state === 'RUNNING' ? 'color-green' : 'color-purple'}" style="font-size:20px;"></i>
                            <div class="spool-details">
                                <h4>${escapeHtml(p.name)}</h4>
                                <p>Статус: <strong>${p.state}</strong>${pNozzle} | ${badgeText}</p>
                            </div>
                        </div>
                        <button class="btn btn-sm ${p.compatible ? 'btn-success' : 'btn-outline-danger'} btn-start-print-job" data-id="${p.id}" ${p.state === 'RUNNING' ? 'disabled' : ''}>
                            ${p.state === 'RUNNING' ? 'Зайнятий' : (p.compatible ? '🚀 Друк' : '🛑 Заблоковано')}
                        </button>
                    </div>
                    ${!p.compatible ? `<div class="mt-2 p-2" style="background:rgba(239,68,68,0.15); border:1px solid rgba(239,68,68,0.4); border-radius:6px; font-size:12px; color:#fca5a5;">${escapeHtml((p.reason || "").replace(/<[^>]*>/g, ""))}</div>` : ''}
                </div>`;
            }).join("");

            document.querySelectorAll(".btn-start-print-job").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const printerId = btn.getAttribute("data-id");
                    const targetP = (state.uploadedFileData.printers || []).find(x => x.id === printerId);
                    if (targetP && !targetP.compatible) {
                        alert((targetP.reason || "").replace(/<[^>]*>/g, ""));
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
                                file_token: state.uploadedFileData.file_token,
                                filename: state.uploadedFileData.filename,
                                ams_slot: (targetP && targetP.matched_ams_slot) ? targetP.matched_ams_slot : null
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
}

// ============================================================================
// Bottom Tab Navigation
// ============================================================================
function initTabNavigation() {
    const navButtons = document.querySelectorAll(".nav-btn");
    const tabPages = document.querySelectorAll(".tab-page");

    navButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            triggerHaptic("selection");
            const targetTab = btn.getAttribute("data-tab");

            navButtons.forEach(b => b.classList.remove("active"));
            tabPages.forEach(p => p.classList.remove("active"));

            btn.classList.add("active");
            const page = document.getElementById(targetTab);
            if (page) page.classList.add("active");

            if (targetTab === "tab-commercial") loadCommercialPresets();
            else if (targetTab === "tab-materials") loadMaterials();
            else if (targetTab === "tab-parts") loadParts(false);
            else if (targetTab === "tab-history") loadHistory();
            else if (targetTab === "tab-settings") loadSettings();
        });
    });
}

// ============================================================================
// Main Application Bootstrapper
// ============================================================================
async function bootstrapApp() {
    // 1. Setup fetch credentials & token interceptor
    setupFetchInterceptor();

    // 2. Setup legacy state bridges for backward compatibility
    initLegacyStateBridges();

    // 3. Apply active language dictionary
    applyLanguageDictionary(state.currentLanguage);

    // 4. Initialize all feature modules
    initModalsModule();
    initPrintersModule();
    initSpoolsModule();
    initCommercialCalculator();
    initPartsModule();
    initHistoryModule();
    initSettingsModule();
    initHeaderFileUpload();
    initTabNavigation();

    // 5. Wire top-bar refresh button
    const refreshBtn = document.getElementById("refresh-btn");
    if (refreshBtn) {
        refreshBtn.addEventListener("click", () => {
            triggerHaptic("light");
            fetchPrinters();
        });
    }

    // 6. Initial Data Fetching
    fetchPrinters();
    loadCommercialPresets();
    recalculateCommercial();

    // 7. Live SSE Stream & Backup Polling Lifecycle
    const startBackupPolling = () => {
        if (!state.pollInterval && !document.hidden) {
            state.pollInterval = setInterval(fetchPrinters, 4000);
        }
    };

    const stopBackupPolling = () => {
        if (state.pollInterval) {
            clearInterval(state.pollInterval);
            state.pollInterval = null;
        }
    };

    const handleSSEPrinters = (printers) => {
        if (!Array.isArray(printers)) return;
        state.printers = printers;
        renderPrinters(state.printers);
        if (state.selectedPrinterId && document.getElementById("printer-modal")?.classList.contains("active")) {
            const currentP = state.printers.find(p => p.id === state.selectedPrinterId);
            if (currentP) updatePrinterModalContent(currentP);
        }
    };

    initSSEStream({
        onOpen: () => {
            // SSE stream connected: stop backup polling to prevent race conditions and redundant network traffic
            stopBackupPolling();
        },
        onPrinters: handleSSEPrinters,
        onFinish: () => {
            triggerHaptic("success");
            const activeTab = document.querySelector(".tab-page.active")?.id;
            if (activeTab === "tab-history") loadHistory();
        },
        onError: (err) => {
            console.warn("SSE stream disconnected, activating backup polling:", err);
            startBackupPolling();
        }
    });

    setupVisibilityHandler({
        onVisible: () => {
            fetchPrinters();
            if (!window.EventSource) {
                startBackupPolling();
            }
        },
        onHidden: () => {
            stopBackupPolling();
        }
    });

    // Only start initial polling if EventSource is unsupported in this environment
    if (!window.EventSource) {
        startBackupPolling();
    }
}

// Ensure execution when DOM is ready
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrapApp);
} else {
    bootstrapApp();
}
