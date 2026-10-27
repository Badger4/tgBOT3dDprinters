/**
 * 3D Farm Manager - Fleet & Printers Module
 */

import { escapeHtml, formatRemainingTime, getPrinterStatusInfo, cleanSubtaskName, evaluateMathExpression, triggerHaptic } from "./utils.js";
import { renderCockpitPrinterCard, renderClassicPrinterCard } from "./cockpit.js";
import { state } from "./state.js";
import { api, getWebSessionToken } from "./api.js";
import { openPrinterSettingsModal } from "./settings.js";

const ENABLE_COCKPIT_CARDS = true;

/**
 * Fetch printers and optionally spools from the backend
 */
export async function fetchPrinters() {
    try {
        const needSpools = !state.spools || Object.keys(state.spools).length === 0;
        const [pData, sData] = await Promise.all([
            api.getPrinters().catch(err => {
                if (err.status === 401 || err.status === 403) {
                    renderAccessDenied();
                }
                throw err;
            }),
            needSpools ? api.getSpools().catch(() => null) : Promise.resolve(null)
        ]);

        if (Array.isArray(pData)) {
            state.printers = pData;
        }
        if (sData && typeof sData === "object") {
            state.spools = sData;
        }

        renderPrinters(state.printers);

        if (state.selectedPrinterId && document.getElementById("printer-modal")?.classList.contains("active")) {
            const currentP = state.printers.find(p => p.id === state.selectedPrinterId);
            if (currentP) updatePrinterModalContent(currentP);
        }
    } catch (err) {
        console.error("Error fetching printers:", err);
    }
}

/**
 * Render access denied screen if user is unauthorized
 */
export function renderAccessDenied() {
    if (state.pollInterval) clearInterval(state.pollInterval);
    document.body.innerHTML = `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;background:#0f172a;color:#ef4444;text-align:center;padding:24px;font-family:sans-serif;">
            <div style="font-size:54px;margin-bottom:16px;">⛔</div>
            <h2 style="font-size:24px;font-weight:700;margin-bottom:12px;color:#f87171;">Доступ заблоковано</h2>
            <p style="color:#94a3b8;max-width:360px;line-height:1.5;font-size:15px;">
                Ваш акаунт не має прав доступу до цієї 3D Ферми або ваш доступ було скасовано адміністратором.
            </p>
        </div>`;
}

/**
 * Update filter count badges
 */
export function updateFilterBadges(printers) {
    if (!printers) return;
    const total = printers.length;
    let running = 0;
    let pause = 0;
    let online = 0;
    let offline = 0;

    printers.forEach(p => {
        const info = getPrinterStatusInfo(p.state);
        if (info.code === "RUNNING") running++;
        else if (info.code === "PAUSE") pause++;
        else if (info.code === "OFFLINE") offline++;
        else online++;
    });

    const cAll = document.getElementById("count-filter-all");
    const cRun = document.getElementById("count-filter-running");
    const cPause = document.getElementById("count-filter-pause");
    const cIdle = document.getElementById("count-filter-idle");
    const cOffline = document.getElementById("count-filter-offline");

    if (cAll) cAll.textContent = total;
    if (cRun) cRun.textContent = running;
    if (cPause) cPause.textContent = pause;
    if (cIdle) cIdle.textContent = online;
    if (cOffline) cOffline.textContent = offline;
}

/**
 * Filter printer cards in the DOM based on query and active status tab
 */
export function applyPrinterFilters() {
    const searchInput = document.getElementById("printer-search-input");
    const rawQuery = (searchInput?.value || "").trim().toLowerCase();
    const activeBtn = document.querySelector("#tab-printers .filter-pills .pill-btn.active");
    const filterState = activeBtn?.dataset.filter || "all";

    document.querySelectorAll(".printer-card, #dashboard-grid .glass-card").forEach(card => {
        const name = (card.getAttribute("data-name") || "").toLowerCase();
        const searchBlob = (card.getAttribute("data-search") || name).toLowerCase();
        const stateCode = (card.getAttribute("data-state") || "ONLINE").toUpperCase();
        const statusInfo = getPrinterStatusInfo(stateCode);

        const matchesQuery = !rawQuery || name.includes(rawQuery) || searchBlob.includes(rawQuery);
        let matchesFilter = true;
        if (filterState === "RUNNING") {
            matchesFilter = statusInfo.code === "RUNNING";
        } else if (filterState === "PAUSE") {
            matchesFilter = statusInfo.code === "PAUSE";
        } else if (filterState === "IDLE" || filterState === "ONLINE") {
            matchesFilter = statusInfo.code === "ONLINE";
        } else if (filterState === "OFFLINE") {
            matchesFilter = statusInfo.code === "OFFLINE";
        }

        card.style.display = (matchesQuery && matchesFilter) ? "" : "none";
    });
}

/**
 * Populate printer select dropdown in settings modal
 */
export function populatePrinterSettingsSelect(printers) {
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

/**
 * Render the main printers list into the DOM
 */
export function renderPrinters(printers = state.printers) {
    updateFilterBadges(printers);
    populatePrinterSettingsSelect(printers);

    const printersGrid = document.getElementById("printers-grid");
    const dashboardGrid = document.getElementById("dashboard-grid");
    const activeCountEl = document.getElementById("active-printers-count") || document.getElementById("active-count");

    if (!printers || printers.length === 0) {
        const emptyHtml = `
            <div class="glass-card text-center p-4" style="grid-column: 1 / -1;">
                <i class="fa-solid fa-triangle-exclamation color-orange fa-2x mb-2"></i>
                <p>Не знайдено жодного підключеного принтера Bambu Lab.</p>
            </div>`;
        if (printersGrid) printersGrid.innerHTML = emptyHtml;
        if (dashboardGrid) dashboardGrid.innerHTML = emptyHtml;
        if (activeCountEl) activeCountEl.textContent = "0/0";
        return;
    }

    const isBusy = (code) => code === "RUNNING" || code === "PREPARE";
    const runningCount = printers.filter(p => isBusy(getPrinterStatusInfo(p.state).code)).length;
    const pauseCount = printers.filter(p => getPrinterStatusInfo(p.state).code === "PAUSE").length;
    const activeTotal = runningCount + pauseCount;

    let subDetail = [];
    if (runningCount > 0) subDetail.push(`друк: ${runningCount}`);
    if (pauseCount > 0) subDetail.push(`пауза: ${pauseCount}`);
    const subStr = subDetail.length > 0 ? ` (${subDetail.join(', ')})` : '';

    if (activeCountEl) {
        activeCountEl.textContent = `${activeTotal}/${printers.length}${subStr}`;
    }

    if (printersGrid) {
        // Collect existing peek boxes with an active image to avoid snapshot reload/flicker
        const activePeekImgs = new Map();
        printers.forEach(p => {
            const peekBox = document.getElementById(`cockpit-peek-${p.id}`);
            const img = peekBox?.querySelector("img");
            if (img && img.src && img.style.display !== "none") {
                activePeekImgs.set(String(p.id), img);
            }
        });

        printersGrid.innerHTML = printers.map(p => {
            const rawSt = String(p.state || "IDLE").toUpperCase();
            const statusInfo = getPrinterStatusInfo(rawSt);
            const isPrinting = statusInfo.code === "RUNNING";
            let progress = p.progress_pct !== undefined ? p.progress_pct : 0;

            const modelName = cleanSubtaskName(p.subtask_name, isPrinting);
            let timeStr = formatRemainingTime(p.remaining_mins);
            if (statusInfo.code === "PAUSE") timeStr = "Пауза";
            else if (statusInfo.code === "IDLE") timeStr = "Вільний";
            else if (!timeStr && isPrinting) timeStr = "Підготовка...";

            const layerStr = (statusInfo.code === "IDLE" && p.current_layer === 0) ? "—" : `${p.current_layer}/${p.total_layers}`;

            const spoolsList = Object.values(state.spools || {});
            const assignedSpools = spoolsList.filter(s => s.assigned_printer_id === p.id);
            const activeKey = String(p.active_slot_key || "254");
            const slotLabels = { "0": "A1", "1": "A2", "2": "A3", "3": "A4", "254": "VT", "255": "VT" };
            const hasAms = Boolean(p.has_ams);

            let displaySlotKey = activeKey;
            let assignedSpool = assignedSpools.find(s => String(s.assigned_slot_key) === activeKey || (activeKey in ["254", "255"] && String(s.assigned_slot_key) in ["254", "255"]));

            if (!assignedSpool && assignedSpools.length > 0) {
                assignedSpool = assignedSpools[0];
                displaySlotKey = String(assignedSpool.assigned_slot_key !== undefined ? assignedSpool.assigned_slot_key : "254");
            } else if (!assignedSpool && hasAms && (activeKey === "254" || activeKey === "255")) {
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
                : (assignedSpool ? assignedSpool.remaining_grams : (p.filament_grams_left !== undefined ? p.filament_grams_left : 0));

            const slotTag = (hasAms && slotLabels[displaySlotKey]) ? `[${slotLabels[displaySlotKey]}] ` : "";

            const hasAmsTray = Boolean(p.ams_trays_info && p.ams_trays_info[displaySlotKey] && p.ams_trays_info[displaySlotKey].type && !p.ams_trays_info[displaySlotKey].empty);
            const hasAssigned = Boolean(assignedSpool && (assignedSpool.remaining_grams > 0 || assignedSpool.name));
            const hasPhysicalSpool = hasAssigned || hasAmsTray || (p.filament_type && p.filament_type !== "Невизначено" && slotGrams > 0);

            let filamentDisplay = "";
            if (assignedSpool) {
                filamentDisplay = `${slotTag}${escapeHtml(assignedSpool.name)} (${slotGrams}g)`;
            } else if (hasAmsTray) {
                const tInfo = p.ams_trays_info[displaySlotKey];
                const name = tInfo.sub_brands ? `Bambu ${tInfo.type} ${tInfo.sub_brands}` : `Bambu ${tInfo.type}`;
                filamentDisplay = `${slotTag}${escapeHtml(name)} (${slotGrams}g)`;
            } else if (p.filament_type && p.filament_type !== "Невизначено" && slotGrams > 0) {
                filamentDisplay = `${slotTag}${escapeHtml(p.filament_type)} (${slotGrams}g)`;
            } else {
                filamentDisplay = `${slotTag}Порожньо`;
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
                hasPhysicalSpool ? `${slotGrams}g` : "",
                `${progress}%`,
                timeStr
            ].filter(Boolean).join(" ").toLowerCase();

            if (ENABLE_COCKPIT_CARDS) {
                return renderCockpitPrinterCard(p, statusInfo, modelName, isPrinting, progress, timeStr, layerStr, filamentDisplay, hasPhysicalSpool, slotGrams, printerModelVal, serialVal, fullSearchText, assignedSpools);
            } else {
                return renderClassicPrinterCard(p, statusInfo, modelName, isPrinting, progress, timeStr, layerStr, filamentDisplay, hasPhysicalSpool, slotGrams, printerModelVal, serialVal, fullSearchText);
            }
        }).join("");

        // Restore active peek images so the existing decoded image is retained without reload/flicker
        activePeekImgs.forEach((oldImg, pId) => {
            const newBox = document.getElementById(`cockpit-peek-${pId}`);
            if (newBox) {
                const currentImg = newBox.querySelector("img");
                if (currentImg) {
                    currentImg.replaceWith(oldImg);
                }
            }
        });
    }

    // Render Compact Dashboard Grid only when active to avoid wasting CPU/DOM cycles
    if (dashboardGrid) {
        const isCompactActive = dashboardGrid.style.display !== "none" &&
            localStorage.getItem("farm_view_mode") === "compact";

        if (isCompactActive) {
            window._lastCompactSnapshotTime = window._lastCompactSnapshotTime || {};
            // Collect existing compact thumbnail images to avoid flickering
            const activeThumbs = new Map();
            printers.forEach(p => {
                const card = dashboardGrid.querySelector(`.glass-card[data-id="${p.id}"]`);
                const img = card?.querySelector("img");
                if (img && img.src && img.style.display !== "none") {
                    activeThumbs.set(String(p.id), img);
                }
            });

            dashboardGrid.innerHTML = printers.map(p => {
                const rawSt = String(p.state || "IDLE").toUpperCase();
                const statusInfo = getPrinterStatusInfo(rawSt);
                const isPrinting = statusInfo.code === "RUNNING";
                const isOnline = p.is_online !== false && statusInfo.code !== "OFFLINE";
                const progress = p.progress_pct !== undefined ? p.progress_pct : 0;
                
                let timeStr = formatRemainingTime(p.remaining_mins);
                if (statusInfo.code === "PAUSE") timeStr = "Очікування";
                else if (statusInfo.code === "IDLE") timeStr = "Готовий";
                else if (!timeStr && isPrinting) timeStr = "Оцінка...";

                const initData = window.Telegram?.WebApp?.initData || "";
                const initDataParam = initData ? `?initData=${encodeURIComponent(initData)}` : '';
                
                // Refresh snapshot every 15 seconds if online and not in failed cooldown
                const failedAt = window._failedSnapshots?.[p.id] || 0;
                const isFailedCooldown = (Date.now() - failedAt) < 45000;
                const lastFetched = window._lastCompactSnapshotTime[p.id] || 0;
                const needsRefresh = (Date.now() - lastFetched) > 15000;
                const canLoadSnapshot = isOnline && !isFailedCooldown;
                const timeParam = needsRefresh ? `${initDataParam ? '&' : '?'}t=${Date.now()}` : '';
                const thumbSrc = canLoadSnapshot ? `/api/printers/${p.id}/snapshot${initDataParam}${timeParam}` : '';
                
                return `
                    <div class="glass-card" data-id="${p.id}" data-name="${escapeHtml(p.name)}" data-state="${statusInfo.code}" style="padding: 10px; cursor: pointer; display: flex; flex-direction: column; position: relative;">
                        <div style="font-size: 13px; font-weight: 600; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 8px;">
                            ${escapeHtml(p.name)}
                        </div>
                        <div style="width: 100%; aspect-ratio: 4/3; background: #000; border-radius: var(--radius-sm); overflow: hidden; position: relative; margin-bottom: 8px;">
                            ${thumbSrc ? `<img src="${thumbSrc}" loading="lazy" style="width: 100%; height: 100%; object-fit: cover;" onload="if(window._failedSnapshots) delete window._failedSnapshots['${p.id}']; window._lastCompactSnapshotTime['${p.id}'] = Date.now();" onerror="this.style.display='none'; window._failedSnapshots = window._failedSnapshots || {}; window._failedSnapshots['${p.id}'] = Date.now(); if(this.nextElementSibling) this.nextElementSibling.style.display='flex';" />` : ''}
                            <div style="${thumbSrc ? 'display: none;' : 'display: flex;'} position: absolute; inset: 0; align-items: center; justify-content: center; color: var(--text-dim); background: rgba(0,0,0,0.5);">
                                <i class="fa-solid ${!isOnline ? 'fa-power-off' : 'fa-camera-slash'}"></i>
                            </div>
                            <div class="status-pill ${statusInfo.badgeClass}" style="position: absolute; top: 4px; right: 4px; font-size: 9px; padding: 2px 6px;">
                                ${statusInfo.label}
                            </div>
                        </div>
                        <div class="progress-bar-wrap sm w-100">
                            <div class="progress-bar ${statusInfo.code === 'PAUSE' ? 'amber' : ''}" style="width: ${progress}%"></div>
                        </div>
                        <div style="font-size: 10px; color: var(--text-muted); display: flex; justify-content: space-between; margin-top: 6px;">
                            <span style="font-weight:600;">${progress.toFixed(1)}%</span>
                            <span>${timeStr}</span>
                        </div>
                        <div style="font-size: 10px; color: var(--text-muted); display: flex; justify-content: space-between; margin-top: 4px;">
                            <span><i class="fa-solid fa-temperature-high color-red"></i> ${p.nozzle_temp || 0}°C</span>
                            <span><i class="fa-solid fa-hot-tub-person color-orange"></i> ${p.bed_temp || 0}°C</span>
                        </div>
                    </div>
                `;
            }).join("");

            // Restore active thumbnails to eliminate flicker unless refresh is due
            activeThumbs.forEach((oldImg, pId) => {
                const lastFetched = window._lastCompactSnapshotTime[pId] || 0;
                const isRecent = (Date.now() - lastFetched) < 15000;
                if (isRecent) {
                    const card = dashboardGrid.querySelector(`.glass-card[data-id="${pId}"]`);
                    const newImg = card?.querySelector("img");
                    if (newImg) {
                        newImg.replaceWith(oldImg);
                    }
                }
            });
        }
    }

    applyPrinterFilters();
}

/**
 * Open printer details modal
 */
export async function openPrinterModal(pId) {
    triggerHaptic("medium");
    state.selectedPrinterId = pId;
    const p = state.printers.find(x => x.id === pId);
    if (!p) return;

    try {
        const sRes = await api.getSpools();
        if (sRes) state.spools = sRes;
    } catch (e) {
        console.error("Error fetching spools for modal:", e);
    }

    updatePrinterModalContent(p);
    loadCameraSnapshot(pId);
    
    const printerModal = document.getElementById("printer-modal");
    if (printerModal) printerModal.classList.add("active");
}

/**
 * Close printer details modal and cleanly drop camera stream
 */
export function closePrinterModal() {
    triggerHaptic("light");
    const printerModal = document.getElementById("printer-modal");
    if (printerModal) printerModal.classList.remove("active");

    const cameraImg = document.getElementById("camera-snapshot-img");
    if (cameraImg) cameraImg.src = "";

    const fullscreenCamModal = document.getElementById("camera-fullscreen-modal");
    if (fullscreenCamModal) {
        fullscreenCamModal.classList.remove("active");
        const fsImg = document.getElementById("fullscreen-camera-img");
        if (fsImg) fsImg.src = "";
    }

    state.selectedPrinterId = null;
}

/**
 * Update the dynamic content inside #printer-modal
 */
export function updatePrinterModalContent(p) {
    const statusInfo = getPrinterStatusInfo(p.state);
    const st = statusInfo.code;
    const isPrinting = (st === "RUNNING");
    let progress = p.progress_pct !== undefined ? p.progress_pct : 0;
    if (st === "OFFLINE" || st === "ONLINE") progress = 0;

    let timeStr = formatRemainingTime(p.remaining_mins);
    if (st === "OFFLINE") timeStr = "Офлайн";
    else if (st === "ONLINE") timeStr = "Онлайн";
    else if (!timeStr && isPrinting) timeStr = "Підготовка...";

    const layerStr = (st === "ONLINE" || st === "OFFLINE") ? "—" : `${p.current_layer} / ${p.total_layers}`;

    const modalNameEl = document.getElementById("modal-printer-name");
    const modalStatusEl = document.getElementById("modal-printer-status");
    const modalNozzleTemp = document.getElementById("modal-nozzle-temp");
    const modalBedTemp = document.getElementById("modal-bed-temp");
    const modalLayer = document.getElementById("modal-layer");
    const modalTime = document.getElementById("modal-time");

    if (modalNameEl) modalNameEl.textContent = p.name;
    if (modalStatusEl) {
        modalStatusEl.textContent = statusInfo.label;
        modalStatusEl.className = `status-pill ${statusInfo.badgeClass}`;
    }

    if (modalNozzleTemp) modalNozzleTemp.textContent = `${p.nozzle_temp || 0}°C (${p.nozzle_diameter || '0.4'} мм)`;
    if (modalBedTemp) modalBedTemp.textContent = `${p.bed_temp || 0}°C`;
    if (modalLayer) modalLayer.textContent = layerStr;
    if (modalTime) modalTime.textContent = timeStr || "0 хв";

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

    const speedSection = document.querySelector(".speed-selector")?.closest(".control-section");
    if (speedSection) {
        speedSection.style.display = isActivelyPrintingOrPaused ? "block" : "none";
    }

    document.querySelectorAll(".speed-selector .speed-btn").forEach(btn => {
        const lvl = parseInt(btn.getAttribute("data-level"), 10);
        btn.classList.toggle("active", lvl === p.spd_lvl);
    });

    const btnPause = document.getElementById("btn-action-pause");
    const btnResume = document.getElementById("btn-action-resume");
    const btnStop = document.getElementById("btn-action-stop");

    if (btnPause && btnResume && btnStop) {
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
    }

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

    const hasAms = Boolean(p.has_ams);
    const amsBadge = document.getElementById("modal-ams-badge");
    if (amsBadge) {
        amsBadge.innerHTML = `
            <button type="button" class="btn btn-xs ${hasAms ? 'btn-outline-primary' : 'btn-outline-neutral'}" id="modal-ams-toggle-btn" style="font-size:11px; padding:3px 8px; border-radius:6px; cursor:pointer;" title="Натисніть для перемикання режиму AMS">
                <i class="fa-solid ${hasAms ? 'fa-layer-group color-blue' : 'fa-spool color-muted'}"></i>
                <span>${hasAms ? 'Модуль AMS' : 'Пряма подача (VT)'}</span>
            </button>
        `;
        const toggleBtn = document.getElementById("modal-ams-toggle-btn");
        if (toggleBtn) {
            toggleBtn.onclick = async (e) => {
                e.preventDefault();
                e.stopPropagation();
                const newEnabled = !hasAms;
                await sendPrinterAction({ action: "set_ams_enabled", enabled: newEnabled });
            };
        }
    }

    const amsSlotsContainer = document.getElementById("modal-ams-slots-container");
    if (amsSlotsContainer) {
        const activeKey = String(p.active_slot_key || "254");
        const slots = p.ams_slots || {};
        const slotKeys = hasAms ? ["0", "1", "2", "3", "254"] : ["254"];
        const slotLabels = { "0": "A1", "1": "A2", "2": "A3", "3": "A4", "254": hasAms ? "VT (Зовнішній)" : "Зовнішній котушкотримач", "255": hasAms ? "VT (Зовнішній)" : "Зовнішній котушкотримач" };
        const spoolsList = Object.values(state.spools || {});

        amsSlotsContainer.innerHTML = slotKeys.map(k => {
            const rawGrams = slots[k] !== undefined ? slots[k] : (slots["255"] !== undefined && k === "254" ? slots["255"] : 0);
            const isActive = (k === activeKey || (k === "254" && activeKey === "255") || (k === "255" && activeKey === "254"));
            const assignedSpool = spoolsList.find(s => s.assigned_printer_id === p.id && (String(s.assigned_slot_key) === k || (k === "254" && String(s.assigned_slot_key) === "255")));
            const trayInfo = (p.ams_trays_info || {})[k] || (k === "254" ? (p.ams_trays_info || {})["255"] : {}) || {};
            
            const hasAmsTray = Boolean(!trayInfo.empty && trayInfo.type);
            const hasAssigned = Boolean(assignedSpool && (assignedSpool.remaining_grams > 0 || assignedSpool.name));
            const hasPhysicalSpool = hasAssigned || hasAmsTray || (isActive && p.filament_type && p.filament_type !== "Невизначено" && rawGrams > 0);

            if (!hasPhysicalSpool) {
                return `
                    <div class="ams-slot-card empty-slot ${isActive ? 'active-slot' : ''}">
                        <div class="slot-tag d-flex justify-content-between align-items-center mb-1">
                            <span><b>${slotLabels[k]}</b> ${isActive ? '⚡' : ''}</span>
                            <div class="d-flex gap-1">
                                <button class="btn btn-xs btn-outline-primary btn-assign-slot-spool" data-printer="${p.id}" data-slot="${k}" title="Встановити котушку зі Складу">
                                    <i class="fa-solid fa-plus"></i>
                                </button>
                            </div>
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
            let pct = 0;
            let displayGrams = rawGrams;

            if (assignedSpool) {
                spoolColor = assignedSpool.color || '#3b82f6';
                spoolName = escapeHtml(assignedSpool.name);
                spoolType = escapeHtml(assignedSpool.type);
                displayGrams = assignedSpool.remaining_grams !== undefined ? assignedSpool.remaining_grams : rawGrams;
                const maxCap = assignedSpool.initial_grams || assignedSpool.total_grams || 1000;
                pct = Math.min(100, Math.max(0, Math.round((displayGrams / maxCap) * 100)));
            } else if (hasAmsTray) {
                spoolColor = trayInfo.color || (isActive ? '#22c55e' : '#3b82f6');
                spoolType = escapeHtml(trayInfo.type);
                spoolName = trayInfo.sub_brands ? `Bambu ${spoolType} ${escapeHtml(trayInfo.sub_brands)}` : `Bambu ${spoolType}`;
                displayGrams = rawGrams;
                if (trayInfo.remain !== undefined && trayInfo.remain >= 0) {
                    pct = trayInfo.remain;
                } else {
                    pct = Math.min(100, Math.max(0, Math.round((displayGrams / 1000) * 100)));
                }
            } else if (isActive && p.filament_type && p.filament_type !== "Невизначено") {
                spoolColor = '#22c55e';
                spoolName = 'Активна нитка';
                spoolType = escapeHtml(p.filament_type);
                displayGrams = rawGrams;
                pct = Math.min(100, Math.max(0, Math.round((displayGrams / 1000) * 100)));
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
                let spoolsMap = state.spools;
                if (!spoolsMap || Object.keys(spoolsMap).length === 0) {
                    try {
                        spoolsMap = await api.getSpools();
                        state.spools = spoolsMap;
                    } catch (e) {}
                }
                const availableSpools = Object.values(spoolsMap || {}).filter(s => !s.assigned_printer_id);
                if (availableSpools.length === 0) {
                    alert("На Складі немає вільних котушок. Додайте котушку у вкладці 'Філамент'.");
                    return;
                }
                const optionsText = availableSpools.map((s, idx) => `${idx + 1}. ${s.name} (${s.type || 'PLA'}, ${s.remaining_grams || 1000}g)`).join("\n");
                const choice = prompt(`Виберіть котушку зі Складу для слоту ${slotLabels[sId]}:\n\n${optionsText}\n\nВведіть номер (1-${availableSpools.length}):`);
                if (choice) {
                    const idx = parseInt(choice.trim(), 10) - 1;
                    if (!isNaN(idx) && availableSpools[idx]) {
                        const targetSpool = availableSpools[idx];
                        const loadHw = confirm("Запустити фізичне завантаження (Load Filament) на принтері?");
                        await sendPrinterAction({ action: "assign_spool", spool_id: targetSpool.id, slot_id: sId, load_hardware: loadHw });
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
                        const parsed = evaluateMathExpression(val.trim());
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
                if (confirm("Зняти котушку зі слоту в базі даних?")) {
                    const unloadHw = confirm("Запустити фізичне вивантаження (Unload Filament) на принтері?");
                    sendPrinterAction({ action: "unassign_spool", slot_id: sId, unload_hardware: unloadHw });
                }
            });
        });
    }

    // Maintenance section
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

    // Skip objects & Plate map
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
                let val = parseInt(s, 10);
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

                    const pModel = String(p.printer_model || p.name || "").toLowerCase();
                    const bedW = pModel.includes("mini") ? 180 : 256;
                    const bedH = pModel.includes("mini") ? 180 : 256;
                    const scale = 3.0;
                    const margin = 45;
                    const imgW = bedW * scale + margin * 2;
                    const imgH = bedH * scale + margin * 2;
                    const by2 = margin + bedH * scale;

                    const nObjs = objects.length;
                    const cols = nObjs >= 4 ? 3 : (nObjs >= 2 ? 2 : 1);
                    const rows = Math.ceil(nObjs / cols);

                    const hotspotsHtml = objects.map((obj, idx) => {
                        const objId = obj.id;
                        const isSkipped = skipped.includes(parseInt(objId, 10)) || skipped.includes(String(objId));
                        const cleanObjName = sanitizeObjName(obj.name || `Об'єкт #${objId}`);

                        let bbox = obj.bbox;
                        if (!bbox || !Array.isArray(bbox) || bbox.length < 4) {
                            const r = Math.floor(idx / cols);
                            const c = idx % cols;
                            const cellW = bedW / cols;
                            const cellH = bedH / rows;
                            const xmin = c * cellW + cellW * 0.15;
                            const xmax = (c + 1) * cellW - cellW * 0.15;
                            const ymin = r * cellH + cellH * 0.15;
                            const ymax = (r + 1) * cellH - cellH * 0.15;
                            bbox = [xmin, ymin, xmax, ymax];
                        }

                        let xmin = parseFloat(bbox[0]) || 10;
                        let ymin = parseFloat(bbox[1]) || 10;
                        let xmax = parseFloat(bbox[2]) || 50;
                        let ymax = parseFloat(bbox[3]) || 50;

                        let px1 = margin + xmin * scale;
                        let px2 = margin + xmax * scale;
                        let py1 = by2 - ymax * scale;
                        let py2 = by2 - ymin * scale;

                        if (px2 - px1 < 30) px2 = px1 + 30;
                        if (py2 - py1 < 30) py1 = py2 - 30;

                        const leftPct = ((px1 / imgW) * 100).toFixed(2);
                        const topPct = ((py1 / imgH) * 100).toFixed(2);
                        const widthPct = (((px2 - px1) / imgW) * 100).toFixed(2);
                        const heightPct = (((py2 - py1) / imgH) * 100).toFixed(2);

                        return `
                            <div class="plate-obj-hotspot ${isSkipped ? 'is-skipped' : 'is-active'}"
                                 data-id="${objId}"
                                 data-name="${escapeHtml(cleanObjName)}"
                                 style="left: ${leftPct}%; top: ${topPct}%; width: ${widthPct}%; height: ${heightPct}%;"
                                 title="${isSkipped ? `Об'єкт #${objId} (Пропущено)` : `Натисніть, щоб пропустити #${objId} (${escapeHtml(cleanObjName)})`}">
                                <span class="plate-obj-badge">${isSkipped ? '❌' : `#${objId}`}</span>
                            </div>`;
                    }).join("");

                    const initDataParam = window.Telegram?.WebApp?.initData ? ('&initData=' + encodeURIComponent(window.Telegram.WebApp.initData)) : '';
                    const token = getWebSessionToken();
                    const tokenParam = token ? ('&token=' + encodeURIComponent(token)) : '';
                    const mapHtml = `
                        <div class="text-center mb-2">
                            <div class="plate-map-container position-relative d-inline-block rounded overflow-hidden shadow-sm border border-secondary" style="max-width: 100%; background: #16161a;">
                                <img src="/api/printers/${p.id}/plate_map?format=jpg&v=${encodeURIComponent(stateKey)}${initDataParam}${tokenParam}" 
                                     class="img-fluid d-block" 
                                     style="max-height: 270px; width: auto; object-fit: contain;" 
                                     alt="Схема столу" />
                                <div class="plate-map-overlay position-absolute top-0 start-0 w-100 h-100">
                                    ${hotspotsHtml}
                                </div>
                            </div>
                            <div class="small text-muted mt-1 mb-2">
                                <i class="fa-solid fa-hand-pointer text-warning me-1"></i> Натисніть на об'єкт на схемі або кнопку нижче для пропуску
                            </div>
                        </div>`;
                    const btnsHtml = `<div class="d-flex flex-wrap gap-1 justify-content-center">` + objects.map(obj => {
                        const objId = obj.id;
                        const isSkipped = skipped.includes(parseInt(objId, 10)) || skipped.includes(String(objId));
                        const labelText = isSkipped ? `#${objId} (Пропущено)` : `#${objId}`;
                        return `
                            <button class="btn btn-sm py-1 px-2 ${isSkipped ? 'btn-secondary disabled' : 'btn-outline-danger'} btn-skip-obj-item font-monospace fw-bold" 
                                    data-id="${objId}" ${isSkipped ? 'disabled' : ''}>
                                ${isSkipped ? '<i class="fa-solid fa-xmark"></i> ' : '<i class="fa-solid fa-ban me-1"></i>'}
                                ${escapeHtml(labelText)}
                            </button>`;
                    }).join("") + `</div>`;
                    skipObjectsList.innerHTML = mapHtml + btnsHtml;

                    const handleSkipObj = async (objId, objName) => {
                        const displayName = objName ? `Об'єкт #${objId} (${objName})` : `Об'єкт #${objId}`;
                        if (confirm(`Пропустити ${displayName} на плейті без зупинки друку?`)) {
                            triggerHaptic("warning");
                            await sendPrinterAction({ action: "skip_objects", obj_ids: [objId] });
                        }
                    };

                    skipObjectsList.querySelectorAll(".plate-obj-hotspot.is-active").forEach(hotspot => {
                        hotspot.addEventListener("click", (e) => {
                            e.stopPropagation();
                            const objId = parseInt(hotspot.getAttribute("data-id"), 10);
                            const objName = hotspot.getAttribute("data-name") || "";
                            handleSkipObj(objId, objName);
                        });
                    });

                    skipObjectsList.querySelectorAll(".btn-skip-obj-item:not(.disabled)").forEach(b => {
                        b.addEventListener("click", () => {
                            const objId = parseInt(b.getAttribute("data-id"), 10);
                            handleSkipObj(objId, "");
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

/**
 * Load MJPEG stream or fallback snapshot for a printer
 */
export function loadCameraSnapshot(pId) {
    if (!pId) return;
    const initData = window.Telegram?.WebApp?.initData || "";
    const initDataParam = initData ? "?initData=" + encodeURIComponent(initData) : "";
    const streamUrl = `/api/printers/${pId}/stream${initDataParam}`;

    const cameraImg = document.getElementById("camera-snapshot-img");
    if (cameraImg) {
        cameraImg.style.display = "block";
        if (cameraImg.nextElementSibling) cameraImg.nextElementSibling.style.display = "none";
        if (!cameraImg.src.includes(`/api/printers/${pId}/stream`)) {
            cameraImg.src = streamUrl;
            cameraImg.onerror = () => {
                cameraImg.src = "";
                cameraImg.style.display = "none";
                if (cameraImg.nextElementSibling) cameraImg.nextElementSibling.style.display = "flex";
            };
        }
    }

    const fullscreenCamModal = document.getElementById("camera-fullscreen-modal");
    const fullscreenCamImg = document.getElementById("fullscreen-camera-img");
    if (fullscreenCamImg && fullscreenCamModal && fullscreenCamModal.classList.contains("active")) {
        fullscreenCamImg.style.display = "block";
        if (fullscreenCamImg.nextElementSibling) fullscreenCamImg.nextElementSibling.style.display = "none";
        if (!fullscreenCamImg.src.includes(`/api/printers/${pId}/stream`)) {
            fullscreenCamImg.src = streamUrl;
            fullscreenCamImg.onerror = () => {
                fullscreenCamImg.src = "";
                fullscreenCamImg.style.display = "none";
                if (fullscreenCamImg.nextElementSibling) fullscreenCamImg.nextElementSibling.style.display = "flex";
            };
        }
    }
}

/**
 * Open camera in full screen mode
 */
export function openFullscreenCamera() {
    if (!state.selectedPrinterId) return;
    triggerHaptic("medium");
    const currentP = state.printers.find(p => p.id === state.selectedPrinterId);
    const fullscreenCamTitle = document.getElementById("fullscreen-camera-title");
    const fullscreenCamModal = document.getElementById("camera-fullscreen-modal");

    if (fullscreenCamTitle && currentP) {
        fullscreenCamTitle.innerHTML = `<i class="fa-solid fa-video color-green"></i> ${escapeHtml(currentP.name)} (Жива камера)`;
    }
    if (fullscreenCamModal) {
        fullscreenCamModal.classList.add("active");
        if (fullscreenCamModal.requestFullscreen) {
            fullscreenCamModal.requestFullscreen().catch(() => {});
        }
    }
    loadCameraSnapshot(state.selectedPrinterId);
}

/**
 * Close full screen camera
 */
export function closeFullscreenCamera() {
    triggerHaptic("light");
    const fullscreenCamModal = document.getElementById("camera-fullscreen-modal");
    const fullscreenCamImg = document.getElementById("fullscreen-camera-img");
    if (fullscreenCamModal) {
        fullscreenCamModal.classList.remove("active");
        if (fullscreenCamImg) fullscreenCamImg.src = "";
    }
    if (document.fullscreenElement && document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
    }
}

/**
 * Send an action payload to the selected printer
 */
export async function sendPrinterAction(actionPayload) {
    if (!state.selectedPrinterId) return;
    triggerHaptic("medium");
    try {
        const res = await api.sendPrinterAction(state.selectedPrinterId, actionPayload);
        if (res.status === "ok") {
            if (["assign_spool", "unassign_spool", "set_slot_grams", "set_filament"].includes(actionPayload.action)) {
                try {
                    const spoolsMap = await api.getSpools();
                    state.spools = spoolsMap;
                } catch (e) {}
            }
            await fetchPrinters();
            if (state.selectedPrinterId && document.getElementById("printer-modal")?.classList.contains("active")) {
                const currentP = state.printers.find(p => p.id === state.selectedPrinterId);
                if (currentP) updatePrinterModalContent(currentP);
            }
        } else {
            alert("Помилка при виконанні дії: " + (res.error || "Невідомо"));
        }
    } catch (e) {
        console.error("Action error:", e);
    }
}

let currentFleetBatchAction = null;

export function updateFleetBatchSelectedCount() {
    const chks = document.querySelectorAll(".fleet-batch-printer-chk:not(:disabled)");
    const checked = document.querySelectorAll(".fleet-batch-printer-chk:not(:disabled):checked");
    const countEl = document.getElementById("fleet-batch-selected-count");
    const fleetBatchSelectAll = document.getElementById("fleet-batch-select-all");
    const fleetBatchRunSelectedBtn = document.getElementById("fleet-batch-run-selected-btn");

    if (countEl) countEl.textContent = `Обрано: ${checked.length} з ${chks.length}`;
    if (fleetBatchSelectAll) {
        fleetBatchSelectAll.checked = chks.length > 0 && checked.length === chks.length;
    }
    if (fleetBatchRunSelectedBtn) {
        fleetBatchRunSelectedBtn.disabled = checked.length === 0;
    }
}

/**
 * Open fleet batch modal for lights or calibration
 */
export function openFleetBatchModal(actionType) {
    currentFleetBatchAction = actionType;
    const fleetBatchModal = document.getElementById("fleet-batch-modal");
    if (!fleetBatchModal) return;

    const titleEl = document.getElementById("fleet-batch-modal-title");
    const runAllLabel = document.getElementById("fleet-batch-run-all-label");
    const runSelLabel = document.getElementById("fleet-batch-run-selected-label");
    const listEl = document.getElementById("fleet-batch-printers-list");

    if (actionType === "light_on") {
        if (titleEl) titleEl.innerHTML = `<i class="fa-regular fa-lightbulb color-amber"></i> Увімкнути світло`;
        if (runAllLabel) runAllLabel.textContent = "💡 Увімкнути усі";
        if (runSelLabel) runSelLabel.textContent = "Увімкнути для вибраних";
    } else if (actionType === "light_off") {
        if (titleEl) titleEl.innerHTML = `<i class="fa-solid fa-lightbulb color-blue"></i> Вимкнути світло`;
        if (runAllLabel) runAllLabel.textContent = "🌑 Вимкнути усі";
        if (runSelLabel) runSelLabel.textContent = "Вимкнути для вибраних";
    } else if (actionType === "calibrate") {
        if (titleEl) titleEl.innerHTML = `<i class="fa-solid fa-crosshairs color-green"></i> Автокалібрування`;
        if (runAllLabel) runAllLabel.textContent = "🎯 Калібрувати усі вільні";
        if (runSelLabel) runSelLabel.textContent = "Калібрувати вибрані";
    }

    if (listEl) {
        const printers = state.printers || [];
        if (printers.length === 0) {
            listEl.innerHTML = `<p class="text-muted text-center p-2">Немає підключених принтерів</p>`;
        } else {
            listEl.innerHTML = printers.map(p => {
                const stInfo = getPrinterStatusInfo(p.state);
                const isOffline = stInfo.code === "OFFLINE";
                const isBusy = stInfo.code === "RUNNING" || stInfo.code === "PAUSE";
                const disabled = isOffline || (actionType === "calibrate" && isBusy);
                const lightState = String(p.chamber_light_state || "off").toLowerCase() === "on";
                const extraBadge = actionType === "calibrate"
                    ? (isBusy ? `<span class="badge badge-warning" style="font-size:10px;">Друкує (пропуск)</span>` : stInfo.label)
                    : `<span class="badge badge-secondary" style="font-size:10px;">${lightState ? "💡 Увімк" : "🌑 Вимк"}</span>`;

                return `
                    <label class="spool-item glass-card p-2 mb-2 d-flex justify-content-between align-items-center" style="cursor: ${disabled ? 'not-allowed' : 'pointer'}; opacity: ${disabled ? '0.5' : '1'};">
                        <div class="d-flex align-items-center gap-2">
                            <input type="checkbox" class="fleet-batch-printer-chk" value="${escapeHtml(p.id)}" ${disabled ? "disabled" : "checked"} style="width: 18px; height: 18px; accent-color: #3b82f6;">
                            <span style="font-weight: 600; font-size: 13px;">${escapeHtml(p.name)}</span>
                        </div>
                        <div class="d-flex align-items-center gap-2">
                            <span style="font-size: 11px;">${extraBadge}</span>
                        </div>
                    </label>`;
            }).join("");

            listEl.querySelectorAll(".fleet-batch-printer-chk").forEach(chk => {
                chk.addEventListener("change", updateFleetBatchSelectedCount);
            });
        }
    }

    updateFleetBatchSelectedCount();
    fleetBatchModal.classList.add("active");
}

/**
 * Execute fleet batch action
 */
export async function executeFleetBatchAction(actionType, selectedIds) {
    triggerHaptic("medium");
    const fleetBatchModal = document.getElementById("fleet-batch-modal");
    if (fleetBatchModal) fleetBatchModal.classList.remove("active");

    try {
        if (actionType === "light_on" || actionType === "light_off") {
            const mode = actionType === "light_on" ? "on" : "off";
            const payload = { mode };
            if (Array.isArray(selectedIds)) payload.printer_ids = selectedIds;
            const res = await fetch("/api/fleet/lights", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.status === "ok") {
                await fetchPrinters();
                alert(`${mode === "on" ? "💡 Світло увімкнено" : "🌑 Світло вимкнено"} на ${data.updated_count} принтерах!`);
            } else {
                alert("Помилка: " + (data.error || "Невідомо"));
            }
        } else if (actionType === "calibrate") {
            const payload = {};
            if (Array.isArray(selectedIds)) payload.printer_ids = selectedIds;
            const res = await fetch("/api/fleet/calibrate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.status === "ok") {
                await fetchPrinters();
                let msg = `🎯 Калібрування запущено на ${data.calibrated_count} принтерах!`;
                if (data.skipped_count > 0) {
                    msg += `\n(Пропущено зайнятих/офлайн: ${data.skipped_count})`;
                }
                alert(msg);
            } else {
                alert("Помилка: " + (data.error || "Невідомо"));
            }
        }
    } catch (e) {
        console.error("Fleet batch action error:", e);
        alert("Помилка зв'язку під час виконання групової дії.");
    }
}

export function openAddPrinterModal() {
    triggerHaptic("medium");
    const form = document.getElementById("add-printer-form");
    if (form) form.reset();
    const modal = document.getElementById("add-printer-modal");
    if (modal) modal.classList.add("active");
    setTimeout(() => {
        const nameInput = document.getElementById("new-p-name");
        if (nameInput) nameInput.focus();
    }, 100);
}

export function closeAddPrinterModal() {
    triggerHaptic("light");
    const modal = document.getElementById("add-printer-modal");
    if (modal) modal.classList.remove("active");
}

export async function submitAddPrinterForm() {
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
    const savePrinterSubmitBtn = document.getElementById("save-printer-submit");
    if (savePrinterSubmitBtn) {
        savePrinterSubmitBtn.disabled = true;
        savePrinterSubmitBtn.textContent = "Збереження...";
    }

    try {
        const data = await api.addPrinter({ name, ip, accessCode, serialNumber, printer_model });
        if (data.status === "ok") {
            closeAddPrinterModal();
            const form = document.getElementById("add-printer-form");
            if (form) form.reset();
            fetchPrinters();
        } else {
            alert("Помилка додавання принтера: " + (data.error || "Невідомо"));
        }
    } catch (e) {
        console.error("Add printer error:", e);
        alert("Помилка з'єднання або таймаут при додаванні принтера.");
    } finally {
        if (savePrinterSubmitBtn) {
            savePrinterSubmitBtn.disabled = false;
            savePrinterSubmitBtn.textContent = "Зберегти принтер";
        }
    }
}

/**
 * Initialize event listeners for printers and farm controls
 */
export function initPrintersModule() {
    // Search input
    const searchInput = document.getElementById("printer-search-input");
    if (searchInput) {
        searchInput.addEventListener("input", applyPrinterFilters);
    }

    // Filter pills
    document.querySelectorAll("#tab-printers .filter-pills .pill-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            triggerHaptic("selection");
            document.querySelectorAll("#tab-printers .filter-pills .pill-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            applyPrinterFilters();
        });
    });

    // View switcher: Detailed vs Compact
    const btnViewDetailed = document.getElementById("btn-view-detailed");
    const btnViewCompact = document.getElementById("btn-view-compact");
    const printersGrid = document.getElementById("printers-grid");
    const dashboardGrid = document.getElementById("dashboard-grid");

    if (btnViewDetailed && btnViewCompact) {
        btnViewDetailed.addEventListener("click", () => {
            triggerHaptic("selection");
            btnViewDetailed.classList.add("active");
            btnViewCompact.classList.remove("active");
            if (printersGrid) printersGrid.style.display = "";
            if (dashboardGrid) dashboardGrid.style.display = "none";
            localStorage.setItem("farm_view_mode", "detailed");
            renderPrinters();
        });

        btnViewCompact.addEventListener("click", () => {
            triggerHaptic("selection");
            btnViewCompact.classList.add("active");
            btnViewDetailed.classList.remove("active");
            if (printersGrid) printersGrid.style.display = "none";
            if (dashboardGrid) dashboardGrid.style.display = "grid";
            localStorage.setItem("farm_view_mode", "compact");
            renderPrinters();
        });

        // Restore view preference
        const savedView = localStorage.getItem("farm_view_mode");
        if (savedView === "compact") {
            btnViewCompact.click();
        }
    }

    // Modal action buttons
    const btnPause = document.getElementById("btn-action-pause");
    const btnResume = document.getElementById("btn-action-resume");
    const btnStop = document.getElementById("btn-action-stop");
    const btnLight = document.getElementById("btn-action-light");
    const btnNotify = document.getElementById("btn-action-notify");
    const btnCalibrate = document.getElementById("btn-action-calibrate");
    const btnResetMaint = document.getElementById("btn-action-reset-maint");
    const btnSkipObjectModal = document.getElementById("btn-action-skip-object");
    const closeModalBtn = document.getElementById("close-printer-modal") || document.getElementById("close-modal-btn");
    const printerModal = document.getElementById("printer-modal");
    const btnPrinterSettings = document.getElementById("btn-printer-settings");
    const refreshCamBtn = document.getElementById("refresh-cam-btn");
    const fullscreenCamBtn = document.getElementById("fullscreen-cam-btn");
    const cameraImg = document.getElementById("camera-snapshot-img");
    const closeFullscreenCamBtn = document.getElementById("close-fullscreen-cam-btn");
    const fullscreenRefreshCamBtn = document.getElementById("fullscreen-refresh-cam-btn");

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
        const p = state.printers.find(x => x.id === state.selectedPrinterId);
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
    if (btnSkipObjectModal) {
        btnSkipObjectModal.addEventListener("click", () => {
            const sec = document.getElementById("modal-skip-objects-section");
            if (sec) sec.scrollIntoView({ behavior: "smooth" });
        });
    }

    if (closeModalBtn) closeModalBtn.addEventListener("click", closePrinterModal);
    if (printerModal) {
        printerModal.addEventListener("click", (e) => {
            if (e.target === printerModal) closePrinterModal();
        });
    }
    if (btnPrinterSettings) {
        btnPrinterSettings.addEventListener("click", () => {
            if (state.selectedPrinterId) {
                openPrinterSettingsModal(state.selectedPrinterId);
            }
        });
    }
    if (refreshCamBtn) refreshCamBtn.addEventListener("click", () => {
        triggerHaptic("light");
        if (state.selectedPrinterId) loadCameraSnapshot(state.selectedPrinterId);
    });

    if (fullscreenCamBtn) fullscreenCamBtn.addEventListener("click", openFullscreenCamera);
    if (cameraImg) cameraImg.addEventListener("click", openFullscreenCamera);
    if (closeFullscreenCamBtn) closeFullscreenCamBtn.addEventListener("click", closeFullscreenCamera);
    if (fullscreenRefreshCamBtn) fullscreenRefreshCamBtn.addEventListener("click", () => {
        triggerHaptic("light");
        if (state.selectedPrinterId) loadCameraSnapshot(state.selectedPrinterId);
    });

    // Speed controls
    document.querySelectorAll(".speed-selector .speed-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const level = parseInt(btn.getAttribute("data-level"), 10);
            sendPrinterAction({ action: "set_speed", level: level });
        });
    });

    // Fleet batch buttons
    const btnFleetLightOn = document.getElementById("fleet-light-on-btn");
    const btnFleetLightOff = document.getElementById("fleet-light-off-btn");
    const btnFleetCalibrate = document.getElementById("fleet-calibrate-btn");
    const closeFleetBatchModalBtn = document.getElementById("close-fleet-batch-modal");
    const fleetBatchModal = document.getElementById("fleet-batch-modal");
    const fleetBatchSelectAll = document.getElementById("fleet-batch-select-all");
    const fleetBatchRunAllBtn = document.getElementById("fleet-batch-run-all-btn");
    const fleetBatchRunSelectedBtn = document.getElementById("fleet-batch-run-selected-btn");

    if (btnFleetLightOn) btnFleetLightOn.addEventListener("click", () => openFleetBatchModal("light_on"));
    if (btnFleetLightOff) btnFleetLightOff.addEventListener("click", () => openFleetBatchModal("light_off"));
    if (btnFleetCalibrate) btnFleetCalibrate.addEventListener("click", () => openFleetBatchModal("calibrate"));
    if (closeFleetBatchModalBtn) closeFleetBatchModalBtn.addEventListener("click", () => fleetBatchModal?.classList.remove("active"));
    if (fleetBatchModal) {
        fleetBatchModal.addEventListener("click", (e) => {
            if (e.target === fleetBatchModal) fleetBatchModal.classList.remove("active");
        });
    }
    if (fleetBatchSelectAll) {
        fleetBatchSelectAll.addEventListener("change", () => {
            const checked = fleetBatchSelectAll.checked;
            document.querySelectorAll(".fleet-batch-printer-chk:not(:disabled)").forEach(chk => {
                chk.checked = checked;
            });
            updateFleetBatchSelectedCount();
        });
    }
    if (fleetBatchRunAllBtn) {
        fleetBatchRunAllBtn.addEventListener("click", () => {
            if (currentFleetBatchAction) executeFleetBatchAction(currentFleetBatchAction, null);
        });
    }
    if (fleetBatchRunSelectedBtn) {
        fleetBatchRunSelectedBtn.addEventListener("click", () => {
            const selectedIds = Array.from(document.querySelectorAll(".fleet-batch-printer-chk:not(:disabled):checked")).map(c => c.value);
            if (selectedIds.length === 0) return;
            if (currentFleetBatchAction) executeFleetBatchAction(currentFleetBatchAction, selectedIds);
        });
    }

    // Add printer modal
    const addPrinterBtn = document.getElementById("add-printer-btn");
    const closeAddPrinterModalBtn = document.getElementById("close-add-printer-modal");
    const addPrinterModal = document.getElementById("add-printer-modal");
    const addPrinterFormEl = document.getElementById("add-printer-form");
    const savePrinterSubmitBtn = document.getElementById("save-printer-submit");

    if (addPrinterBtn) addPrinterBtn.addEventListener("click", openAddPrinterModal);
    if (closeAddPrinterModalBtn) closeAddPrinterModalBtn.addEventListener("click", closeAddPrinterModal);
    if (addPrinterModal) {
        addPrinterModal.addEventListener("click", (e) => {
            if (e.target === addPrinterModal) closeAddPrinterModal();
        });
    }
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

    // Delete printer button inside settings modal
    const btnActionDelete = document.getElementById("btn-action-delete");
    if (btnActionDelete) {
        btnActionDelete.addEventListener("click", async () => {
            const targetId = document.getElementById("ps-modal-printer-id")?.value || state.selectedPrinterId;
            if (!targetId) return;
            const p = (state.printers || []).find(x => x.id === targetId);
            const pName = p ? p.name : targetId;
            if (confirm(`Ви дійсно бажаєте ВИДАЛИТИ принтер "${pName}" з системи?`)) {
                triggerHaptic("medium");
                btnActionDelete.disabled = true;
                try {
                    const data = await api.deletePrinter(targetId);
                    if (data.status === "ok") {
                        document.getElementById("printer-settings-modal")?.classList.remove("active");
                        document.getElementById("printer-modal")?.classList.remove("active");
                        state.selectedPrinterId = null;
                        await fetchPrinters();
                    } else {
                        alert("Помилка видалення принтера: " + (data.error || "Невідомо"));
                    }
                } catch (e) {
                    console.error("Delete printer error:", e);
                    alert("Помилка при видаленні принтера.");
                } finally {
                    btnActionDelete.disabled = false;
                }
            }
        });
    }
}
