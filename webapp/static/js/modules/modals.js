/**
 * 3D Farm Manager - Modals, Gestures & Centralized Event Delegation Module
 */

import { triggerHaptic } from "./utils.js";
import { state } from "./state.js";
import { fetchPrinters, openPrinterModal, closePrinterModal, closeFullscreenCamera } from "./printers.js";
import { handleQuickPauseResume, handleQuickCamPeek, handleQuickLightToggle, handleQuickSpeedCycle } from "./cockpit.js";
import { openPrinterSettingsModal } from "./settings.js";
import { openSpoolMovementsFor, openAssignSpoolModal, openAddSpoolModal, loadMaterials } from "./spools.js";
import { adjustPartQuantity, triggerPrintPartById, openAddPartModal, deletePart, showPartDetails, loadParts } from "./parts.js";
import { reprintJob, deleteHistoryItem, openScrapModal, loadHistory } from "./history.js";
import { loadCommercialPresets } from "./commercial.js";

/**
 * Update Telegram BackButton visibility based on active modals
 */
export function updateBackButton() {
    const tg = window.Telegram?.WebApp;
    if (!tg || !tg.BackButton) return;

    const activeModals = document.querySelectorAll('.modal-backdrop.active, .camera-fullscreen-backdrop.active, [id$="-modal"].active');
    if (activeModals.length > 0) {
        tg.BackButton.show();
    } else {
        tg.BackButton.hide();
    }
}

/**
 * Close the topmost active modal
 */
export function closeTopmostModal() {
    const activeModals = Array.from(document.querySelectorAll('.modal-backdrop.active, .camera-fullscreen-backdrop.active, [id$="-modal"].active'));
    if (activeModals.length > 0) {
        const lastModal = activeModals[activeModals.length - 1];
        lastModal.classList.remove('active');
        if (lastModal.style.display === 'flex' || lastModal.style.display === 'block') {
            lastModal.style.display = 'none';
        }
        if (lastModal.id === "printer-modal" || lastModal.id === "camera-fullscreen-modal") {
            const cImg = document.getElementById("camera-snapshot-img");
            const fsImg = document.getElementById("fullscreen-camera-img");
            if (cImg) cImg.src = "";
            if (fsImg) fsImg.src = "";
            state.selectedPrinterId = null;
        }
        updateBackButton();
        return true;
    }
    return false;
}

/**
 * Toast Notification system
 */
export function showToast(message, type = "info", duration = 3000) {
    let container = document.getElementById("toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "toast-container";
        container.style.cssText = "position: fixed; top: 16px; left: 50%; transform: translateX(-50%); z-index: var(--z-toast, 2000); display: flex; flex-direction: column; gap: 8px; pointer-events: none; width: max-content; max-width: 90vw;";
        document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.className = `toast-pill toast-${type}`;
    toast.style.cssText = "pointer-events: auto; background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(255, 255, 255, 0.15); color: #f8fafc; padding: 8px 16px; border-radius: 9999px; font-size: 13px; font-weight: 500; box-shadow: 0 4px 12px rgba(0,0,0,0.3); backdrop-filter: blur(8px); display: flex; align-items: center; gap: 8px; animation: toastIn 0.2s ease-out;";

    let icon = '<i class="fa-solid fa-circle-info color-blue"></i>';
    if (type === "success") icon = '<i class="fa-solid fa-circle-check color-green"></i>';
    else if (type === "warning") icon = '<i class="fa-solid fa-triangle-exclamation color-amber"></i>';
    else if (type === "error") icon = '<i class="fa-solid fa-circle-xmark color-red"></i>';

    toast.innerHTML = `${icon} <span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateY(-10px)";
        toast.style.transition = "all 0.25s ease-in";
        setTimeout(() => toast.remove(), 250);
    }, duration);
}

/**
 * Setup mobile touch gestures: Pull-to-Refresh & Bottom-Sheet Swipe-to-Dismiss
 */
export function initGestures() {
    // 1. Pull-to-Refresh Gesture at top of viewport
    let ptrEl = document.querySelector(".ptr-indicator");
    if (!ptrEl) {
        ptrEl = document.createElement("div");
        ptrEl.className = "ptr-indicator";
        ptrEl.innerHTML = `<i class="fa-solid fa-rotate"></i> <span>Потягніть для оновлення</span>`;
        document.body.appendChild(ptrEl);
    }

    let ptrStartY = 0;
    let ptrPulling = false;
    let ptrRefreshing = false;

    document.addEventListener("touchstart", (e) => {
        if (ptrRefreshing || window.scrollY > 2) return;
        const activeModal = document.querySelector(".modal-backdrop.active, .camera-fullscreen-backdrop.active");
        if (activeModal) return;
        ptrStartY = e.touches[0].clientY;
        ptrPulling = true;
    }, { passive: true });

    document.addEventListener("touchmove", (e) => {
        if (!ptrPulling || ptrRefreshing) return;
        if (window.scrollY > 2) {
            ptrPulling = false;
            ptrEl.classList.remove("visible");
            ptrEl.style.transform = "translate(-50%, -70px)";
            return;
        }
        const dy = e.touches[0].clientY - ptrStartY;
        if (dy > 15) {
            const pullOffset = Math.min(40, (dy - 15) * 0.45);
            ptrEl.classList.add("visible");
            ptrEl.style.transform = `translate(-50%, ${pullOffset - 35}px)`;
            const span = ptrEl.querySelector("span");
            if (span) {
                span.textContent = dy > 80 ? "Відпустіть для оновлення" : "Потягніть для оновлення";
            }
        }
    }, { passive: true });

    document.addEventListener("touchend", async (e) => {
        if (!ptrPulling || ptrRefreshing) return;
        ptrPulling = false;
        const endY = e.changedTouches?.[0]?.clientY || ptrStartY;
        const dy = endY - ptrStartY;
        if (dy > 80 && window.scrollY <= 2) {
            ptrRefreshing = true;
            triggerHaptic("medium");
            ptrEl.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>Оновлення...</span>`;
            ptrEl.style.transform = "translate(-50%, 6px)";
            try {
                await fetchPrinters();
                const activeTab = document.querySelector(".nav-btn.active")?.getAttribute("data-tab");
                if (activeTab === "tab-materials") await loadMaterials();
                else if (activeTab === "tab-parts") await loadParts(false);
                else if (activeTab === "tab-history") await loadHistory();
            } catch (_) {}
            setTimeout(() => {
                ptrEl.classList.remove("visible");
                ptrEl.style.transform = "translate(-50%, -70px)";
                ptrEl.innerHTML = `<i class="fa-solid fa-rotate"></i> <span>Потягніть для оновлення</span>`;
                ptrRefreshing = false;
            }, 350);
        } else {
            ptrEl.classList.remove("visible");
            ptrEl.style.transform = "translate(-50%, -70px)";
        }
    }, { passive: true });

    // 2. Mobile Bottom-Sheet Swipe-Down-to-Dismiss on .modal-header
    let sheetStartY = 0;
    let sheetActiveWindow = null;
    let sheetActiveBackdrop = null;

    document.addEventListener("touchstart", (e) => {
        const header = e.target.closest(".modal-header");
        if (!header) return;
        const backdrop = header.closest(".modal-backdrop.active:not(.camera-fullscreen-backdrop)");
        const win = header.closest(".modal-window");
        if (!backdrop || !win) return;
        sheetStartY = e.touches[0].clientY;
        sheetActiveWindow = win;
        sheetActiveBackdrop = backdrop;
        win.style.transition = "none";
    }, { passive: true });

    document.addEventListener("touchmove", (e) => {
        if (!sheetActiveWindow) return;
        const dy = Math.max(0, e.touches[0].clientY - sheetStartY);
        if (dy > 5) {
            sheetActiveWindow.style.transform = `translateY(${dy}px)`;
        }
    }, { passive: true });

    document.addEventListener("touchend", (e) => {
        if (!sheetActiveWindow || !sheetActiveBackdrop) return;
        const endY = e.changedTouches?.[0]?.clientY || sheetStartY;
        const dy = endY - sheetStartY;
        const win = sheetActiveWindow;
        const backdrop = sheetActiveBackdrop;
        sheetActiveWindow = null;
        sheetActiveBackdrop = null;
        win.style.transition = "transform 0.2s ease";
        if (dy > 75) {
            triggerHaptic("light");
            win.style.transform = "";
            const closeBtn = backdrop.querySelector(".icon-btn-close");
            if (closeBtn) {
                closeBtn.click();
            } else {
                backdrop.classList.remove("active");
                updateBackButton();
            }
        } else {
            win.style.transform = "";
        }
    }, { passive: true });

    // 3. Mobile Virtual Keyboard adaptation via visualViewport
    if (window.visualViewport) {
        window.visualViewport.addEventListener("resize", () => {
            const isKeyboardOpen = (window.innerHeight - window.visualViewport.height) > 150;
            document.body.classList.toggle("keyboard-open", isKeyboardOpen);
        });
    }
}

/**
 * Centralized Event Delegation for all main lists & grids
 */
export function initEventDelegation() {
    // 1. Printers Grid delegation
    const pGrid = document.getElementById("printers-grid");
    if (pGrid && !pGrid._delegated) {
        pGrid._delegated = true;
        pGrid.addEventListener("click", (e) => {
            const gearBtn = e.target.closest(".btn-card-gear");
            if (gearBtn) {
                e.stopPropagation();
                const pId = gearBtn.getAttribute("data-id");
                if (pId) openPrinterSettingsModal(pId);
                return;
            }
            const pauseBtn = e.target.closest(".btn-cockpit-pause-resume");
            if (pauseBtn) {
                e.stopPropagation();
                const pId = pauseBtn.getAttribute("data-id");
                if (pId) handleQuickPauseResume(pId, pauseBtn, e);
                return;
            }
            const peekBtn = e.target.closest(".btn-cockpit-cam-peek");
            if (peekBtn) {
                e.stopPropagation();
                const pId = peekBtn.getAttribute("data-id");
                if (pId) handleQuickCamPeek(pId, peekBtn, e);
                return;
            }
            const lightBtn = e.target.closest(".btn-cockpit-light");
            if (lightBtn) {
                e.stopPropagation();
                const pId = lightBtn.getAttribute("data-id");
                if (pId) handleQuickLightToggle(pId, lightBtn, e);
                return;
            }
            const speedBtn = e.target.closest(".btn-cockpit-speed");
            if (speedBtn) {
                e.stopPropagation();
                const pId = speedBtn.getAttribute("data-id");
                if (pId) handleQuickSpeedCycle(pId, speedBtn, e);
                return;
            }
            const card = e.target.closest(".printer-card");
            if (card) {
                const pId = card.getAttribute("data-id");
                if (pId) openPrinterModal(pId);
                return;
            }
        });
    }

    // 2. Dashboard Grid delegation
    const dGrid = document.getElementById("dashboard-grid");
    if (dGrid && !dGrid._delegated) {
        dGrid._delegated = true;
        dGrid.addEventListener("click", (e) => {
            const card = e.target.closest(".glass-card[data-id]");
            if (card) {
                const pId = card.getAttribute("data-id");
                if (pId) openPrinterModal(pId);
            }
        });
    }

    // 3. Spools Warehouse delegation
    const sList = document.getElementById("spools-list");
    if (sList && !sList._delegated) {
        sList._delegated = true;
        sList.addEventListener("click", async (e) => {
            const histBtn = e.target.closest(".btn-history-spool");
            if (histBtn) {
                const id = histBtn.getAttribute("data-id");
                if (id) openSpoolMovementsFor(id);
                return;
            }
            const assignBtn = e.target.closest(".btn-assign-spool");
            if (assignBtn) {
                const id = assignBtn.getAttribute("data-id");
                state.selectedSpoolForAssign = state.spools[id];
                openAssignSpoolModal(state.printers || []);
                return;
            }
            const editBtn = e.target.closest(".btn-edit-spool");
            if (editBtn) {
                const id = editBtn.getAttribute("data-id");
                const s = state.spools[id];
                if (s) openAddSpoolModal(s);
                return;
            }
            const delBtn = e.target.closest(".btn-delete-spool");
            if (delBtn) {
                const id = delBtn.getAttribute("data-id");
                if (confirm("Видалити цю котушку зі складу?")) {
                    await fetch(`/api/spools/${id}`, { method: "DELETE" });
                    loadMaterials();
                }
                return;
            }
        });
    }

    // 4. History Table delegation
    const hTbody = document.getElementById("history-table-body");
    if (hTbody && !hTbody._delegated) {
        hTbody._delegated = true;
        hTbody.addEventListener("click", async (e) => {
            const reprintBtn = e.target.closest(".btn-reprint-history");
            if (reprintBtn) {
                reprintJob(reprintBtn);
                return;
            }
            const delBtn = e.target.closest(".btn-delete-history-entry");
            if (delBtn) {
                const ts = delBtn.getAttribute("data-ts");
                if (ts) deleteHistoryItem(ts);
                return;
            }
            const scrapBtn = e.target.closest(".btn-mark-scrap");
            if (scrapBtn) {
                const data = {
                    ts: scrapBtn.getAttribute("data-ts"),
                    weight: parseFloat(scrapBtn.getAttribute("data-weight")) || 0,
                    task: scrapBtn.getAttribute("data-task") || "Модель",
                    printer: scrapBtn.getAttribute("data-printer") || "Принтер",
                    printerId: scrapBtn.getAttribute("data-printer-id") || "",
                    slotKey: scrapBtn.getAttribute("data-slot") || "",
                    spoolId: scrapBtn.getAttribute("data-spool-id") || "",
                    date: scrapBtn.getAttribute("data-date") || "-",
                };
                openScrapModal(data);
                return;
            }
        });
    }

    // 5. Parts List delegation
    const pList = document.getElementById("parts-list");
    if (pList && !pList._delegated) {
        pList._delegated = true;
        pList.addEventListener("click", async (e) => {
            const decBtn = e.target.closest(".btn-part-qty-dec");
            if (decBtn) {
                e.preventDefault();
                e.stopPropagation();
                const id = decBtn.getAttribute("data-id");
                if (id) adjustPartQuantity(id, -1);
                return;
            }
            const incBtn = e.target.closest(".btn-part-qty-inc");
            if (incBtn) {
                e.preventDefault();
                e.stopPropagation();
                const id = incBtn.getAttribute("data-id");
                if (id) adjustPartQuantity(id, 1);
                return;
            }
            const printBtn = e.target.closest(".btn-print-part");
            if (printBtn) {
                e.preventDefault();
                e.stopPropagation();
                const id = printBtn.getAttribute("data-id");
                if (id) triggerPrintPartById(id);
                return;
            }
            const editBtn = e.target.closest(".btn-edit-part");
            if (editBtn) {
                e.preventDefault();
                e.stopPropagation();
                const id = editBtn.getAttribute("data-id");
                if (id && state.parts[id]) openAddPartModal(state.parts[id]);
                return;
            }
            const delBtn = e.target.closest(".btn-delete-part");
            if (delBtn) {
                e.preventDefault();
                e.stopPropagation();
                const id = delBtn.getAttribute("data-id");
                if (id) deletePart(id);
                return;
            }
            const infoEl = e.target.closest(".part-card-main-info, .part-card-file-row");
            if (infoEl) {
                e.preventDefault();
                e.stopPropagation();
                const id = infoEl.getAttribute("data-id");
                if (id) showPartDetails(id);
                return;
            }
        });
    }

    // 6. Commercial Presets delegation
    const cpList = document.getElementById("commercial-presets-list");
    if (cpList && !cpList._delegated) {
        cpList._delegated = true;
        cpList.addEventListener("click", async (e) => {
            const editBtn = e.target.closest(".btn-edit-preset");
            if (editBtn) {
                e.stopPropagation();
                const pId = editBtn.getAttribute("data-id");
                const p = state.presets[pId];
                if (!p) return;

                state.editingPresetId = pId;
                const titleEl = document.getElementById("preset-modal-title");
                if (titleEl) titleEl.textContent = "✏️ Редагувати пресет";

                const n = document.getElementById("preset-name");
                const pg = document.getElementById("preset-price-g");
                const el = document.getElementById("preset-elec-rate");
                const pw = document.getElementById("preset-power");
                const dep = document.getElementById("preset-depreciation");
                const con = document.getElementById("preset-consumables");
                const prf = document.getElementById("preset-profit");

                if (n) n.value = p.name || "";
                if (pg) pg.value = p.price_per_g !== undefined ? p.price_per_g : 0.85;
                if (el) el.value = p.electricity_rate_uah !== undefined ? p.electricity_rate_uah : 4.32;
                if (pw) pw.value = p.power_watts !== undefined ? p.power_watts : 120;
                if (dep) dep.value = p.depreciation_val || "10";
                if (con) con.value = p.consumables_val || "5";
                if (prf) prf.value = p.profit_val || "100%";

                triggerHaptic("light");
                const presetModal = document.getElementById("preset-modal");
                if (presetModal) presetModal.classList.add("active");
                return;
            }
            const delBtn = e.target.closest(".btn-delete-preset");
            if (delBtn) {
                e.stopPropagation();
                const pId = delBtn.getAttribute("data-id");
                if (confirm("Видалити цей пресет?")) {
                    await fetch(`/api/commercial/presets/${pId}`, { method: "DELETE" });
                    loadCommercialPresets();
                }
                return;
            }
        });
    }
}

/**
 * Initialize modal system, global key listeners and BackButton observer
 */
export function initModalsModule() {
    const tg = window.Telegram?.WebApp;
    if (tg) {
        tg.ready();
        tg.expand();
        tg.enableClosingConfirmation();

        if (tg.BackButton) {
            tg.BackButton.onClick(() => {
                closeTopmostModal();
            });
        }
    }

    // Observe modal DOM changes to keep BackButton in sync
    const modalObserver = new MutationObserver(() => {
        updateBackButton();
    });
    modalObserver.observe(document.body, { attributes: true, subtree: true, attributeFilter: ['class', 'style'] });

    // Global Escape key handler
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            closeTopmostModal();
        }
    });

    initGestures();
    initEventDelegation();
}
